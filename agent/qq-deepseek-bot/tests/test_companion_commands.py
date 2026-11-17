import asyncio
import sqlite3
import threading

from qq_deepseek.core.events import Message
from qq_deepseek.services.companion_commands import CompanionCommands
from qq_deepseek.storage.companion import CompanionStore, SCHEMA


def test_private_commands_and_generation(tmp_path):
    db = sqlite3.connect(tmp_path / "test.sqlite", check_same_thread=False)
    db.executescript(SCHEMA)
    class Chat:
        async def proactive_reply(self, scope, prompt):
            assert scope == "private:1"
            return "本鱼在云朵池塘里游泳。"
    service = CompanionCommands(CompanionStore(db), threading.RLock(), 1, Chat())
    async def run():
        async def ask(text, kind="private", uid=1):
            return await service.command(Message(kind, uid, 2 if kind == "group" else None, 9, text, True), text)
        assert "仅允许" in await ask("/日记", "group")
        assert "仅允许" in await ask("/画像 私密", uid=2)
        assert "已保存" in await ask("/画像 喜欢小鱼")
        assert await ask("/画像") == "喜欢小鱼"
        assert "虚构梦境" in await ask("/梦境 生成")
        assert "每小时" in await ask("/梦境 生成")
        assert "云朵" in await ask("/梦境")
        await ask("/拟人 停止")
        assert (await service.call("load", "control"))["stopped"]
    try:
        asyncio.run(run())
    finally:
        db.close()
