from qq_deepseek.services.runtime_context import ReplyRequest, clean_legacy_history, resolve_context, PendingReply
import asyncio
import inspect

from qq_deepseek.core.reply_mode import (
    ReplyPolicy,
    select_reply_mode,
)
from qq_deepseek.storage.memory import InMemoryHistory


class ChatService:
    def __init__(self, provider, history: InMemoryHistory, system_prompt: str, memory_service=None, reply_policy: ReplyPolicy | None = None,):
        self.provider = provider
        self.history = history
        self.system_prompt = system_prompt
        self.memory_service = memory_service
        self.reply_policy = reply_policy or ReplyPolicy()
        self._supports_max_tokens = "max_tokens" in inspect.signature(provider.chat).parameters
        self._supports_conversation_id = "conversation_id" in inspect.signature(provider.chat).parameters
        self._locks: dict[str, asyncio.Lock] = {}

    async def reply(self, conversation_id: str, prompt: str) -> str:
        async with self._locks.setdefault(conversation_id, asyncio.Lock()):
            request = prompt
            raw_text = str(request)
            clean_legacy_history(self.history, conversation_id)
            mode, prompt = select_reply_mode(raw_text)
            max_tokens = self.reply_policy.max_tokens(mode)
            additions = await self.memory_service.context_for(conversation_id) if self.memory_service and not getattr(request, "isolated", False) else ""
            system = self.system_prompt + ("\n\n" + additions if additions else "")
            system += "\n当前聊天路径未挂载可调用工具；时间由服务端直接注入。不要声称能执行未提供的工具。"
            system += "\n" + await resolve_context(request)
            messages = ([{"role": "system", "content": system}]
                        + (self.history.get(conversation_id) if not getattr(request, "isolated", False) else [])
                        + [{"role": "user", "content": prompt}])
            kwargs = {}
            if self._supports_conversation_id:
                kwargs['conversation_id'] = conversation_id
            if self._supports_max_tokens:
                kwargs['max_tokens'] = max_tokens
            answer = await self.provider.chat(messages, **kwargs)
            if not getattr(request, "ephemeral", False) and not getattr(request, "defer_history", False):
                self.history.append_exchange(conversation_id, raw_text, answer)
            if getattr(request, "defer_history", False) and not getattr(request, "ephemeral", False):
                return PendingReply(answer, self.history, conversation_id, raw_text, answer)
            return answer

    async def reset(self, conversation_id: str) -> None:
        async with self._locks.setdefault(conversation_id, asyncio.Lock()):
            self.history.clear(conversation_id)

    async def proactive_reply(self, conversation_id, prompt):
        return await self.reply(conversation_id, ReplyRequest(str(prompt), runtime_context=getattr(prompt, "runtime_context", ""), ephemeral=True, isolated=getattr(prompt, "isolated", False)))

    async def reply_without_tools(self, conversation_id, prompt):
        return await self.reply(conversation_id, prompt)
