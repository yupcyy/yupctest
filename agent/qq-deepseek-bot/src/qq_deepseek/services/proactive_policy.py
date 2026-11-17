"""Deterministic shared budget for unsolicited messages; no message text."""
from dataclasses import dataclass


@dataclass
class Budget:
    day: int = -1
    count: int = 0
    unanswered: int = 0
    next_at: float = 0


class ProactivePolicy:
    def __init__(self):
        self.targets = {}
        self.global_day = -1
        self.global_count = 0

    def answered(self, target):
        if target in self.targets:
            self.targets[target].unanswered = 0
            self.targets[target].next_at = 0

    def reserve(self, target, now, *, group=False):
        hour = int((now + 8 * 3600) // 3600 % 24)
        if not (hour >= 7 or hour < 2):
            return False
        day = int((now + 8 * 3600) // 86400)
        if self.global_day != day:
            self.global_day, self.global_count = day, 0
        if target not in self.targets and len(self.targets) >= 512:
            return False
        state = self.targets.setdefault(target, Budget())
        if state.day != day:
            state.day, state.count = day, 0
        if group:
            try:
                group_id = int(str(target).split(":", 1)[1])
            except (ValueError, IndexError):
                return False
            daily_cap = {1025309198: 120, 1077893032: 20}.get(group_id, 0)
        else:
            daily_cap = 3
        if daily_cap <= 0 or state.count >= daily_cap or now < state.next_at:
            return False
        state.count += 1
        state.unanswered += 1
        if group and state.unanswered >= 3:
            state.next_at = now + 1800
            state.unanswered = 0
        elif not group:
            state.next_at = now + 14400 * 2 ** (state.unanswered - 1)
        self.global_count += 1
        return True
