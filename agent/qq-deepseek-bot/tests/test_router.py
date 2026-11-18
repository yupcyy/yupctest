import asyncio
from qq_deepseek.core.events import parse_message
from qq_deepseek.core.router import Router
from qq_deepseek.services.chat import ChatService
from qq_deepseek.storage.memory import InMemoryHistory


class FakeProvider:
    def __init__(self):
        self.calls = []

    async def chat(self, messages):
        self.calls.append(messages)
        return "模拟回答"


def event(kind="group", at=True, text="你好", uid=2, gid=123):
    segments = ([{"type": "at", "data": {"qq": "1"}}] if at else []) + [
        {"type": "text", "data": {"text": text}}]
    obj = {"post_type": "message", "message_type": kind, "user_id": uid,
           "self_id": 1, "message": segments}
    if kind == "group":
        obj["group_id"] = gid
    return obj


def test_group_trigger_and_history():
    provider = FakeProvider()
    chat = ChatService(provider, InMemoryHistory(10), "system")
    router = Router(chat, frozenset(), frozenset())

    async def scenario():
        assert await router.handle(parse_message(event(at=False))) is None
        m = parse_message(event())
        answer = await router.handle(m)
        assert answer == "模拟回答"
        answer.delivered()
        answer = await router.handle(m)
        assert answer == "模拟回答"
        answer.delivered()
        assert len(provider.calls[1]) == 4
        assert await router.handle(parse_message(event(text="/reset"))) == "当前对话上下文已清空。"
        answer = await router.handle(m)
        assert answer == "模拟回答"
        answer.delivered()
        assert len(provider.calls[2]) == 2
    asyncio.run(scenario())


def test_private_and_separation():
    provider = FakeProvider()
    chat = ChatService(provider, InMemoryHistory(10), "system")
    router = Router(chat, frozenset(), frozenset())

    async def scenario():
        a = parse_message(event(kind="private", at=False, uid=2))
        b = parse_message(event(kind="private", at=False, uid=3))
        assert a.conversation_id != b.conversation_id
        assert await router.handle(a) == "模拟回答"
        assert await router.handle(b) == "模拟回答"
        assert len(provider.calls[1]) == 2
    asyncio.run(scenario())


def test_allowlist():
    provider = FakeProvider()
    chat = ChatService(provider, InMemoryHistory(10), "system")
    router = Router(chat, frozenset({3}), frozenset({123}))
    assert asyncio.run(router.handle(parse_message(event(uid=2)))) is None


def test_poke_uses_router_permissions():
    provider = FakeProvider()
    router = Router(ChatService(provider, InMemoryHistory(10), "system"),
                    frozenset({3}), frozenset({123}))
    denied = parse_message(event(uid=2))
    allowed = parse_message(event(uid=3))
    assert asyncio.run(router.handle_poke(denied)) is None
    assert asyncio.run(router.handle_poke(allowed)) == "模拟回答"
    assert len(provider.calls) == 1
    assert "戳了你一下" in provider.calls[0][-1]["content"]
