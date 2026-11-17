import asyncio
from types import SimpleNamespace

from qq_deepseek.core.events import Message
from qq_deepseek.core.router import Router
from qq_deepseek.services.memory_service import MemoryService
from qq_deepseek.storage.memory_sqlite import SQLiteMemoryStore


class Chat:
    async def reply(self, *_): return "晚安，睡个好觉。"
    async def reset(self, *_): pass


def test_sleep_timer_overwrites_and_is_consumed_once(tmp_path, monkeypatch):
    store = SQLiteMemoryStore(tmp_path / "sleep.sqlite3")
    settings = SimpleNamespace(master_qq_id=10, proactive_groups=set(),
        proactive_probability=0, proactive_cooldown=1800)
    router = Router(Chat(), frozenset(), frozenset(), MemoryService(store, 10), settings=settings)
    now = [1000.0]
    monkeypatch.setattr("qq_deepseek.core.router.time.time", lambda: now[0])
    msg = lambda text: Message("group", 20, 30, 99, text, True)
    assert "晚安" in asyncio.run(router.handle(msg("晚安")))
    now[0] = 1600
    asyncio.run(router.handle(msg("晚安")))
    now[0] = 5200
    answer = asyncio.run(router.handle(msg("早安")))
    assert "1 小时 0 分钟" in answer
    assert store.finish_sleep(20, 5300) is None
    store.close()
