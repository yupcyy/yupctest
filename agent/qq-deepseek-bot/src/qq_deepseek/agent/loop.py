"""Bounded tool-calling loop for an OpenAI-compatible async client."""
import json
from typing import Any

from qq_deepseek.tools.registry import ToolRegistry


async def run_tool_loop(
    provider: Any,
    messages: list[dict[str, Any]],
    registry: ToolRegistry,
    *,
    max_rounds: int = 3,
    max_calls: int = 5,
    max_tokens: int = 1024,
    conversation_id: str | None = None,
    usage_service: Any = None,
) -> str:
    """Return final answer, never persisting intermediate tool messages to chat history.

    provider is the existing DeepSeekProvider exposing .client and .model.
    """
    if max_rounds < 0 or max_calls < 0:
        raise ValueError("Tool limits must be nonnegative")
    working = list(messages)
    used = 0
    rounds = 0
    schemas = registry.schemas()

    while True:
        can_use_tools = bool(schemas) and rounds < max_rounds and used < max_calls
        kwargs: dict[str, Any] = {
            "model": provider.model,
            "messages": working,
            "max_tokens": (
                max(max_tokens, 512)
                if can_use_tools
                else max_tokens
            ),
            "stream": False,
        }
        if can_use_tools:
            kwargs.update(tools=schemas, tool_choice="auto")
        response = await provider.client.chat.completions.create(**kwargs)
        if usage_service is not None and conversation_id:
            await usage_service.record(
                response, model=provider.model, conversation_id=conversation_id,
                operation="agent_tool_round" if rounds else "agent_chat",
            )
        msg = response.choices[0].message
        calls = list(msg.tool_calls or [])
        if not calls:
            return msg.content or "（模型未返回文本）"
        if not can_use_tools:
            return msg.content or "（工具调用次数已达到限制，请稍后再试。）"

        # Record assistant's entire tool_calls message, followed by exactly one
        # tool result for every requested ID (including rejected calls).
        assistant: dict[str, Any] = {"role": "assistant", "content": msg.content, "tool_calls": []}
        for call in calls:
            assistant["tool_calls"].append({
                "id": call.id,
                "type": "function",
                "function": {"name": call.function.name, "arguments": call.function.arguments},
            })
        working.append(assistant)

        for call in calls:
            if used >= max_calls:
                result = {"error": "Tool call limit reached"}
            elif call.type != "function":
                result = {"error": "Unsupported tool call type"}
                used += 1
            else:
                used += 1
                result = await registry.invoke(call.function.name, call.function.arguments)
            working.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, ensure_ascii=False),
            })
        rounds += 1
