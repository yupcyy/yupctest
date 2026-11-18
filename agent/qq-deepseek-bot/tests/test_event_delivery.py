import asyncio
from dataclasses import replace
from types import SimpleNamespace
from qq_deepseek.core.events import Message, parse_message
from qq_deepseek.core.router import Router


def test_concurrent_duplicate_delivery_has_one_effect():
    class Chat:
        calls = 0
        async def reply(self, key, prompt):
            self.calls += 1
            await asyncio.sleep(0)
            return 'reply'
    async def scenario():
        chat = Chat()
        router = Router(chat, frozenset(), frozenset(), settings=SimpleNamespace(enable_companion=True, proactive_groups=set()))
        message = Message('private', 1, None, 99, '谢谢', False, event_id='123')
        answers = await asyncio.gather(router.handle(message), router.handle(message))
        assert answers.count('reply') == 1
        assert chat.calls == 1
        assert router.companion.snapshot('private:1')['value'] <= .12
        await router.handle(replace(message, user_id=2))
        assert chat.calls == 2
    asyncio.run(scenario())


def test_parser_preserves_transport_message_id():
    message = parse_message(dict(post_type='message', message_type='private', user_id=1,
                                 self_id=99, message='hello', message_id=123))
    assert message.event_id == '123'
