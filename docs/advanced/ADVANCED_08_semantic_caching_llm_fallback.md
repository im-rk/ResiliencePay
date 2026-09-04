# Advanced Feature 8 — Semantic Caching for the LLM Diagnosis Fallback

**Effort:** ~half a day
**Builds on:** Phase 3 (Diagnose)
**Demo impact:** Moderate-high — a real cost/latency optimization technique, cheap to add given `pgvector` is a standard Postgres extension

---

## The gap this closes

Every time an event's `gateway_error_code` doesn't match the known
taxonomy, Phase 3's design calls an LLM to classify it — correct behavior,
but on a real high-volume system, many "unknown" error messages are
actually semantically identical or near-identical to ones already
classified minutes or hours earlier. Calling the LLM fresh every single
time is unnecessary latency and cost for something that's often a repeat
of already-solved work.

## The technique: embedding-based semantic cache

Instead of an exact-string cache (which would miss near-duplicate
messages), embed the incoming error message and search for a
semantically similar *already-classified* message using vector similarity
— `pgvector` (a standard, widely-used Postgres extension) makes this a
single SQL query, no separate vector database needed.

## Implementation

### Migration addition

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE diagnosis_embeddings (
    embedding_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_message     TEXT NOT NULL,
    embedding       vector(1536) NOT NULL,
    cause_category  TEXT NOT NULL REFERENCES cause_categories(cause_category),
    confidence      NUMERIC(4,3) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_diagnosis_embeddings_vector ON diagnosis_embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

### `services/diagnose/semantic_cache.py`

```python
SIMILARITY_THRESHOLD = 0.95  # deliberately high — a false-positive cache
                              # hit here means misclassifying a payment
                              # failure cause, which is worse than the
                              # latency/cost of an unnecessary LLM call


def find_cached_classification(db_session, raw_message: str, embed_fn):
    query_embedding = embed_fn(raw_message)
    result = db_session.execute(
        text("""
            SELECT cause_category, confidence, 1 - (embedding <=> :query_embedding) AS similarity
            FROM diagnosis_embeddings
            ORDER BY embedding <=> :query_embedding
            LIMIT 1
        """),
        {"query_embedding": query_embedding},
    ).fetchone()

    if result is None or result.similarity < SIMILARITY_THRESHOLD:
        return None

    return DiagnosisResult(
        cause_category=result.cause_category, confidence=float(result.confidence),
        method="semantic_cache_hit",
        justification=f"similarity={result.similarity:.4f} to a prior classification",
    )


def store_classification_for_future_cache_hits(db_session, raw_message: str, result, embed_fn):
    db_session.add(DiagnosisEmbedding(
        raw_message=raw_message, embedding=embed_fn(raw_message),
        cause_category=result.cause_category, confidence=result.confidence,
    ))
    db_session.commit()
```

### Wiring into `services/diagnose/service.py`

```python
def diagnose(event, db_session, embed_fn):
    if category := RULES.get(event.gateway_error_code):
        return DiagnosisResult(cause_category=category, confidence=1.0, method="rule_based")

    if cached := find_cached_classification(db_session, event.raw_gateway_message, embed_fn):
        return cached  # LLM call entirely skipped

    result = llm_fallback.classify(event.raw_gateway_message)
    if result.method == "llm_fallback":  # only cache genuinely successful classifications, never a fallback_failed result
        store_classification_for_future_cache_hits(db_session, event.raw_gateway_message, result, embed_fn)
    return result
```

**Never cache a `fallback_failed` or `unknown` result** — caching a
failure to classify would just make future genuinely-classifiable
messages incorrectly match against a non-answer.

## Honest trade-off to state explicitly

A 0.95 cosine-similarity threshold is a judgment call, not a proven
optimum — state this if asked, and note the real risk: too low a
threshold risks a false-positive cache hit misclassifying a genuinely
different failure cause, which is worse than the cost/latency this
feature saves. This is exactly why the threshold is conservative, and why
this is presented as a legitimate optimization with a stated risk
trade-off, not an unqualified win.

## Test to write

```python
def test_semantic_cache_hit_skips_llm_call(db_session, fake_embed_fn):
    store_classification_for_future_cache_hits(
        db_session, "Insufficient balance in account",
        DiagnosisResult(cause_category="insufficient_funds", confidence=0.92, method="llm_fallback"),
        fake_embed_fn,
    )
    result = find_cached_classification(db_session, "Insufficient funds available", fake_embed_fn)
    assert result is not None
    assert result.cause_category == "insufficient_funds"
    assert result.method == "semantic_cache_hit"

def test_dissimilar_message_does_not_hit_cache(db_session, fake_embed_fn):
    store_classification_for_future_cache_hits(
        db_session, "Insufficient balance in account",
        DiagnosisResult(cause_category="insufficient_funds", confidence=0.92, method="llm_fallback"),
        fake_embed_fn,
    )
    result = find_cached_classification(db_session, "Card reported stolen by issuer", fake_embed_fn)
    assert result is None
```

## What to say in the demo

*"Calling an LLM for every unclassified error is unnecessary once we've
already seen a semantically similar one — we embed incoming error text
and check for a high-confidence match against prior classifications using
pgvector, a standard Postgres extension, before ever calling the LLM. The
threshold is deliberately conservative, because a wrong cache hit
misclassifying a payment failure is a worse outcome than an unnecessary
LLM call."*
