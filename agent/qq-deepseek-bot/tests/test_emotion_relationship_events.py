from dataclasses import replace
from qq_deepseek.services.interaction_events import InteractionEvent, InteractionReducer


def test_independent_scopes_and_idempotency():
    engine = InteractionReducer()
    event = InteractionEvent('1', 100, 'gift', 'group:3', 10)
    assert engine.apply(event)
    assert not engine.apply(event)
    assert engine.relationships == {10: 1}
    assert 'private:10' not in engine.moods
    mood = engine.moods.copy()
    engine.relationships[10] = -100
    assert engine.moods == mood
    assert not engine.apply(replace(event, event_id='2', confidence=.1))


def test_daily_cap():
    engine = InteractionReducer()
    for i in range(20):
        engine.apply(InteractionEvent(str(i), 100, 'comfort', 'private:10', 10))
    assert engine.relationships[10] == 10
    assert engine.moods['private:10'][0] <= 1
