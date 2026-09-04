# Phase 4 — Gate (Compliance Engine)

**Depends on:** Phase 1 (schema for `gate_checks`, `opt_outs`)
**Unblocks:** Phase 5 (bandit is developed against this known-safe boundary), Phase 6 (Act only ever receives gate-passed decisions)
**Owner:** whoever is most rigorous about testing on the team — this is the highest-stakes correctness phase
**Estimated time:** ~1 day

## Objective
Build a deterministic, independently-testable safety layer that the
learning system (Decide) cannot override. **Build this before Phase 5**,
even though it logically executes after Decide in the pipeline — the bandit
should be developed against an already-hardened boundary.

## Scope
**In scope:** all compliance rules, orchestration, exhaustive unit +
adversarial + (stretch) property-based tests.
**Out of scope:** what happens after a gate-passed decision (Phase 6).

## Deliverables mapped to monorepo paths

| Path | What goes here |
|---|---|
| `services/gate/rules.py` | `check_max_attempts`, `check_opt_out`, `check_cool_off`, `check_time_window` |
| `services/gate/service.py` | `evaluate_gate()` orchestration, runs the rule chain in order |
| `services/gate/schemas.py` | `GateResult` model |
| `services/gate/tests/test_rules.py` | One test per rule, both pass/block directions |
| `services/gate/tests/test_adversarial.py` | High-confidence-bandit-but-still-blocked test |
| `services/gate/tests/test_property_based.py` | (Stretch) `hypothesis`-driven fuzz test |

## Detailed task breakdown

1. **Rule functions** — each pure, independently testable, typed:
   ```python
   RuleResult = Literal["pass"] | tuple[Literal["blocked"], str]

   def check_max_attempts(episode, max_attempts=3) -> RuleResult:
       if episode.attempt_count >= max_attempts:
           return ("blocked", "max_attempts_exceeded")
       return "pass"

   def check_opt_out(customer_id, db) -> RuleResult:
       if db.query(OptOut).filter_by(customer_id=customer_id).count():
           return ("blocked", "customer_opted_out")
       return "pass"

   def check_cool_off(episode, min_gap_hours, now) -> RuleResult:
       if episode.last_action_at and (now - episode.last_action_at) < timedelta(hours=min_gap_hours):
           return ("blocked", "cool_off_active")
       return "pass"

   def check_time_window(now, allowed_hours=(9, 20)) -> RuleResult:
       if not (allowed_hours[0] <= now.hour < allowed_hours[1]):
           return ("blocked", "outside_communication_window")
       return "pass"
   ```

2. **Orchestration** — rules evaluated in a fixed, documented order
   (severity-ordered: opt-out first, then max-attempts, then cool-off, then
   time-window), first block wins, every evaluation (pass or block) writes
   a `gate_checks` row.

3. **`evaluate_gate()` always runs the full rule set on every decision**,
   regardless of the bandit's confidence score — this is the single
   sentence to have ready: *"the bandit's sampled score is never consulted
   by the gate; the gate cannot be influenced by how confident the learning
   system was."*

## Edge-case matrix

| Case | Expected result |
|---|---|
| High-confidence bandit arm, attempt #4 | **Blocked** — confidence irrelevant, rule is absolute |
| Customer opted out mid-episode (after episode opened) | **Blocked** — checked fresh every time, never cached at episode start |
| Two rules would both block | First rule in the documented order fires and is logged |
| Bandit chooses `stop` | Always passes trivially — "do nothing" cannot violate a compliance rule |

## Design decisions & trade-offs

| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| Where compliance logic lives | Inside the bandit's action space vs. a separate hard-coded layer | Separate hard-coded layer, always evaluated after Decide, before Act | A probabilistic system must never be the only thing standing between a decision and a compliance violation — the single most important architectural decision in the project |
| Rule composition | One monolithic function | Chain of independent, typed, individually-testable functions | Each rule independently auditable; a monolith obscures which rule fired |
| Fail-safe direction | Default-deny vs. default-allow with exhaustive tested rules | Default-allow, exhaustive rule set | Pragmatic for a bounded, fully-controlled, fully-tested rule set at this scale |

## Test plan
- **Unit, one per rule, both directions.**
- **Adversarial test:** construct a context where the bandit *would* pick a real-money-moving arm, force gate evaluation, confirm block — screenshot this for your submission.
- **(Stretch) property-based test:** using `hypothesis`, generate random contexts, assert the gate never allows an action when `attempt_count >= max_attempts`, across ≥1000 cases.

## Definition of Done
- [ ] 100% rule coverage in unit tests.
- [ ] Adversarial test passes.
- [ ] (Stretch) property-based test passes across ≥1000 generated cases.
- [ ] Every gate evaluation (pass or block) writes exactly one `gate_checks` row.

## Handoff to Phase 5 & 6
Phase 5 assumes: it can call `evaluate_gate()` after producing a decision
and treat the result as final and non-negotiable. Phase 6 assumes: it will
only ever be invoked with a `GateResult(passed=True)` — add an assertion
for this at the top of `execute_action()`.
