import asyncio
from qq_deepseek.services.chat import ChatService
from qq_deepseek.services.runtime_context import ReplyRequest, clean_legacy_history
from qq_deepseek.storage.memory import InMemoryHistory

def test_runtime_and_ephemeral():
    asyncio.run(_runtime_and_ephemeral())

async def _runtime_and_ephemeral():
    class Provider:
        calls = []
        async def chat(self, messages):
            self.calls.append(messages)
            return 'reply'
    p = Provider()
    h = InMemoryHistory(10)
    c = ChatService(p, h, 'system')
    await c.reply('private:1', ReplyRequest('hello', runtime_context='happy'))
    await c.reply('private:1', ReplyRequest('again', runtime_context='sad'))
    assert 'sad' in p.calls[-1][0]['content']
    assert 'happy' not in str(p.calls[-1])
    assert [m['content'] for m in h.get('private:1')] == ['hello', 'reply', 'again', 'reply']
    await c.proactive_reply('private:1', 'diary')
    assert len(h.get('private:1')) == 4

def test_cleanup():
    h = InMemoryHistory(10)
    h.append_exchange('a', '【内部关系提示：old】', 'reply')
    h.append_exchange('b', 'hello', 'reply')
    clean_legacy_history(h, 'a')
    assert not h.get('a')
    assert len(h.get('b')) == 2


def test_isolated_generation_excludes_private_history_and_memory():
    async def scenario():
        class Memory:
            async def context_for(self, key):
                raise AssertionError('isolated generation must not read private facts')
        class Provider:
            async def chat(self, messages):
                assert 'private secret' not in str(messages)
                return 'fiction'
        h = InMemoryHistory(10)
        h.append_exchange('private:1', 'private secret', 'reply')
        service = ChatService(Provider(), h, 'system', Memory())
        await service.proactive_reply('private:1', ReplyRequest('dream', isolated=True))
        assert len(h.get('private:1')) == 2
    asyncio.run(scenario())


def test_deferred_commit_and_context_refresh_under_lock():
    async def run():
        state = {'mood': 'happy'}
        class Provider:
            async def chat(self, messages):
                assert state['mood'] in messages[0]['content']
                return 'answer'
        async def latest():
            return state['mood']
        h = InMemoryHistory(10)
        service = ChatService(Provider(), h, 'system')
        req = ReplyRequest('hello', context_factory=latest, defer_history=True)
        state['mood'] = 'sad'
        answer = await service.reply('private:1', req)
        assert not h.get('private:1')
        answer.delivered()
        answer.delivered()
        assert len(h.get('private:1')) == 2
    asyncio.run(run())


def test_reset_invalidates_pending_transport_commit():
    from qq_deepseek.services.runtime_context import PendingReply
    h = InMemoryHistory(10)
    pending = PendingReply('answer', h, 'private:1', 'hello', 'answer')
    h.clear('private:1')
    pending.with_content('[[voice]]answer').delivered()
    assert h.get('private:1') == []


def test_legacy_persistent_history_is_never_automatically_deleted():
    from qq_deepseek.services.runtime_context import PendingReply
    class LegacyHistory:
        def get(self, key):
            return [{'role': 'user', 'content': '【内部关系提示：old】'}]
        def clear(self, key):
            raise AssertionError('durable history must not be deleted')
        def append_exchange(self, *args):
            self.saved = args
    history = LegacyHistory()
    clean_legacy_history(history, 'private:1')
    PendingReply('reply', history, 'private:1', 'hello', 'reply').delivered()
    assert history.saved == ('private:1', 'hello', 'reply')


def test_system_china_time_refreshes_on_each_request(monkeypatch):
    import datetime
    from qq_deepseek.services.runtime_context import resolve_context
    times = iter([datetime.datetime(2026, 11, 18, 0, 1), datetime.datetime(2026, 11, 18, 0, 2)])
    class Clock(datetime.datetime):
        @classmethod
        def now(cls, tz):
            assert str(tz) == 'Asia/Shanghai'
            return next(times).replace(tzinfo=tz)
    monkeypatch.setattr(datetime, 'datetime', Clock)
    async def run():
        request = ReplyRequest('hello', runtime_context='context')
        first = await resolve_context(request)
        second = await resolve_context(request)
        assert '00:01:00+08:00' in first
        assert '00:02:00+08:00' in second
        assert 'context' in second
    asyncio.run(run())
