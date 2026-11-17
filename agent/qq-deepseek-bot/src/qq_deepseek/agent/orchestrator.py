"""Drop-in ChatService-compatible agent entry point (reply/reset)."""
import asyncio

from qq_deepseek.agent.loop import run_tool_loop
from qq_deepseek.core.prompt_manager import PromptManager
from qq_deepseek.core.reply_mode import (
    ReplyPolicy,
    select_reply_mode,
)
from qq_deepseek.storage.memory import InMemoryHistory
from qq_deepseek.tools.registry import ToolRegistry


class AgentOrchestrator:
    def __init__(
        self,
        provider,
        history: InMemoryHistory,
        registry: ToolRegistry,
        prompt_manager: PromptManager,
        *,
        reply_policy: ReplyPolicy | None = None,
        persona: str = "dafeiyu",
        usage_service=None,
        memory_service=None,
        max_tool_rounds: int = 3,
        max_tool_calls: int = 5,
    ):
        self.provider = provider
        self.history = history
        self.registry = registry
        self.prompt_manager = prompt_manager
        self.reply_policy = reply_policy or ReplyPolicy()
        self.persona = persona
        self.usage_service = usage_service
        self.memory_service = memory_service
        self.max_tool_rounds = max_tool_rounds
        self.max_tool_calls = max_tool_calls
        self._locks: dict[str, asyncio.Lock] = {}

    async def reply(self, conversation_id: str, prompt: str) -> str:
        async with self._locks.setdefault(conversation_id, asyncio.Lock()):
            mode, prompt = select_reply_mode(prompt)
            max_tokens = self.reply_policy.max_tokens(mode)
            system = self.prompt_manager.build(self.persona, tools_enabled=bool(self.registry.schemas()))
            additions = await self.memory_service.context_for(conversation_id) if self.memory_service else ""
            if additions:
                system += "\n\n" + additions
            messages = (
                [{"role": "system", "content": system}]
                + self.history.get(conversation_id)
                + [{"role": "user", "content": prompt}]
            )
            answer = await run_tool_loop(
                self.provider,
                messages,
                self.registry,
                max_rounds=self.max_tool_rounds,
                max_calls=self.max_tool_calls,
                max_tokens=max_tokens,
                conversation_id=conversation_id,
                usage_service=self.usage_service,
            )
            self.history.append_exchange(conversation_id, prompt, answer)
            return answer

    async def reset(self, conversation_id: str) -> None:
        async with self._locks.setdefault(conversation_id, asyncio.Lock()):
            self.history.clear(conversation_id)
