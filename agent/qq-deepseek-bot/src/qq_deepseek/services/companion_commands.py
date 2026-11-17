"""Owner-only private companion management using the approved SQLite tables."""
import asyncio
import time


class CompanionCommands:
    def __init__(self, store, lock, owner, chat):
        self.store, self.lock, self.owner, self.chat = store, lock, owner, chat
        self.generation_lock = asyncio.Lock()

    async def call(self, method, *args):
        def run():
            with self.lock:
                return getattr(self.store, method)(*args)
        return await asyncio.to_thread(run)

    async def command(self, message, text):
        if not text.startswith(("/梦境", "/日记", "/画像", "/拟人")):
            return None
        if message.kind != "private" or message.user_id != self.owner:
            return "这些内容仅允许主人私聊查看和管理。"
        name, _, arg = text.partition(" ")
        if name == "/画像":
            key = f"profile:{self.owner}"
            if arg:
                if len(arg) > 500:
                    return "画像请控制在500字以内。"
                await self.call("save", key, {"note": arg}, time.time())
                return "已保存主人画像，仅用于私聊。"
            return (await self.call("load", key) or {}).get("note", "尚未设置画像；/画像 内容")
        if name == "/拟人":
            if arg in {"停止", "恢复", "睡觉", "醒来"}:
                state = await self.call("load", "control") or {}
                state["stopped" if arg in {"停止", "恢复"} else "asleep"] = arg in {"停止", "睡觉"}
                await self.call("save", "control", state, time.time())
                return "已更新拟人状态。"
            return str(await self.call("load", "control") or {"stopped": False, "asleep": False})
        if arg != "生成":
            rows = await self.call("journal", self.owner)
            kind = "dream" if name == "/梦境" else "diary"
            return "\n\n".join(content for k, content, _ in rows if k == kind) or f"暂无记录；{name} 生成"
        if self.generation_lock.locked():
            return "正在写一份，请稍等。"
        async with self.generation_lock:
            key = f"journal_limit:{self.owner}"
            previous = await self.call("load", key) or {}
            if time.time() - previous.get(name, 0) < 3600:
                return "这种记录每小时最多生成一次。"
            generate = getattr(self.chat, "proactive_reply", None)
            if generate is None:
                return "当前聊天服务未提供无工具生成通道。"
            prompt = ("写一段明确标注为虚构的梦境，不把用户隐私或梦境当作真实经历。"
                      if name == "/梦境" else
                      "写一段本鱼当下心情的日记，不编造用户发生过的事情，不引用私聊原话。")
            content = await generate(f"private:{self.owner}", prompt + "保持当前人格，温和乖巧，限200字，不调用工具。")
            content = ("【虚构梦境】" if name == "/梦境" else "【心情日记】") + str(content)[:1800]
            await self.call("append_journal", self.owner, "dream" if name == "/梦境" else "diary", content, time.time())
            previous[name] = time.time()
            await self.call("save", key, previous, time.time())
            return content
