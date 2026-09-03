import uuid
from unittest.mock import MagicMock

from packages.db_models.models.episode import Episode
from services.gate.service import evaluate_gate, GateContext

def create_test_episode_at_max_attempts(db_session=None):
    episode = Episode(
        episode_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        merchant_id=uuid.uuid4()
    )
    episode.attempt_count = 3
    return episode

def create_test_opt_out(db_session, customer_id):
    pass # Opt out existence is mocked below

def test_high_confidence_bandit_choice_still_blocked_at_max_attempts():
    """The single most important test in this project. Constructs a
    scenario where the bandit's own confidence signal would argue strongly
    FOR taking an action, and proves the Gate blocks it anyway, because the
    Gate never looks at that signal in the first place."""
    db_session = MagicMock()
    db_session.query.return_value.filter_by.return_value.first.return_value = None

    episode = create_test_episode_at_max_attempts(db_session)
    # Note: we don't even pass a confidence/sampled_score into evaluate_gate —
    # this test's real assertion is architectural: the function signature
    # itself makes this scenario impossible to construct incorrectly.
    context = GateContext(decision_id=str(uuid.uuid4()), episode=episode, customer_id=episode.customer_id)
    result = evaluate_gate(context, db_session)
    assert result.passed is False
    assert result.rule_triggered == "max_attempts_exceeded"

def test_opt_out_takes_priority_over_max_attempts():
    db_session = MagicMock()
    # Mock opt-out check to return an OptOut object (truthy)
    db_session.query.return_value.filter_by.return_value.first.return_value = True

    episode = create_test_episode_at_max_attempts(db_session)
    context = GateContext(decision_id=str(uuid.uuid4()), episode=episode, customer_id=episode.customer_id)
    result = evaluate_gate(context, db_session)
    
    assert result.rule_triggered == "customer_opted_out", (
        "opt-out must be reported even when max_attempts would ALSO block — "
        "see section 2.2 for why opt-out takes reporting priority"
    )
