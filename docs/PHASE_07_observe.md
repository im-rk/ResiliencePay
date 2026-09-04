# Phase 7 — Observe & Reward Loop

**Depends on:** Phase 6 (actions to observe outcomes for), Phase 5 (bandit to feed rewards back to)
**Unblocks:** Phase 8 (batch harness needs the same reward logic), Phase 9 (audit trail writes originate here)
**Owner:** backend/integration owner (can be same as Phase 6)
**Estimated time:** ~1 day

## Objective
Close the loop: capture real-world outcomes, compute rewards, feed them
back into the bandit, and write the audit trail — this is what makes the
system genuinely learn rather than just act.

## Scope
**In scope:** webhook handling, reconciliation polling fallback, reward
computation, bandit feedback, audit trail write-through.
**Out of scope:** the audit trail's read/query API (Phase 9).

## Deliverables mapped to monorepo paths

| Path | What goes here |
|---|---|
| `services/observe/webhook_handlers.py` | `payment.captured`, `subscription.charge.failed`, etc. |
| `services/observe/reward_service.py` | Outcome → reward computation, independently testable |
| `apps/worker/src/tasks/reconcile_payment_status.py` | Polling safety-net for missed webhooks |
| `services/audit/audit_log_service.py` | Single write path into `audit_log` (built here, used by Phase 9's read API) |
| `services/observe/tests/test_webhook_idempotency.py` | Duplicate webhook delivery test |
| `services/observe/tests/test_reward_computation.py` | Reward correctness per outcome type |

## Detailed task breakdown

1. **Webhook handler**
   ```python
   def handle_payment_captured_webhook(payload: dict):
       action = find_action_by_razorpay_ref(payload["payment"]["id"])
       outcome = Outcome(
           action_id=action.id,
           result="recovered",
           amount_recovered=payload["payment"]["amount"],
           time_to_resolution_hrs=hours_between(action.executed_at, now()),
       )
       outcome.reward = reward_service.compute(outcome)
       db.upsert(outcome, conflict_target="action_id")  # idempotent on redelivery

       decision = action.decision
       bandit.update(decision.context_bucket, decision.chosen_arm, outcome.reward)
       audit_log_service.write(event=decision.event, decision=decision, outcome=outcome)
   ```
   **Idempotency is mandatory** — most webhook providers (including
   Razorpay) explicitly guarantee at-least-once delivery, so treat duplicate
   delivery as a certainty, not an edge case.

2. **`RewardService`** — kept separate from the webhook handler so reward
   shaping (per `ML_DESIGN.md` §2.5) is independently testable:
   ```python
   def compute(outcome: Outcome) -> float:
       if outcome.result == "recovered":
           return 1.0
       if outcome.result == "blocked_by_policy":
           return -0.1
       return 0.0
   ```

3. **Reconciliation polling task** (safety net) — runs periodically,
   queries any `actions` with `status="scheduled"` or `status="executed"`
   older than a threshold with no corresponding `outcome`, polls
   `GET /payments/{id}` directly, and processes as if the webhook had
   arrived. This is the "webhook + reconciliation" pattern — document why
   both exist, not just the webhook path.

4. **`AuditLogService`** — the single write path into `audit_log`, called
   from exactly one place (here) so there is never ambiguity about where an
   audit row originates:
   ```python
   class AuditLogService:
       def write(self, event, decision=None, gate_result=None, outcome=None):
           db.insert(AuditLog(
               event_id=event.id, episode_id=event.episode_id,
               cause_category=event.diagnosis.cause_category if event.diagnosis else None,
               chosen_arm=decision.chosen_arm if decision else None,
               gate_result=gate_result.passed if gate_result else None,
               simulated=decision.action.simulated if decision and decision.action else None,
               outcome_result=outcome.result if outcome else None,
               reward=outcome.reward if outcome else None,
           ))
   ```

5. **Simulated-action outcomes (for live-demo mode, not batch eval)** —
   since a simulated nudge has no real webhook, provide a manual
   "mark resolved" trigger in the API (`POST /v1/events/{id}/mark-resolved`)
   used during live demos; batch-mode outcome simulation is handled
   separately in Phase 8's eval harness.

## Edge-case matrix

| Case | Expected behavior |
|---|---|
| Webhook arrives for an action already reconciled by the polling job | Idempotent upsert keyed on `action_id`, no duplicate row |
| Webhook references an unknown `razorpay_ref_id` | Logged as an integrity warning, does not crash the handler |
| Simulated nudge action | No real webhook will ever arrive — handled via eval-harness simulation (batch) or manual trigger (live demo) |
| `bandit.update()` called with a `context_bucket` that no longer exists (taxonomy changed) | Falls back to default prior bucket, logs a warning, does not crash the reward loop |
| Duplicate webhook delivered twice | Only one `outcome` row exists after both deliveries |

## Design decisions & trade-offs

| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| Outcome capture (real actions) | Polling only vs. webhook-driven | Webhook-driven + periodic reconciliation poll as fallback | Webhooks are the correct event-driven pattern; polling-only is wasteful and laggy; reconciliation guards against missed webhooks |
| Reward computation location | Inline in webhook handler vs. separate service | Separate `RewardService` | Keeps reward-shaping logic independently testable and swappable |

## Test plan
- **Unit:** `RewardService.compute()` returns expected reward for each outcome type.
- **Integration:** simulated webhook payload → outcome row → bandit state change → audit_log row, all asserted in one test.
- **Idempotency:** same webhook delivered twice → only one outcome row exists.

## Definition of Done
- [ ] Full webhook→outcome→bandit→audit chain integration test passes.
- [ ] Duplicate webhook delivery is provably idempotent.
- [ ] Reconciliation polling task tested against a deliberately "missed" webhook scenario.

## Handoff to Phase 8 & 9
Phase 8 assumes: it can reuse `RewardService` and `AuditLogService` inside
its own (non-webhook-driven, simulated-outcome) batch loop, so both live and
batch modes share identical reward/audit logic. Phase 9 assumes: `audit_log`
rows are already being written correctly and just need a query API on top.
