from qq_deepseek.services.runtime_context import ReplyRequest
"""Owner-only private companion management using the approved SQLite tables."""
import asyncio
import time


class CompanionCommands:
    def __init__(self, store, lock, owner, chat, *, enable_self_profile=False):
        self.store, self.lock, self.owner, self.chat = store, lock, owner, chat
        self.generation_lock = asyncio.Lock()
        self.enable_self_profile = enable_self_profile

    async def call(self, method, *args):
        def run():
            with self.lock:
                return getattr(self.store, method)(*args)
        return await asyncio.to_thread(run)

    async def command(self, message, text):
        if not text.startswith(("/梦境", "/日记", "/画像", "/拟人")):
            return None
        name, _, arg = text.partition(" ")
        if name == "/画像":
            if message.kind != "private":
                return "画像仅允许私聊查看和管理。"
            is_owner = message.user_id == self.owner
            if not is_owner and not self.enable_self_profile:
                return "用户自设画像未开启，当前仅允许主人补充。"
            target = message.user_id
            content = arg.strip()
            action = "补充"
            if is_owner and content:
                parts = content.split(maxsplit=1)
                if parts[0].isdigit():
                    target = int(parts[0])
                    if target <= 0:
                        return "用户QQ号必须为正整数。"
                    content = parts[1] if len(parts) > 1 else ""
                if content.startswith("补充 "):
                    content = content[3:].strip()
                elif content.startswith("设置 "):
                    action, content = "设置", content[3:].strip()
            key = f"profile:{target}"
            profile = await self.call("load", key) or {}
            if not content:
                return profile.get("note", "尚未设置画像。主人用 /画像 QQ号 补充 内容；/画像 QQ号 设置 内容 可替换。")
            note = content if action == "设置" else "\n".join(filter(None, (profile.get("note", ""), content)))
            if len(note) > 500:
                return "画像总长度请控制在500字以内。"
            await self.call("save", key, {"note": note, "subject_user_id": target,
                "updated_by": message.user_id, "scope": "group"}, time.time())
            return f"已保存用户 {target} 的群聊画像，用于群内回复该用户。"
        if message.kind != "private" or message.user_id != self.owner:
            return "这些内容仅允许主人私聊查看和管理。"
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
            control = await self.call("load", "control") or {}
            if control.get("stopped"):
                return "拟人功能已停止，请先恢复。"
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
            content = await generate(f"private:{self.owner}", ReplyRequest(prompt + "保持当前人格，温和乖巧，限200字，不调用工具。", ephemeral=True, isolated=True))
            # Stop can arrive while the model is generating. Discard its output
            # rather than archiving after the owner's emergency stop.
            if (await self.call("load", "control") or {}).get("stopped"):
                return "拟人功能已停止，已取消归档。"
            content = ("【虚构梦境】" if name == "/梦境" else "【心情日记】") + str(content)[:1800]
            await self.call("append_journal", self.owner, "dream" if name == "/梦境" else "diary", content, time.time())
            previous[name] = time.time()
            await self.call("save", key, previous, time.time())
            return content
