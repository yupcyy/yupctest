import asyncio
from qq_deepseek.services.affinity import AffinityService


class Store:
    value = 0
    def ensure_affinity(self, user_id, default):
        return self.value
    def adjust_affinity(self, user_id, delta, default):
        self.value += delta
        return self.value


def test_concurrent_positive_keywords_are_bounded(monkeypatch):
    async def inline(func, *args):
        return func(*args)
    monkeypatch.setattr(asyncio, 'to_thread', inline)
    async def run():
        store = Store()
        service = AffinityService(store, 0)
        await asyncio.gather(*(service.adjust_for_message(1, '谢谢') for _ in range(50)))
        assert store.value == 2
        await asyncio.gather(*(service.social_gesture(1, '抱抱') for _ in range(50)))
        assert store.value == 5
    asyncio.run(run())


def test_negative_event_takes_priority_without_mood_mapping(monkeypatch):
    async def inline(func, *args):
        return func(*args)
    monkeypatch.setattr(asyncio, 'to_thread', inline)
    async def run():
        store = Store()
        service = AffinityService(store, 0)
        assert await service.adjust_for_message(1, '谢谢，废物') == -3
        assert await service.adjust_for_message(2, '谢谢') == -1
    asyncio.run(run())
