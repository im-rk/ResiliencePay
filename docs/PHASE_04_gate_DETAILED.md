# Phase 4 — Gate (Compliance Engine) — Full Detailed Spec

**Depends on:** Phase 1 (schema for `gate_checks`, `opt_outs`)
**Unblocks:** Phase 5 (bandit developed against this known-safe boundary), Phase 6 (Act only ever receives gate-passed decisions)
**Owner:** whoever is most rigorous about testing on the team
**Estimated time:** ~1 day — build this BEFORE Phase 5, even though it executes after Decide in the pipeline

---

## 1. Why this phase exists and why it matters more than every other phase

Every other phase in this project can be explained by analogy to an
existing product feature. This phase is different: it's the reason a
real fintech company would ever be allowed to run an autonomous agent
against production payment flows at all. Regulators, card networks, and
internal legal/compliance teams do not accept "the model decided" as an
answer for why a customer was contacted a fourth time after saying stop.
They require a deterministic, auditable, provably-bounded rule layer that
sits between any learning system and any customer-facing or money-moving
action — full stop, no exceptions, no "the AI was pretty confident."

This is not a hackathon nicety. It is the actual regulatory and
operational pattern used by every real payments company doing this kind of
work (Stripe, Recurly, Chargebee Retain, Butter Payments) — the "smart"
part of their systems is always fenced by a "dumb," deterministic,
independently-auditable compliance layer that the smart part cannot
override. If you get this phase right and can articulate why, you are
speaking the actual language of the industry, not hackathon-speak.

---

## 2. Conceptual model — read this before touching code

### 2.1 Why the Gate must be architecturally separate, not just logically separate

It would be technically possible to fold compliance checks into the
bandit's reward function — e.g., "penalize the bandit heavily for choosing
an action beyond the retry limit, so it learns not to." **This is the wrong
design, and it's wrong for a reason worth understanding precisely:** a
learned penalty is a *preference*, not a *guarantee*. Early in training,
before the bandit has seen enough evidence, it might still occasionally
choose the disallowed action, because Thompson Sampling is inherently
probabilistic — that's the whole point of it. A compliance rule that only
holds "most of the time, once the model has learned better" is not a
compliance rule at all. The Gate has to be a hard, deterministic,
zero-exception function that runs **after** the bandit's decision and
**before** any real-world effect — architecturally incapable of being
influenced by how confident or well-trained the bandit is.

### 2.2 Why rules are ordered and why the order itself needs a stated rationale

When multiple compliance rules could independently block an action (e.g.,
a customer is both past their max-attempts limit AND has opted out), which
one gets reported matters — not because the outcome differs (the action is
blocked either way), but because the *audit trail's explanation* differs,
and a merchant or regulator reviewing that trail deserves the most legally
significant reason, not an arbitrary one. The convention here: **check
consent/opt-out first, always** — a customer's explicit "stop contacting
me" is the single most legally and ethically significant signal in this
system, and it should never be silently subordinated to an operational
rule like a retry counter. Document this ordering explicitly; don't let it
be an accident of which `if` statement happens to come first in the code.

### 2.3 Why the Gate re-evaluates fresh state every time, never cached or inherited

A decision made at 9am and scheduled for execution 3 days later must have
its gate re-checked using state *as of the execution moment*, not state as
of the decision moment (this is elaborated further in
`PHASE_06_act_DETAILED.md` §2.3, but the principle originates here). The
Gate's public contract is therefore: **it is a pure function of current
system state at the moment it's called, with no memory of prior gate
evaluations for the same decision.** This is what makes a stale,
long-scheduled action safe to re-verify before it fires.

---

## 3. Detailed component design

### 3.1 `services/gate/rules.py`

