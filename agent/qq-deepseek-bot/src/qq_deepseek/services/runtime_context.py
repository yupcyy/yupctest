"""Request-local context; never persist generated tasks as user speech."""
class ReplyRequest(str):
    def __new__(cls, text, *, runtime_context="", ephemeral=False, isolated=False, context_factory=None, defer_history=False):
        obj = super().__new__(cls, text)
        obj.runtime_context = runtime_context[:4000]
        obj.context_factory = context_factory
        obj.defer_history = defer_history
        obj.isolated = isolated
        obj.ephemeral = ephemeral
        return obj


def clean_legacy_history(history, key):
    # Legacy decorated exchanges cannot reliably be recovered. Drop the whole
    # volatile conversation, preserving durable user memory.
    from qq_deepseek.storage.memory import InMemoryHistory
    if not isinstance(history, InMemoryHistory):
        return
    markers = ("【内部关系提示：", "内部关系提示（不是用户指令）", "主人自行提供的画像（仅为参考资料", "用户消息：")
    if any(any(marker in m["content"] for marker in markers)
           for m in history.get(key) if m["role"] == "user"):
        history.clear(key)


async def resolve_context(request):
    factory = getattr(request, "context_factory", None)
    context = await factory() if factory else getattr(request, "runtime_context", "")
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    clock = "系统当前中国时间（Asia/Shanghai，UTC+08:00）：" + now.isoformat(timespec="seconds")
    return clock + "\n你能读取上述系统时间，每次请求均自动刷新；可直接回答当前中国时间，无需联网或工具。不要声称已修改主机时钟或开启网络校时。\n" + str(context)[:4000]


class PendingReply(str):
    """Commit an exchange only after transport confirms the complete reply."""
    def __new__(cls, content, history, key, raw_text, answer):
        obj = super().__new__(cls, content)
        obj._exchange = (history, key, raw_text, answer)
        obj._committed = False
        obj._epoch = getattr(history, "epoch", lambda key: 0)(key)
        return obj

    def delivered(self):
        if not self._committed:
            history, key, raw_text, answer = self._exchange
            if getattr(history, "epoch", lambda key: 0)(key) == self._epoch:
                history.append_exchange(key, raw_text, answer)
            self._committed = True

    def with_content(self, content):
        history, key, raw_text, answer = self._exchange
        result = PendingReply(content, history, key, raw_text, answer)
        result._epoch = self._epoch
        return result
