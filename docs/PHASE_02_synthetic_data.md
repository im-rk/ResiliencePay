# Phase 2 — Synthetic Data Generation Service

**Depends on:** Phase 1 (schema, factories)
**Unblocks:** Phase 8 (batch evaluation needs a dataset), all pipeline testing
**Owner:** DB/backend owner (can be same person as Phase 1)
**Estimated time:** ~0.5-1 day

## Objective
Produce a reproducible, realistically-noisy synthetic dataset — inserted as
real rows through the actual schema, not a detached JSON file — that
exercises every downstream phase honestly.

## Scope
**In scope:** the generator itself, distribution shaping, reproducibility
guarantees, schema-validity guarantees.
**Out of scope:** anything that consumes this data (Diagnose onward).

## Deliverables mapped to monorepo paths

| Path | What goes here |
|---|---|
| `data/generator.py` | Main generation logic |
| `data/error_code_samples.py` | Realistic gateway error code pools per `CauseCategory` |
| `data/tests/test_reproducibility.py` | Same-seed → identical-output test |
| `data/tests/test_distribution.py` | Chi-squared distribution conformance test |
| `data/tests/test_schema_validity.py` | Every generated row passes Phase 1 constraints |

## Detailed task breakdown

1. **Distribution table** (from `DATA_MODEL.md` §4) — hardcode as a
   constant dict in `data/generator.py`, imported from
   `packages.domain_constants.cause_categories` for the category keys so
   there is exactly one source of truth for valid categories.

2. **Core generator function**
   ```python
   import numpy as np
   from packages.db_models.factories import EpisodeFactory, EventFactory

   CAUSE_DISTRIBUTION = {
       "insufficient_funds": 0.30, "expired_card": 0.15, "otp_failure": 0.15,
       "bank_timeout": 0.15, "mandate_inactive": 0.10, "hard_decline": 0.10,
       "customer_cancelled": 0.05,
   }
   RECOVERABLE_CEILING = {
       "insufficient_funds": 0.70, "expired_card": 0.55, "otp_failure": 0.85,
       "bank_timeout": 0.75, "mandate_inactive": 0.40, "hard_decline": 0.15,
       "customer_cancelled": 0.0,
   }

   def generate_batch(seed: int, n: int, merchant_id) -> list[dict]:
       rng = np.random.default_rng(seed)
       drafts = []
       for _ in range(n):
           cause = rng.choice(list(CAUSE_DISTRIBUTION), p=list(CAUSE_DISTRIBUTION.values()))
           drafts.append({
               "cause_category": cause,
               "gateway_error_code": sample_error_code(cause, rng),
               "amount": int(rng.integers(9_900, 999_900)),  # paise
               "customer_segment": sample_segment(rng),
               "occurred_at": sample_timestamp(rng, window_days=14),
               "opted_out": bool(rng.random() < 0.05),
               "_ground_truth_recoverable": bool(rng.random() < RECOVERABLE_CEILING[cause]),
           })
       return drafts
   ```
   **Critical:** `_ground_truth_recoverable` is prefixed with `_` and must
   never be passed to `services/diagnose` or `services/decide` — it exists
   solely for `eval/`'s outcome simulation (Phase 8). Enforce this with a
   code comment AND a test that asserts the pipeline's input schema
   (`DiagnosisInput` / event ingestion schema) has no such field.

3. **Insert through the real schema**, not a flat file — use
   `EpisodeFactory`/`EventFactory` (or direct model construction) so every
   generated row is validated by Phase 1's constraints at insert time.

4. **Content-addressed dataset identity** — compute
   `dataset_ref = f"seed={seed},n={n},dist_hash={hash(CAUSE_DISTRIBUTION)}"`
   and store it on the `batch_runs` row (Phase 8), so any headline number
   can be traced back to the exact generation parameters that produced it.

## Edge-case matrix

| Case | Handling |
|---|---|
| `n = 0` | Returns empty list, zero DB writes, no crash |
| Same seed + params run twice | Byte-identical output (hash-compared in test) |
| Extreme amounts (₹1, ₹10,00,000) | Included at low frequency deliberately, to exercise formatting/overflow paths downstream |

## Design decisions & trade-offs

| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| Randomness source | `random` vs. `numpy.random.Generator` | `numpy.random.Generator(seed)` | Explicit generator object avoids global-state seed pollution across test runs |
| Distribution shaping | Uniform per field vs. joint/correlated | Joint (cause ↔ recoverability correlated) | Uncorrelated synthetic data is the fastest way to make judges distrust your numbers |
| Dataset identity | Regenerate-and-overwrite vs. content-addressed | Content-addressed hash stored with each batch run | Lets you prove exactly which dataset produced which claimed number |

## Test plan
- **Reproducibility:** identical seed+params → identical serialized output.
- **Distribution:** n=10,000, chi-squared test against target distribution within tolerance.
- **Schema-validity:** every generated + inserted row passes all Phase 1 constraints.
- **Leakage test:** assert `_ground_truth_recoverable` never appears in any schema/type consumed by `services/diagnose` or `services/decide`.

## Definition of Done
- [ ] Reproducibility, distribution, and schema-validity tests pass.
- [ ] Leakage test passes (ground truth never reaches the pipeline under test).
- [ ] 200+ event batch inserted cleanly into the real schema end-to-end.

## Handoff to Phase 3
Phase 3 assumes: a way to pull a batch of real `Event` rows (via
`data/generator.py` + DB query) to run diagnosis against, with realistic,
non-uniform `gateway_error_code` values to classify.
