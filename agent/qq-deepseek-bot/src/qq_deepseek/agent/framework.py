"""Pydantic AI runtime; QQ identities are supplied by the router, never the model."""
import asyncio
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart, TextPart
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

from qq_deepseek.core.prompt_manager import PromptManager
from qq_deepseek.core.reply_mode import select_reply_mode
from qq_deepseek.tools.plugins import load_plugins, server_operation


class FrameworkAgent:
    def __init__(self, settings, provider, history, memory_service, reply_policy):
        self.settings = settings
        self.provider = provider
        self.history = history
        self.memory_service = memory_service
        self.reply_policy = reply_policy
        self._locks = {}
        self.model = OpenAIChatModel(provider.model, provider=OpenAIProvider(openai_client=provider.client))
        self.config_path = Path(settings.plugin_config)
        if not self.config_path.is_absolute():
            self.config_path = Path(__file__).resolve().parents[3] / self.config_path

    async def reply(self, conversation_id, prompt, *, allow_tools=True):
        async with self._locks.setdefault(conversation_id, asyncio.Lock()):
            mode, prompt = select_reply_mode(prompt)
            owner = (self.settings.master_qq_id > 0 and
                     conversation_id == f'private:{self.settings.master_qq_id}')
            tools, toolsets = load_plugins(self.config_path, owner) if allow_tools else ([], [])
            if owner and allow_tools:
                async def operate(operation: str) -> str:
                    """Run an administrator-configured server operation by its name."""
                    return await server_operation(self.config_path, operation)
                tools.append(operate)
            system = PromptManager().build(tools_enabled=allow_tools)
            if self.memory_service:
                system += '\n' + await self.memory_service.context_for(conversation_id)
            history = []
            # Group conversations are keyed by group + QQ user, so loading history
            # cannot mix different members or groups.
            for message in self.history.get(conversation_id):
                history.append(ModelRequest(parts=[UserPromptPart(message['content'])])
                    if message['role'] == 'user' else ModelResponse(parts=[TextPart(message['content'])]))
            agent = Agent(self.model, instructions=system, tools=tools, toolsets=toolsets)
            async with asyncio.timeout(120), agent:
                result = await asyncio.wait_for(agent.run(prompt, message_history=history,
                    model_settings={'max_tokens': max(512, self.reply_policy.max_tokens(mode))},
                    usage_limits=UsageLimits(request_limit=4, tool_calls_limit=5)), 120)
            answer = result.output
            self.history.append_exchange(conversation_id, prompt, answer)
            usage_service = self.provider.usage_service
            if usage_service:
                from types import SimpleNamespace
                usage = result.usage()
                await usage_service.record(SimpleNamespace(usage=SimpleNamespace(
                    prompt_tokens=usage.input_tokens, completion_tokens=usage.output_tokens,
                    total_tokens=usage.input_tokens + usage.output_tokens)),
                    model=self.provider.model, conversation_id=conversation_id, operation='pydantic_agent')
            return answer

    async def reset(self, conversation_id):
        async with self._locks.setdefault(conversation_id, asyncio.Lock()):
            self.history.clear(conversation_id)

    async def proactive_reply(self, conversation_id, prompt):
        return await self.reply(conversation_id, prompt, allow_tools=False)

    async def reply_without_tools(self, conversation_id, prompt):
        return await self.reply(conversation_id, prompt, allow_tools=False)
