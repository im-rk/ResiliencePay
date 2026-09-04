# Advanced Feature 7 — The Dual-Write Problem: Compensating Transactions & Dead Letter Queue

**Effort:** ~1 day
**Builds on:** Phase 6 (Act)
**Demo impact:** Very high for any judge with distributed-systems background — this is the single most sophisticated addition in the entire project if built correctly

---

## The problem, stated precisely

`execute_action()` does two things that cannot be wrapped in a single
atomic transaction, because they happen against two different systems:

1. Call Razorpay's API to create a real payment link (an external,
   irreversible side effect — money-adjacent, and outside your control
   once it succeeds).
2. Write the corresponding `actions` row to your local Postgres database.

**What happens if step 1 succeeds and step 2 fails?** — e.g., Postgres is
briefly unreachable, the process crashes between the two calls, or a
serialization error occurs on write. You now have a **real Razorpay
payment link that exists, with zero record of it anywhere in your
system.** This is not a hypothetical edge case; it's a named, well-studied
distributed-systems failure mode called the **dual-write problem**, and
it exists any time a single logical operation must touch two independent
systems without a shared transaction.

Almost no hackathon team will have thought about this at all. Handling it
correctly — not perfectly, but *visibly and honestly* — is a strong signal
of real distributed-systems maturity.

## Why this can't be "solved" with a database transaction

A Postgres transaction can make your *local* writes atomic. It cannot make
a *local write* atomic with a *remote HTTP call* — there is no shared
transaction coordinator between your database and Razorpay's API. Anyone
proposing "just wrap it in a transaction" as the fix doesn't understand
the actual problem; the correct answer is to **accept that this window
exists, detect when it's been hit, and recover from it deliberately** —
which is exactly what a Saga pattern and a Dead Letter Queue (DLQ) do.

## The approach: outbox-style detection + a reconciliation DLQ

