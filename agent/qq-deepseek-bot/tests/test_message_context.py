import asyncio

from qq_deepseek.adapters.onebot_ws import OneBotWS


class Router: pass


def test_poke_target_filter_and_cooldown(monkeypatch):
    class PokeRouter:
        def __init__(self): self.calls = 0
        async def handle_poke(self, message):
            self.calls += 1
            return "戳到啦"
    router = PokeRouter()
    adapter = OneBotWS("ws://test", "", router, 1000, 1)
    sent = []
    async def send(ws, message, content): sent.append((message, content))
    monkeypatch.setattr(adapter, "_send", send)
    async def run():
        base = {"post_type":"notice", "notice_type":"notify", "sub_type":"poke",
                "user_id":2, "self_id":1, "group_id":123}
        await adapter._process_poke(None, {**base, "target_id":9})
        await adapter._process_poke(None, {**base, "target_id":1})
        await adapter._process_poke(None, {**base, "target_id":1})
    asyncio.run(run())
    assert router.calls == 1
    assert len(sent) == 1 and sent[0][0].group_id == 123


def test_reply_and_image_ocr_context(monkeypatch):
    adapter = OneBotWS("ws://test", "", Router(), 1000, 1)
    async def action(ws, name, params):
        if name == "get_msg":
            return {"sender":{"nickname":"小明"}, "message":[{"type":"text","data":{"text":"原消息"}}]}
        return {"texts":[{"text":"图片文字"}]}
    monkeypatch.setattr(adapter, "_action", action)
    event={"message":[
        {"type":"reply","data":{"id":"1"}},
        {"type":"image","data":{"file":"abc.jpg"}},
    ]}
    context=asyncio.run(adapter._extract_context(None,event))
    assert "引用 小明 的消息：原消息" in context
    assert "图片1 OCR文字：图片文字" in context