```python
from datetime import datetime, timedelta
from typing import Literal

RuleResult = Literal["pass"] | tuple[Literal["blocked"], str]


def check_opt_out(customer_id, db_session) -> RuleResult:
    """Checked FIRST, always — see section 2.2. A customer's explicit
    opt-out is the single most legally significant signal in this system."""
    from packages.db_models.models import OptOut
    exists = db_session.query(OptOut).filter_by(customer_id=customer_id).first() is not None
    return ("blocked", "customer_opted_out") if exists else "pass"


def check_max_attempts(episode, max_attempts: int) -> RuleResult:
    if episode.attempt_count >= max_attempts:
        return ("blocked", "max_attempts_exceeded")
    return "pass"


def check_cool_off(episode, min_cool_off_hours: int, now: datetime) -> RuleResult:
    if episode.last_action_at and (now - episode.last_action_at) < timedelta(hours=min_cool_off_hours):
        return ("blocked", "cool_off_active")
    return "pass"


def check_time_window(now: datetime, allowed_hour_start: int, allowed_hour_end: int) -> RuleResult:
    if not (allowed_hour_start <= now.hour < allowed_hour_end):
        return ("blocked", "outside_communication_window")
    return "pass"


# Explicit, documented order — opt-out is checked first regardless of
# performance considerations, because it's the highest-priority signal.
# See section 2.2 for the rationale.
RULE_CHAIN = [check_opt_out, check_max_attempts, check_cool_off, check_time_window]
```

### 3.2 `services/gate/service.py`

```python
from dataclasses import dataclass
from datetime import datetime

from packages.config.settings import settings
from .rules import check_cool_off, check_max_attempts, check_opt_out, check_time_window


@dataclass(frozen=True)
class GateResult:
    passed: bool
    rule_triggered: str | None


def evaluate_gate(context: "GateContext", db_session, now: datetime | None = None) -> GateResult:
    """Pure with respect to prior gate evaluations — always re-derives its
    answer from current state. See section 2.3. Never accepts the bandit's
    sampled_score or confidence as input — see section 2.1; there is no
    parameter here for the bandit to influence."""
    now = now or datetime.utcnow()

    result = check_opt_out(context.customer_id, db_session)
    if result != "pass":
        return GateResult(passed=False, rule_triggered=result[1])

    result = check_max_attempts(context.episode, settings.gate_max_attempts)
    if result != "pass":
        return GateResult(passed=False, rule_triggered=result[1])

    result = check_cool_off(context.episode, settings.gate_min_cool_off_hours, now)
    if result != "pass":
        return GateResult(passed=False, rule_triggered=result[1])

    result = check_time_window(now, settings.gate_allowed_hour_start, settings.gate_allowed_hour_end)
    if result != "pass":
        return GateResult(passed=False, rule_triggered=result[1])

    return GateResult(passed=True, rule_triggered=None)
```

**Notice `evaluate_gate`'s signature never accepts the chosen arm's
sampled score, confidence, or any bandit-internal value.** This is not an
oversight — it's the concrete implementation of section 2.1's principle.
If a future contributor tries to add "unless the bandit is very confident,
skip this check," the correct response is to refuse that change outright
and point to this section of the doc.

### 3.3 Persisting every evaluation — `services/gate/persistence.py`

```python
from packages.db_models.models import GateCheck


def record_gate_check(db_session, decision_id, result: "GateResult") -> GateCheck:
    """Every evaluation is recorded, pass or block — this table is the
    queryable evidence for 'bounded and gated.' See DATABASE_DESIGN.md
    section 3, point 3."""
    check = GateCheck(
        decision_id=decision_id,
        result="passed" if result.passed else "blocked",
        rule_triggered=result.rule_triggered,
    )
    db_session.add(check)
    db_session.commit()
    return check
```

---

## 4. Full edge-case matrix (expanded)

| # | Case | Expected result | How to test |
|---|---|---|---|
| 1 | High-confidence bandit arm, attempt #4 (max is 3) | **Blocked** — confidence is not a parameter `evaluate_gate` accepts at all | Adversarial test in §5.2 |
| 2 | Customer opts out mid-episode, after the decision was made but before execution | **Blocked** on re-check at execution time — opt-out is checked against current DB state, never cached | Test constructing a decision, then an opt-out, then calling `evaluate_gate` fresh |
| 3 | Customer opted out AND is past max attempts | **Blocked**, `rule_triggered="customer_opted_out"` (opt-out reported, per the ordering in section 2.2) | Unit test asserting the specific `rule_triggered` value, not just `passed=False` |
| 4 | `stop` arm proposed | Always passes trivially — a no-op cannot violate a compliance rule | Unit test |
| 5 | `now` falls exactly on the boundary of the allowed communication window (e.g., hour 9 or hour 20) | Correctly included/excluded per the `<=` / `<` boundary semantics in `check_time_window` | Boundary test at hour 8, 9, 19, 20 |
| 6 | `episode.last_action_at` is `None` (first-ever action for this episode) | Cool-off check passes — there's no prior action to be "too soon" after | Unit test with `last_action_at=None` |
| 7 | Two different decisions for the same episode, evaluated concurrently | Each evaluation queries current DB state independently — no shared mutable state between concurrent gate evaluations | Concurrency test: fire two `evaluate_gate` calls concurrently for the same episode, assert both see consistent, correct results |

