from collections import deque


class InMemoryHistory:
    """Volatile chat history; replace with SQLite/Redis later."""
    def __init__(self, max_turns: int):
        self._store: dict[str, deque[dict[str, str]]] = {}
        self._max_items = 2 * max_turns

    def get(self, key: str) -> list[dict[str, str]]:
        return list(self._store.get(key, ()))

    def append_exchange(self, key: str, user: str, assistant: str) -> None:
        bucket = self._store.setdefault(key, deque(maxlen=self._max_items))
        bucket.append({"role": "user", "content": user})
        bucket.append({"role": "assistant", "content": assistant})

    def clear(self, key: str) -> None:
        self._store.pop(key, None)
