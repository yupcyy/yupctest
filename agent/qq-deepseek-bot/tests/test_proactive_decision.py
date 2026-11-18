from qq_deepseek.services.proactive_decision import decide_proactive
from qq_deepseek.services.proactive_policy import ProactivePolicy


def test_hard_guards_override_dynamic_influence():
    for flag in ('stopped', 'asleep', 'dnd'):
        assert not decide_proactive(hour=12, mood=1, affinity=100, dynamic=True, **{flag: True}).eligible
    assert not decide_proactive(hour=12, unanswered=3).eligible
    assert not decide_proactive(hour=12, failures=3).eligible
    assert not decide_proactive(hour=2).eligible


def test_independent_bounded_modulation():
    base = decide_proactive(hour=12)
    assert base == decide_proactive(hour=12, mood=1, affinity=100)
    assert .8 == decide_proactive(hour=12, mood=1, dynamic=True).cooldown_multiplier
    assert .8 == decide_proactive(hour=12, affinity=100, dynamic=True).cooldown_multiplier


def test_budget_stops_until_response_and_failure_circuit():
    policy = ProactivePolicy()
    # Noon UTC, within local permitted hours, different days preserve unanswered.
    for day in range(3):
        assert policy.reserve('private:1', day * 86400 + 43200)
    assert policy.reserve('private:1', 4 * 86400 + 43200)
    policy.answered('private:1')
    assert policy.reserve('private:1', 5 * 86400 + 43200)
    for _ in range(3):
        policy.record_send('private:1', False)
    assert not policy.reserve('private:1', 5 * 86400 + 43200)
