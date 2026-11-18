"""Validated text-free interaction records and independent bounded effects.

This in-memory reducer is intentionally separate from durable store operations.
"""
from dataclasses import dataclass
import math

EFFECTS = {'gratitude': (.12, 1), 'comfort': (.15, 1), 'gift': (.12, 1),
           'insult': (-.18, -2), 'coercion': (-.2, -3), 'apology': (.05, 0)}


@dataclass(frozen=True)
class InteractionEvent:
    event_id: str
    timestamp: float
    kind: str
    scope: str
    actor_id: int
    source: str = 'deterministic'
    confidence: float = 1.0
    evidence_reference: str = ''
    dedupe_key: str = ''


class InteractionReducer:
    def __init__(self):
        self.seen = set()
        self.daily = {}
        self.moods = {}
        self.relationships = {}

    def apply(self, event):
        key = event.dedupe_key or event.event_id
        if (not key or event.kind not in EFFECTS or event.actor_id <= 0
                or not event.scope.startswith(('private:', 'group:'))
                or event.source != 'deterministic'
                or not math.isfinite(event.timestamp)
                or not .8 <= event.confidence <= 1 or key in self.seen):
            return False
        day = int(event.timestamp // 86400)
        quota = (day, event.actor_id)
        if self.daily.get(quota, 0) >= 10 or len(self.seen) >= 10000:
            return False
        self.seen.add(key)
        self.daily[quota] = self.daily.get(quota, 0) + 1
        mood_delta, relation_delta = EFFECTS[event.kind]
        value, updated = self.moods.get(event.scope, (0., event.timestamp))
        value *= math.exp(-max(0, event.timestamp - updated) / 21600)
        self.moods[event.scope] = (max(-1., min(1., value + mood_delta)), max(updated, event.timestamp))
        score = self.relationships.get(event.actor_id, 0)
        self.relationships[event.actor_id] = max(-100, min(100, score + relation_delta))
        return True


def classify_interaction(text):
    """Single deterministic classification; no text is retained in the record."""
    from qq_deepseek.services.affinity import COMFORT_RE, NEGATIVE_RE, POSITIVE_RE, COERCION_RE, GIFTS
    if COERCION_RE.search(text):
        return 'coercion'
    if NEGATIVE_RE.search(text):
        return 'insult'
    if any(word in text for word in ('送给你', '送你', '给你', '请你吃')) and any(name in text for name, _ in GIFTS):
        return 'gift'
    if COMFORT_RE.search(text):
        return 'comfort'
    if POSITIVE_RE.search(text):
        return 'gratitude'
    return None
