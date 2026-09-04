# Phase 6 — Act (Execution Layer)

**Depends on:** Phase 4 (only ever called with a gate-passed decision), Phase 5 (chosen arm)
**Unblocks:** Phase 7 (Observe watches for the outcomes of these actions), Phase 11 (chaos testing hooks into this layer)
**Owner:** backend/integration-strongest team member
**Estimated time:** ~1-1.5 days (can run in parallel with Phase 5)

## Objective
Translate an approved decision into a real Razorpay test-mode API call or a
clearly-labeled simulated action, correctly handling delayed/scheduled
actions and idempotency.

## Scope
**In scope:** Razorpay client wrapper, nudge generation, delayed-action
scheduling via Celery, idempotency, fault-injection hooks (used by Phase 11).
**Out of scope:** capturing the result of the action (Phase 7).

## Deliverables mapped to monorepo paths

| Path | What goes here |
|---|---|
| `services/act/razorpay_client.py` | Idempotency-key-aware wrapper over the Razorpay SDK |
| `services/act/nudge_generator.py` | LLM-based Hinglish/English message generation, with template fallback |
| `services/act/fault_injection.py` | Flag-gated fault injection hooks (built now, exercised in Phase 11) |
| `services/act/service.py` | `execute_action()` orchestration/routing by arm type |
| `apps/worker/src/tasks/execute_delayed_action.py` | Celery task for ETA-scheduled retries |
| `services/act/tests/test_idempotency.py` | Duplicate-call-safety test |
| `services/act/tests/test_routing.py` | Each arm type routes correctly |

## Detailed task breakdown

1. **Razorpay client wrapper** — every mutating call takes an
   `idempotency_key` (e.g., `f"action:{decision_id}"`), wraps the SDK call
   with retry (exponential backoff, max 3 attempts) on transient 5xx, and
   raises a typed exception on permanent failure.

2. **Routing logic**
   ```python
   def execute_action(decision: Decision, gate_result: GateResult) -> Action:
       assert gate_result.passed, "execute_action must never be called on a blocked decision"
       idempotency_key = f"action:{decision.decision_id}"

       if decision.chosen_arm in REAL_MONEY_ARMS:
           result = razorpay_client.create_retry_payment_link(decision.episode, idempotency_key)
           return Action(simulated=False, razorpay_ref_id=result.id, status="executed")
       elif decision.chosen_arm in DELAYED_ARMS:
           eta = now() + ARM_DELAYS[decision.chosen_arm]
           execute_delayed_action.apply_async(args=[decision.decision_id], eta=eta)
           return Action(simulated=False, scheduled_for=eta, status="scheduled")
       elif decision.chosen_arm in NUDGE_ARMS:
           text = nudge_generator.generate(decision, language=decision.chosen_arm)
           return Action(simulated=True, message_text=text, status="executed")
       else:  # 'stop'
           return Action(simulated=True, status="executed")
   ```

3. **Nudge generator** — LLM call for message text; on LLM failure, falls
   back to a pre-written template, still marked `simulated=true`, logged
   with `method="template_fallback"` so this is visible in the audit trail,
   not silently masked.

4. **Fault injection hooks** — wrap the Razorpay client and the LLM client
   calls with a flag-gated decorator that can simulate timeouts/5xx/malformed
   responses when `FAULT_INJECTION_ENABLED=true`. Build this now, even
   though it's exercised properly in Phase 11 — it's cheap to add while
   you're already writing these clients, and expensive to retrofit later.

5. **Celery delayed task**
   ```python
   @celery_app.task(bind=True, max_retries=3)
   def execute_delayed_action(self, decision_id):
       decision = load_decision(decision_id)
       # re-check the gate at execution time — state may have changed since scheduling
       gate_result = evaluate_gate(build_context(decision))
       if gate_result.passed:
           execute_action(decision, gate_result)
       else:
           log_blocked(decision, gate_result)
   ```
   **Important:** re-evaluate the gate at execution time, not just at
   scheduling time — a customer could opt out in the hours between
   scheduling and execution.

## Edge-case matrix

| Case | Expected behavior |
|---|---|
| `execute_action` called with `gate_result.passed=False` | Assertion error — structurally unreachable, defensive check |
| Razorpay API returns transient 5xx | Retried with backoff, then marked `status="failed"` with reason logged |
| Same `decision_id` executed twice (e.g., retried Celery task) | Idempotency key prevents duplicate Razorpay resource creation |
| LLM nudge generation fails | Falls back to template, still `simulated=true`, method logged |
| Gate re-check at delayed-execution time fails (e.g., opted out since scheduling) | Action is blocked at execution time, logged, not silently executed anyway |

## Design decisions & trade-offs

| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| Delayed scheduling | `time.sleep()` loop, cron polling, task queue | Celery ETA-scheduled tasks | Models the real timing problem correctly; `time.sleep()` in a handler is a real anti-pattern |
| Razorpay resilience | Fire-and-forget vs. idempotent retry | Idempotency key + retry with backoff | Prevents double-charging/double-link-creation on network blips |
| Simulated/real boundary | Inferred from arm type at render time | Explicit boolean set at creation, persisted, never re-derived | Prevents any code path from mislabeling a simulated action as real |

## Test plan
- **Unit:** each arm type routes to the correct execution path (mocked clients).
- **Idempotency:** call `execute_action` twice with the same `decision_id`, assert only one real Razorpay resource created.
- **Delayed task test:** `retry_long_delay` enqueues a Celery task with ETA ~2-3 days out, not executed immediately.
- **Gate re-check test:** simulate an opt-out occurring between scheduling and execution, assert the delayed task blocks correctly.

## Definition of Done
- [ ] Idempotency test passes.
- [ ] All arm-type routing paths covered.
- [ ] Failure/fallback paths (Razorpay 5xx, LLM failure) tested.
- [ ] Fault-injection hooks present and flag-gated (off by default).

## Handoff to Phase 7
Phase 7 assumes: every executed action has a corresponding `actions` row
with `razorpay_ref_id` (if real) or `message_text` (if simulated), and that
delayed actions will eventually re-enter this same code path when their
Celery ETA fires.
