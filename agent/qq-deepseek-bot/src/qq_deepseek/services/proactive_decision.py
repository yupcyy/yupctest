"""Pure server-side eligibility; dynamic influence is opt-in and bounded."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ProactiveDecision:
    eligible: bool
    priority: float
    reason: str
    suggested_topic: str = '轻松分享，不索取回应'
    cooldown_multiplier: float = 1.0


def decide_proactive(*, hour, mood=0., energy=1., affinity=0., unanswered=0,
                     stopped=False, asleep=False, dnd=False, enabled=True, all_day=False,
                     failures=0, dynamic=False):
    for blocked, reason in ((not enabled, 'disabled'), (stopped, 'stopped'),
                            (asleep, 'asleep'), (dnd, 'dnd'),
                            (not all_day and not 9 <= hour < 23, 'quiet_hours'),
                            (failures >= 3, 'send_failures'),
                            (unanswered >= 3, 'unanswered')):
        if blocked:
            return ProactiveDecision(False, 0., reason)
    clamp = lambda value, low, high: max(low, min(high, value))
    multiplier = 1.
    if dynamic:
        multiplier = ((1 - .2 * clamp(mood, -1, 1)) *
                      (1 - .2 * clamp(affinity / 100, -1, 1)))
    return ProactiveDecision(True, clamp(energy, 0, 1) / (1 + unanswered),
                             'eligible', cooldown_multiplier=multiplier)


class ProactiveReply(str):
    """Carries a server-owned budget target through the transport boundary."""
    def __new__(cls, content, target):
        obj = super().__new__(cls, content)
        obj.target = target
        return obj
