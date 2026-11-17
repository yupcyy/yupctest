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
            mode, prompt = select_reply_mode(prompt)
            max_tokens = self.reply_policy.max_tokens(mode)
            additions = await self.memory_service.context_for(conversation_id) if self.memory_service else ""
            system = self.system_prompt + ("\n\n" + additions if additions else "")
            messages = ([{"role": "system", "content": system}]
                        + self.history.get(conversation_id)
                        + [{"role": "user", "content": prompt}])
            kwargs = {}
            if self._supports_conversation_id:
                kwargs['conversation_id'] = conversation_id
            if self._supports_max_tokens:
                kwargs['max_tokens'] = max_tokens
            answer = await self.provider.chat(messages, **kwargs)
            self.history.append_exchange(conversation_id, prompt, answer)
            return answer

    async def reset(self, conversation_id: str) -> None:
        async with self._locks.setdefault(conversation_id, asyncio.Lock()):
            self.history.clear(conversation_id)
