"""Group-scoped identity resolution from OneBot member metadata only."""
from collections import OrderedDict, deque
import re


class GroupIdentity:
    def __init__(self):
        self.groups = OrderedDict()
        self.recent = {}

    def observe(self, group_id, user_id, sender, text):
        members = self.groups.setdefault(group_id, OrderedDict())
        names = {str(sender.get(k, '')).strip()[:64] for k in ('nickname', 'card')}
        members[user_id] = names - {''}
        members.move_to_end(user_id)
        while len(members) > 2000:
            members.popitem(last=False)
        self.groups.move_to_end(group_id)
        self.recent.setdefault(group_id, deque(maxlen=12)).append((user_id, text[:200]))
        while len(self.groups) > 128:
            old, _ = self.groups.popitem(last=False)
            self.recent.pop(old, None)

    def resolve(self, group_id, text):
        matches = {}
        for uid, names in self.groups.get(group_id, {}).items():
            for name in names:
                if len(name) >= 2 and re.search(r'(?<![A-Za-z0-9])' + re.escape(name) + r'(?![A-Za-z0-9])', text):
                    matches.setdefault(name, set()).add(uid)
        ids = tuple(dict.fromkeys(next(iter(ids)) for ids in matches.values() if len(ids) == 1))[:5]
        ambiguous = tuple(name for name, ids in matches.items() if len(ids) > 1)
        return ids, ambiguous

    def context(self, group_id):
        members = self.groups.get(group_id, {})
        return '\n'.join(f'QQ={uid} 称呼={"/".join(sorted(members.get(uid, ())))} 发言={text}'
                         for uid, text in self.recent.get(group_id, ()))[:3000]
