from unittest.mock import MagicMock
from services.act.nudge_generator import NudgeGenerator

def make_decision(arm):
    decision = MagicMock()
    decision.chosen_arm = arm
    return decision

def test_llm_exception_falls_back_to_template():
    failing_llm = MagicMock()
    failing_llm.complete.side_effect = Exception("LLM is down")
    generator = NudgeGenerator(llm_client=failing_llm)

    result = generator.generate(make_decision("send_nudge_hinglish"), language="send_nudge_hinglish")

    assert result.method == "template_fallback"
    assert "[payment_link]" in result.text or "{link}" not in result.text

def test_llm_timeout_falls_back_to_template():
    failing_llm = MagicMock()
    failing_llm.complete.side_effect = TimeoutError("llm too slow")
    generator = NudgeGenerator(llm_client=failing_llm)

    result = generator.generate(make_decision("send_nudge_english"), language="send_nudge_english")

    assert result.method == "template_fallback"
    assert "[payment_link]" in result.text or "{link}" not in result.text

def test_llm_success_returns_generated_text():
    success_llm = MagicMock()
    success_llm.complete.return_value = "Here is your generated message with [payment_link]."
    generator = NudgeGenerator(llm_client=success_llm)

    result = generator.generate(make_decision("send_nudge_english"), language="send_nudge_english")

    assert result.method == "llm_generated"
    assert result.text == "Here is your generated message with [payment_link]."