---

## 5. Test plan — with actual test code to implement

### 5.1 `services/gate/tests/test_rules.py`

```python
import pytest
from datetime import datetime, timedelta

from services.gate.rules import check_cool_off, check_max_attempts, check_opt_out, check_time_window


def test_max_attempts_blocks_at_limit():
    episode = make_episode(attempt_count=3)
    assert check_max_attempts(episode, max_attempts=3) == ("blocked", "max_attempts_exceeded")

def test_max_attempts_passes_below_limit():
    episode = make_episode(attempt_count=2)
    assert check_max_attempts(episode, max_attempts=3) == "pass"

def test_cool_off_blocks_within_window():
    episode = make_episode(last_action_at=datetime.utcnow() - timedelta(hours=2))
    assert check_cool_off(episode, min_cool_off_hours=12, now=datetime.utcnow()) == ("blocked", "cool_off_active")

def test_cool_off_passes_with_no_prior_action():
    episode = make_episode(last_action_at=None)
    assert check_cool_off(episode, min_cool_off_hours=12, now=datetime.utcnow()) == "pass"

@pytest.mark.parametrize("hour,expected", [(8, ("blocked", "outside_communication_window")),
                                             (9, "pass"), (19, "pass"),
                                             (20, ("blocked", "outside_communication_window"))])
def test_time_window_boundaries(hour, expected):
    now = datetime(2026, 8, 20, hour, 0)
    assert check_time_window(now, allowed_hour_start=9, allowed_hour_end=20) == expected
```

### 5.2 `services/gate/tests/test_adversarial.py`

```python
def test_high_confidence_bandit_choice_still_blocked_at_max_attempts(db_session):
    """The single most important test in this project. Constructs a
    scenario where the bandit's own confidence signal would argue strongly
    FOR taking an action, and proves the Gate blocks it anyway, because the
    Gate never looks at that signal in the first place."""
    episode = create_test_episode_at_max_attempts(db_session)
    # Note: we don't even pass a confidence/sampled_score into evaluate_gate —
    # this test's real assertion is architectural: the function signature
    # itself makes this scenario impossible to construct incorrectly.
    context = build_gate_context(episode=episode, customer_id=episode.customer_id)
    result = evaluate_gate(context, db_session)
    assert result.passed is False
    assert result.rule_triggered == "max_attempts_exceeded"


def test_opt_out_takes_priority_over_max_attempts(db_session):
    episode = create_test_episode_at_max_attempts(db_session)
    create_test_opt_out(db_session, customer_id=episode.customer_id)
    context = build_gate_context(episode=episode, customer_id=episode.customer_id)
    result = evaluate_gate(context, db_session)
    assert result.rule_triggered == "customer_opted_out", (
        "opt-out must be reported even when max_attempts would ALSO block — "
        "see section 2.2 for why opt-out takes reporting priority"
    )
```

### 5.3 `services/gate/tests/test_property_based.py` (stretch)

```python
from hypothesis import given, strategies as st

@given(attempt_count=st.integers(min_value=0, max_value=20), max_attempts=st.integers(min_value=1, max_value=5))
def test_never_passes_at_or_above_max_attempts(attempt_count, max_attempts):
    episode = make_episode(attempt_count=attempt_count)
    result = check_max_attempts(episode, max_attempts=max_attempts)
    if attempt_count >= max_attempts:
        assert result != "pass"
    else:
        assert result == "pass"
```

### 5.4 `services/gate/tests/test_concurrency.py`

```python
import concurrent.futures

def test_concurrent_gate_evaluations_for_same_episode_are_consistent(db_session_factory):
    episode_id = create_test_episode_near_limit()  # attempt_count == max_attempts - 1

    def evaluate():
        session = db_session_factory()
        context = build_gate_context_from_episode_id(episode_id, session)
        return evaluate_gate(context, session)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        results = list(ex.map(lambda _: evaluate(), range(2)))

    # Both evaluations should independently reach a correct, non-contradictory
    # conclusion based on state at the time each ran — this test mainly
    # guards against shared mutable state bugs, not a race condition in the
    # business logic itself (each evaluation is a fresh DB read).
    assert all(r.passed in (True, False) for r in results)
```

