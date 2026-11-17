"""Explicit allowlist and validation boundary between LLM and tools."""
import asyncio
import json
import logging
import time
from typing import Any

from qq_deepseek.tools.base import Tool

log = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None, *, timeout: float = 20.0):
        self._tools: dict[str, Tool] = {}
        self.timeout = timeout
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if not tool.name or tool.name in self._tools:
            raise ValueError(f"Invalid or duplicate tool name: {tool.name!r}")
        self._tools[tool.name] = tool

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    @staticmethod
    def _validate(tool: Tool, arguments: dict[str, Any]) -> None:
        schema = tool.parameters
        allowed = schema.get("properties", {})
        required = schema.get("required", [])
        for name in required:
            if name not in arguments:
                raise ValueError(f"Missing argument: {name}")
        if schema.get("additionalProperties") is False:
            unknown = set(arguments) - set(allowed)
            if unknown:
                raise ValueError(f"Unknown argument(s): {', '.join(sorted(unknown))}")
        for name, value in arguments.items():
            rule = allowed.get(name, {})
            kind = rule.get("type")
            if kind == "string" and not isinstance(value, str):
                raise ValueError(f"{name} must be a string")
            if kind == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
                raise ValueError(f"{name} must be an integer")
            if kind == "boolean" and not isinstance(value, bool):
                raise ValueError(f"{name} must be a boolean")

    async def invoke(self, name: str, arguments_json: str) -> dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            return {"error": f"Tool not allowed: {name}"}
        started = time.monotonic()
        try:
            args = json.loads(arguments_json)
            if not isinstance(args, dict):
                raise ValueError("Tool arguments must be an object")
            self._validate(tool, args)
            result = await asyncio.wait_for(tool.execute(args), timeout=self.timeout)
            if not isinstance(result, dict):
                raise TypeError("Tool must return a JSON object")
            log.info("Tool %s succeeded in %.2fs", name, time.monotonic() - started)
            return result
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            log.warning("Invalid tool request %s: %s", name, exc)
            return {"error": str(exc)}
        except TimeoutError:
            log.warning("Tool %s timed out", name)
            return {"error": "Tool timed out"}
        except Exception as exc:
            log.exception("Tool %s failed", name)
            return {"error": f"Tool failed: {type(exc).__name__}"}
