"""Offline framework smoke test; requires the declared Pydantic AI dependency."""
import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip('pydantic_ai')
from pydantic_ai.models.test import TestModel
from qq_deepseek.agent.framework import FrameworkAgent
from qq_deepseek.core.reply_mode import ReplyPolicy
from qq_deepseek.storage.memory import InMemoryHistory


def test_framework_keeps_history(tmp_path):
    from openai import AsyncOpenAI
    async def scenario():
        client = AsyncOpenAI(api_key='offline-test')
        try:
            provider = SimpleNamespace(model='deepseek-chat', client=client, usage_service=None)
            settings = SimpleNamespace(master_qq_id=10, api_key='offline-test',
                plugin_config=str(tmp_path / 'plugins.json'))
            settings_path = tmp_path / 'plugins.json'
            settings_path.write_text('{"server_operations":{}}')
            history = InMemoryHistory(10)
            service = FrameworkAgent(settings, provider, history, None, ReplyPolicy())
            service.model = TestModel(call_tools=[], custom_output_text='本鱼来了')
            assert await service.reply('private:10', '你好') == '本鱼来了'
            assert len(history.get('private:10')) == 2
            assert history.get('private:20') == []
            await service.reset('private:10')
            assert history.get('private:10') == []
        finally:
            await client.close()
    asyncio.run(scenario())


def test_framework_plugin_execution_and_proactive_has_no_tools(tmp_path, monkeypatch):
    import json
    import sys
    from openai import AsyncOpenAI

    calls = []

    async def fish_status() -> str:
        """Check the fish's status."""
        calls.append('fish_status')
        return '正在摸鱼'

    monkeypatch.setitem(sys.modules, 'fish_test_plugin',
                        SimpleNamespace(tools=lambda: [fish_status]))
    path = tmp_path / 'plugins.json'
    path.write_text(json.dumps({'plugins': [{
        'name': 'fish', 'type': 'python', 'factory': 'fish_test_plugin:tools',
        'scope': 'public', 'enabled': True,
    }]}))

    async def scenario():
        client = AsyncOpenAI(api_key='offline-test')
        try:
            provider = SimpleNamespace(model='deepseek-chat', client=client, usage_service=None)
            settings = SimpleNamespace(master_qq_id=10, api_key='offline-test', plugin_config=str(path))
            service = FrameworkAgent(settings, provider, InMemoryHistory(10), None, ReplyPolicy())
            service.model = TestModel(call_tools=['fish_status'])
            answer = await service.reply('private:20', '你在干什么')
            assert calls == ['fish_status']
            assert '正在摸鱼' in answer
            model = TestModel(custom_output_text='本鱼冒泡')
            service.model = model
            assert await service.proactive_reply('group:30:user:20', '插一句') == '本鱼冒泡'
            assert model.last_model_request_parameters.function_tools == []
            assert calls == ['fish_status']
        finally:
            await client.close()

    asyncio.run(scenario())


def test_group_reply_reads_and_stores_user_scoped_history(tmp_path):
    from openai import AsyncOpenAI
    async def scenario():
        client = AsyncOpenAI(api_key='offline-test')
        try:
            provider = SimpleNamespace(model='deepseek-chat', client=client, usage_service=None)
            settings = SimpleNamespace(master_qq_id=10, api_key='offline-test',
                plugin_config=str(tmp_path / 'plugins.json'))
            (tmp_path / 'plugins.json').write_text('{"plugins":[]}')
            history = InMemoryHistory(10)
            history.append_exchange('group:30:user:20', '旧问题', '旧回答')
            service = FrameworkAgent(settings, provider, history, None, ReplyPolicy())
            model = TestModel(call_tools=[], custom_output_text='当前回答')
            service.model = model
            assert await service.reply('group:30:user:20', '新问题') == '当前回答'
            assert len(history.get('group:30:user:20')) == 4
            assert history.get('group:30:user:21') == []
            request = model.last_model_request_parameters
            assert request is not None
        finally:
            await client.close()
    asyncio.run(scenario())