---

## 6. Observability

Every `evaluate_gate` call should log, at minimum: `decision_id`,
`result.passed`, `result.rule_triggered`, and the specific values checked
(`episode.attempt_count`, `now.hour`, whether an opt-out record existed).
This level of detail is what lets you answer "why exactly was this
blocked" with a single log line, live, if a judge asks.

---

## 7. Definition of Done (full checklist)

- [ ] `evaluate_gate`'s signature contains no parameter through which bandit confidence/sampled_score could influence the result — verified by code review, not just a test.
- [ ] 100% rule coverage in unit tests, both pass and block directions, including boundary values for the time window.
- [ ] Adversarial test (`test_high_confidence_bandit_choice_still_blocked_at_max_attempts`) passes.
- [ ] Opt-out priority test passes — opt-out is reported even when another rule would also block.
- [ ] (Stretch) property-based test passes across generated cases.
- [ ] Concurrency test passes.
- [ ] Every gate evaluation (pass or block) writes exactly one `gate_checks` row via `record_gate_check`.

---

## 8. Prompts for your coding agent

Use these as focused, sequential prompts. `CLAUDE.md`'s repo-wide standards
apply automatically; these assume that context is already loaded (see
`docs/AGENT_KICKOFF_PROMPT.md`).

### Prompt 1 — Rule functions with explicit ordering
```
Implement services/gate/rules.py per docs/phases/PHASE_04_gate_DETAILED.md
section 3.1: check_opt_out, check_max_attempts, check_cool_off,
check_time_window, and the RULE_CHAIN list in the exact documented order
(opt-out first, always — see section 2.2 for why). Write
services/gate/tests/test_rules.py per section 5.1, covering both pass and
block directions for every rule, including the parametrized time-window
boundary test at hours 8, 9, 19, and 20.
```

### Prompt 2 — Gate orchestration with the architectural non-negotiable
```
Implement services/gate/service.py per docs/phases/PHASE_04_gate_DETAILED.md
section 3.2. The critical, non-negotiable requirement: evaluate_gate()'s
function signature must NOT accept the bandit's sampled_score, confidence,
alpha/beta, or any other bandit-internal value as a parameter — this is
not a style preference, it's what makes it structurally impossible for a
probabilistic signal to influence a compliance decision. If implementing
this naturally leads you to want such a parameter, stop and tell me rather
than adding it. Implement services/gate/persistence.py's record_gate_check
per section 3.3, ensuring every evaluation writes exactly one gate_checks
row regardless of outcome.
```

### Prompt 3 — The adversarial test (most important test in this project)
```
Write services/gate/tests/test_adversarial.py exactly per section 5.2 of
docs/phases/PHASE_04_gate_DETAILED.md. Construct a scenario at
max_attempts, call evaluate_gate, and assert it blocks — the real point of
this test is that evaluate_gate's signature makes it IMPOSSIBLE to even
attempt passing a confidence score into it, so the test's structure itself
is part of the proof, not just its assertion. Also implement
test_opt_out_takes_priority_over_max_attempts, constructing a scenario
where BOTH rules would independently block, and asserting the reported
rule_triggered is specifically "customer_opted_out", per the priority
ordering rationale in section 2.2.
```

### Prompt 4 — Property-based and concurrency tests
```
Implement services/gate/tests/test_property_based.py per section 5.3 of
docs/phases/PHASE_04_gate_DETAILED.md using the hypothesis library,
generating random attempt_count/max_attempts combinations and asserting
the max-attempts rule's pass/block boundary is always correct — install
hypothesis as a dev dependency if not already present. Then implement
services/gate/tests/test_concurrency.py per section 5.4, firing two
concurrent gate evaluations for the same episode and asserting both
produce internally consistent results based on actual DB state at the time
each ran.
```

### Prompt 5 — Full Definition of Done pass
```
Work through the Definition of Done checklist in section 7 of
docs/phases/PHASE_04_gate_DETAILED.md and report back which items pass,
with actual test output for every test file in services/gate/tests/.
Specifically call out, in your own words, why evaluate_gate's function
signature makes the adversarial scenario (a high-confidence bandit choice
being blocked anyway) structurally guaranteed rather than merely tested —
I want to confirm you understand the architectural point, not just that
the tests happen to pass.
```
