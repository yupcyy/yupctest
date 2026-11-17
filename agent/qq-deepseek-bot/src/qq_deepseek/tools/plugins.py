"""Administrator-owned plugin manifest. QQ messages cannot modify this file."""
import asyncio
import importlib
import json
from pathlib import Path


def manifest(path):
    return json.loads(Path(path).read_text()) if Path(path).exists() else {}


def load_plugins(path, owner):
    tools, toolsets = [], []
    for entry in manifest(path).get('plugins', []):
        if not entry.get('enabled', False):
            continue
        scope = entry.get('scope', 'owner')
        if scope not in {'owner', 'public'}:
            raise ValueError('Plugin scope must be owner or public')
        if scope == 'owner' and not owner:
            continue
        if entry['type'] == 'python':
            module, function = entry['factory'].split(':', 1)
            tools.extend(getattr(importlib.import_module(module), function)())
        elif entry['type'] == 'stdio':
            from pydantic_ai.mcp import MCPServerStdio
            toolsets.append(MCPServerStdio(entry['command'], args=entry.get('args', []),
                env=entry.get('env'), tool_prefix=entry['name'], timeout=20, allow_sampling=False))
        elif entry['type'] == 'http':
            from pydantic_ai.mcp import MCPServerStreamableHTTP
            toolsets.append(MCPServerStreamableHTTP(entry['url'], tool_prefix=entry['name'], timeout=20,
                allow_sampling=False))
        else:
            raise ValueError('Unknown plugin type')
    return tools, toolsets


async def server_operation(path, operation):
    commands = manifest(path).get('server_operations', {})
    argv = commands.get(operation)
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
        return '操作未配置。'
    process = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT)
    try:
        # Bound output as well as runtime. No shell expansion or model-supplied arguments.
        output = await asyncio.wait_for(process.stdout.read(8193), 15)
        if len(output) > 8192:
            return '操作输出超出限制。'
        await asyncio.wait_for(process.wait(), 5)
        return output.decode(errors='replace')[:8192]
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
