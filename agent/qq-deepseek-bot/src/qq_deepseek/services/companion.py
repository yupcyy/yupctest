from qq_deepseek.services.interaction_events import classify_interaction, EFFECTS
"""Independent, bounded short-term companion state; never stores message text."""
from collections import OrderedDict, deque
from dataclasses import dataclass
import math
import time


@dataclass
class Mood:
    value: float = 0.0
    updated: float = 0.0
    arousal: float = .3
    energy: float = .7


class Companion:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.moods = OrderedDict()
        self.activity = OrderedDict()

    def snapshot(self, scope):
        mood = self.moods.get(scope)
        return {"value": mood.value, "updated": mood.updated, "arousal": mood.arousal, "energy": mood.energy} if mood else None

    def restore(self, scope, payload):
        if not payload:
            return
        value, updated = float(payload["value"]), float(payload["updated"])
        if not math.isfinite(value) or not math.isfinite(updated):
            return
        arousal, energy = float(payload.get("arousal", .3)), float(payload.get("energy", .7))
        if not math.isfinite(arousal) or not math.isfinite(energy):
            return
        self.moods[scope] = Mood(max(-1, min(1, value)), updated,
                                 max(0, min(1, arousal)), max(0, min(1, energy)))
        while len(self.moods) > 512:
            key, _ = self.moods.popitem(last=False)
            self.activity.pop(key, None)

    def observe(self, scope, user_id, text):
        now = self.clock()
        mood = self.moods.pop(scope, Mood(updated=now))
        decay = math.exp(-max(0, now - mood.updated) / 21600)
        mood.value *= decay
        mood.arousal = .3 + (mood.arousal - .3) * decay
        mood.energy = .7 + (mood.energy - .7) * decay
        # One bounded event per message, rather than overlapping word matches.
        kind = classify_interaction(text)
        negative = kind in {"insult", "coercion"}
        delta = EFFECTS[kind][0] if kind else 0
        mood.value = max(-1, min(1, mood.value + delta))
        mood.arousal = max(0, min(1, mood.arousal + (.08 if kind else 0)))
        mood.energy = max(0, min(1, mood.energy - (.03 if negative else 0)))
        mood.updated = now
        self.moods[scope] = mood
        window = self.activity.pop(scope, deque(maxlen=100))
        window.append((now, user_id, negative))
        while window and now - window[0][0] > 600:
            window.popleft()
        self.activity[scope] = window
        while len(self.moods) > 512:
            key, _ = self.moods.popitem(last=False)
            self.activity.pop(key, None)
        return mood

    def atmosphere(self, scope):
        rows = [r for r in self.activity.get(scope, ()) if self.clock() - r[0] <= 600]
        if sum(r[2] for r in rows) >= 3:
            return "紧张"
        if len(rows) >= 15 and len({r[1] for r in rows}) >= 3:
            return "热闹"
        return "安静" if len(rows) < 3 else "平常"

    def hint(self, scope):
        mood = self.moods.get(scope)
        if not mood:
            return ""
        value = mood.value * math.exp(-max(0, self.clock() - mood.updated) / 21600)
        label = "开心温柔" if value > .25 else "有点委屈，克制表达" if value < -.25 else "平静友善"
        return f"当前心情：{label}。可以表达感受，不向对方施压索取陪伴。"
