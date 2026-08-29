import concurrent.futures
import uuid
from packages.db_models.models.episode import Episode
from services.gate.service import evaluate_gate, GateContext
from unittest.mock import MagicMock

def test_concurrent_gate_evaluations_for_same_episode_are_consistent():
    episode = Episode(
        episode_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        merchant_id=uuid.uuid4()
    )
    episode.attempt_count = 2 # max_attempts=3

    def evaluate():
        db_session = MagicMock()
        db_session.query.return_value.filter_by.return_value.first.return_value = None
        context = GateContext(decision_id=str(uuid.uuid4()), episode=episode, customer_id=episode.customer_id)
        return evaluate_gate(context, db_session)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        results = list(ex.map(lambda _: evaluate(), range(2)))

    assert all(r.passed in (True, False) for r in results)