Rather than a full formal Saga orchestrator (disproportionate for this
project's scale), implement the **minimum correct version** of the same
idea: record your *intent* to call Razorpay durably, in your own database,
*before* making the external call — so that even if the external call
succeeds but the follow-up local write fails, you have a durable local
record of the attempt to reconcile against.

```
1. INSERT a `pending_action` row (status='attempting') — a local,
   durable record of intent, written and committed BEFORE calling Razorpay.
2. Call Razorpay's API.
3a. On success: UPDATE the same row to status='confirmed', now with the
    real razorpay_ref_id attached. This becomes the normal `actions` row.
3b. On failure (Razorpay call itself failed): UPDATE to status='failed'.
3c. On an exception between step 2 and 3a (e.g., the process crashes
    after Razorpay confirms, before the UPDATE lands) — the row is left
    in 'attempting' state. A periodic reconciliation job (see below)
    finds any row stuck in 'attempting' beyond a timeout and actively
    checks Razorpay's API for what actually happened, then resolves it —
    or, if it genuinely cannot be resolved automatically, moves it to
    the Dead Letter Queue for manual review.
```

## Implementation

### Schema addition — `packages/db-models/models/pending_action.py`

```python
class PendingAction(Base):
    """Durable record of intent, written BEFORE the external Razorpay
    call — this is what makes the dual-write window detectable and
    recoverable rather than silently lost. See ADVANCED_07 for the full
    rationale."""
    __tablename__ = "pending_actions"

    pending_action_id: Mapped[uuid.UUID] = uuid_pk()
    decision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="attempting")
    # 'attempting' | 'confirmed' | 'failed' | 'reconciled' | 'dead_lettered'
    razorpay_ref_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = created_at_col()
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

### `services/act/service.py` addition

```python
def execute_real_money_action(decision, razorpay_client, db_session) -> "Action":
    idempotency_key = f"action:{decision.decision_id}"

    # Step 1 — durable intent record, committed BEFORE the external call.
    pending = PendingAction(decision_id=decision.decision_id,
                             idempotency_key=idempotency_key, status="attempting")
    db_session.add(pending)
    db_session.commit()  # deliberately a separate, immediate commit — this row must survive even if the process crashes next

    try:
        result = razorpay_client.create_retry_payment_link(decision.episode, idempotency_key)
        pending.status = "confirmed"
        pending.razorpay_ref_id = result.id
        pending.resolved_at = now()
        db_session.commit()
        return Action(decision_id=decision.decision_id, simulated=False,
                       razorpay_ref_id=result.id, status="executed")
    except (RazorpayPermanentError, RazorpayTransientError) as e:
        pending.status = "failed"
        pending.resolved_at = now()
        db_session.commit()
        raise
```

### The reconciliation job — `apps/worker/src/tasks/reconcile_pending_actions.py`

```python
STUCK_THRESHOLD = timedelta(minutes=10)  # generous relative to normal Razorpay latency

@celery_app.task
def reconcile_pending_actions():
    stuck = find_pending_actions(status="attempting", older_than=now() - STUCK_THRESHOLD)
    for pending in stuck:
        # We don't know if Razorpay's call actually succeeded. Check directly.
        found_payment = razorpay_client.find_payment_link_by_idempotency_key(pending.idempotency_key)
        if found_payment is not None:
            # Razorpay DID create it — this was exactly the dual-write
            # scenario. Reconcile: the external side effect is real, we
            # just missed recording it locally until now.
            pending.status = "reconciled"
            pending.razorpay_ref_id = found_payment.id
            pending.resolved_at = now()
            create_action_from_reconciled_pending(pending)  # backfills the actions row
            audit_log_service.write_note(pending, note="reconciled_after_dual_write_gap")
        else:
            # Razorpay has no record — the original call genuinely never
            # went through, or is unresolvable automatically. Escalate.
            pending.status = "dead_lettered"
            pending.resolved_at = now()
            send_to_dead_letter_queue(pending)
        db_session.commit()
```

### The Dead Letter Queue

For this project's scale, a DLQ can legitimately be **a dedicated,
clearly-flagged table** (`dead_lettered_actions`) surfaced prominently in
the dashboard, rather than a separate message-queue infrastructure
component — state this scoping decision explicitly if asked, it's the
correctly-sized solution here, not a shortcut.

```python
def send_to_dead_letter_queue(pending: PendingAction) -> None:
    db_session.add(DeadLetteredAction(
        pending_action_id=pending.pending_action_id,
        reason="razorpay_call_unresolvable_after_reconciliation_attempt",
        requires_manual_review=True,
    ))
```

## Why finding a real occurrence of this during testing would be a GREAT demo moment, not an embarrassment

If you deliberately inject a crash between the Razorpay call and the local
commit during your chaos-testing rehearsal (Phase 11), and then show the
reconciliation job correctly detecting and resolving the resulting phantom
state — that is one of the strongest "what broke and how you got out"
demonstrations available to you, directly matching the buildathon's own
stated judging philosophy, and very few teams will have anything like it.

## Test to write

```python
def test_reconciliation_recovers_a_genuine_dual_write_gap(db_session, razorpay_test_mode):
    """Simulates the exact failure: Razorpay call succeeds, but we crash
    before recording it locally."""
    pending = create_pending_action(status="attempting", created_at=now() - timedelta(minutes=15))
    # Simulate that Razorpay actually DID create this resource, even though
    # our local process never got to record the success:
    create_real_test_mode_payment_link_with_idempotency_key(pending.idempotency_key)

    reconcile_pending_actions()

    updated = get_pending_action(pending.pending_action_id)
    assert updated.status == "reconciled"
    assert updated.razorpay_ref_id is not None
    action = get_action_created_from_pending(pending.pending_action_id)
    assert action is not None, "a real, previously-untracked Razorpay resource must result in a backfilled actions row"

def test_reconciliation_dead_letters_a_genuinely_failed_attempt(db_session):
    pending = create_pending_action(status="attempting", created_at=now() - timedelta(minutes=15))
    # No corresponding Razorpay resource exists for this idempotency key.
    reconcile_pending_actions()
    updated = get_pending_action(pending.pending_action_id)
    assert updated.status == "dead_lettered"
```

## What to say in the demo

*"There's a well-known distributed-systems problem here: our Razorpay call
and our local database write can't be wrapped in one atomic transaction,
because they're two different systems. If the Razorpay call succeeds but
our local write fails — a process crash, a brief database outage — you get
a real payment resource with no local record of it. We handle this with a
durable intent record written before the external call, and a
reconciliation job that actively checks Razorpay for anything left in a
stuck state, either backfilling the record if the call actually succeeded,
or routing it to a dead-letter table for manual review if it didn't. We
can trigger this scenario live if you'd like to see it."*
