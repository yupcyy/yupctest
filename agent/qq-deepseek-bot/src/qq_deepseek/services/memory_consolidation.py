"""Review-only, volatile candidate queue. No automatic long-term memory writes."""
from dataclasses import dataclass, replace
import math


@dataclass(frozen=True)
class CandidateMemory:
    candidate_id: str
    subject_user_id: int
    content: str
    source_kind: str
    source_event_ids: tuple[str, ...]
    confidence: float
    created_at: float
    expires_at: float
    status: str = 'pending'


class CandidateQueue:
    def __init__(self, capacity=20):
        self.capacity = capacity
        self.items = {}
        self.audit = []
        self.tombstones = set()

    def propose(self, candidate, *, sensitive=False):
        key = (candidate.subject_user_id, candidate.content.strip())
        if (candidate.source_kind not in {'private_confirmation', 'verified_event'}
                or sensitive or candidate.subject_user_id <= 0
                or not candidate.content.strip() or len(candidate.content) > 500
                or not candidate.source_event_ids or candidate.status != 'pending'
                or not .9 <= candidate.confidence <= 1
                or not all(math.isfinite(t) for t in (candidate.created_at, candidate.expires_at))
                or candidate.expires_at <= candidate.created_at
                or candidate.candidate_id in self.items or key in self.tombstones):
            return False
        if sum(c.subject_user_id == candidate.subject_user_id and c.status == 'pending'
               for c in self.items.values()) >= self.capacity:
            return False
        self.items[candidate.candidate_id] = candidate
        return True

    def review(self, candidate_id, *, user_id, action, now, private):
        candidate = self.items[candidate_id]
        if not private or user_id != candidate.subject_user_id:
            raise PermissionError('private subject confirmation required')
        if action not in {'approve', 'reject', 'delete'}:
            raise ValueError('unsupported review action')
        if action != 'delete' and (candidate.status != 'pending' or now >= candidate.expires_at):
            raise ValueError('candidate unavailable')
        status = {'approve': 'approved', 'reject': 'rejected', 'delete': 'deleted'}[action]
        if action in {'reject', 'delete'}:
            self.tombstones.add((user_id, candidate.content.strip()))
        self.items[candidate_id] = replace(candidate, status=status,
                                           content='' if action == 'delete' else candidate.content)
        self.audit.append((candidate_id, user_id, action, now))
        # Approval only returns a reviewed candidate; caller must explicitly
        # integrate with its private memory store. Dreams never reach this path.
        return self.items[candidate_id]

    def for_user(self, user_id):
        return tuple(c for c in self.items.values() if c.subject_user_id == user_id)
