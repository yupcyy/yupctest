from qq_deepseek.storage.memory_sqlite import SQLiteMemoryStore


def test_group_context_is_bounded_isolated_and_survives_restart(tmp_path):
    path = tmp_path / 'memory.sqlite3'
    store = SQLiteMemoryStore(path)
    for i in range(60):
        store.observe(100, i, f'message-{i}')
    store.observe(200, 1, 'other group secret')
    context = store.group_context(100)
    assert len(context.splitlines()) == 20
    assert 'message-59' in context
    assert 'message-39' not in context
    assert 'other group' not in context
    assert store.reserve_proactive(100, 1000, 1800)
    assert not store.reserve_proactive(100, 1001, 1800)
    store.close()
    store = SQLiteMemoryStore(path)
    assert not store.reserve_proactive(100, 1100, 1800)
    assert store.reserve_proactive(100, 2800, 1800)
    assert store.reserve_proactive(200, 1100, 1800)
    assert 'message-59' in store.group_context(100)
    store.close()


def test_proactive_reply_obeys_permissions_and_three_unanswered_cooldown(tmp_path, monkeypatch):
    monkeypatch.setattr("qq_deepseek.core.router.time.time", lambda: 3600)
    import asyncio
    from types import SimpleNamespace
    from qq_deepseek.core.events import Message
    from qq_deepseek.core.router import Router
    from qq_deepseek.services.memory_service import MemoryService

    class Chat:
        def __init__(self):
            self.calls = []
        async def reply(self, *args):
            raise AssertionError('Proactive reply must use the no-tools entry point')
        async def proactive_reply(self, *args):
            self.calls.append(args)
            return '本鱼冒泡'

    async def scenario():
        store = SQLiteMemoryStore(tmp_path / 'group.sqlite3')
        chat = Chat()
        group_id = 1025309198
        settings = SimpleNamespace(proactive_groups={group_id}, proactive_probability=1,
                                   proactive_cooldown=1800)
        router = Router(chat, frozenset({20}), frozenset({group_id}),
                        MemoryService(store, 10), settings=settings)
        try:
            denied = Message('group', 30, group_id, 999, '未授权', False)
            assert await router.handle(denied) is None
            assert store.group_context(group_id) == ''
            message = Message('group', 20, group_id, 999, '今天吃什么', False)
            assert await router.handle(message) == '本鱼冒泡'
            assert await router.handle(message) == '本鱼冒泡'
            assert await router.handle(message) == '本鱼冒泡'
            assert await router.handle(message) is None
            assert len(chat.calls) == 3
            # Group messages may trigger a reply, but are never persisted for learning.
            assert store.group_context(group_id) == ''
        finally:
            store.close()
    asyncio.run(scenario())
