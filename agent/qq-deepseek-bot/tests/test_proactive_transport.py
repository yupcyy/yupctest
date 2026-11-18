import asyncio
from types import SimpleNamespace
from qq_deepseek.adapters.onebot_ws import OneBotWS
from qq_deepseek.services.proactive_decision import ProactiveReply
from qq_deepseek.services.proactive_policy import ProactivePolicy


def test_group_send_feedback_tracks_success_and_failure():
    async def run(fail):
        policy = ProactivePolicy()
        target = 'group:1077893032'
        assert policy.reserve(target, 3600, group=True)
        class Router:
            proactive_policy = policy
            async def handle(self, message):
                return ProactiveReply('hello', target)
            def next_owner_alert(self):
                return None
        adapter = OneBotWS('', '', Router(), 1000, 1)
        async def send(*args):
            if fail:
                raise RuntimeError('offline failure')
        adapter._send = send
        await adapter._process(None, dict(post_type='message', message_type='group',
                                        user_id=1, self_id=99, group_id=1077893032,
                                        message='hello', message_id=1))
        assert policy.targets[target].failures == int(fail)
    asyncio.run(run(False))
    asyncio.run(run(True))


def test_same_conversation_waits_for_delivery_before_next_generation():
    from qq_deepseek.core.router import Router
    from qq_deepseek.services.chat import ChatService
    from qq_deepseek.storage.memory import InMemoryHistory
    async def run():
        generated = []
        class Provider:
            async def chat(self, messages):
                generated.append(messages)
                return 'reply'
        history = InMemoryHistory(10)
        router = Router(ChatService(Provider(), history, 'system'), frozenset(), frozenset())
        adapter = OneBotWS('', '', router, 1000, 2)
        sending = asyncio.Event()
        release = asyncio.Event()
        async def context(*args):
            return ''
        async def send(*args):
            if not sending.is_set():
                sending.set()
                await release.wait()
        adapter._extract_context = context
        adapter._send = send
        event = dict(post_type='message', message_type='private', user_id=1,
                     self_id=99, message='hello', message_id=1)
        first = asyncio.create_task(adapter._process(None, event))
        await sending.wait()
        second = asyncio.create_task(adapter._process(None, dict(event, message_id=2)))
        await asyncio.sleep(0)
        assert len(generated) == 1
        release.set()
        await asyncio.gather(first, second)
        assert len(generated[1]) == 4
        assert len(history.get('private:1')) == 4
    asyncio.run(run())
