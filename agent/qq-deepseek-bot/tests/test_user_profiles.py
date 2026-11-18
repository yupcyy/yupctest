import asyncio
from types import SimpleNamespace
from qq_deepseek.services.companion_commands import CompanionCommands


def test_owner_management_self_switch_and_isolation():
    async def run():
        service = CompanionCommands(None, None, 10, None)
        rows = {}
        async def call(method, *args):
            if method == 'load':
                return rows.get(args[0])
            if method == 'save':
                rows[args[0]] = args[1]
        service.call = call
        def message(uid, kind='private'):
            return SimpleNamespace(user_id=uid, kind=kind)
        assert '未开启' in await service.command(message(20), '/画像 喜欢茶')
        assert '私聊' in await service.command(message(10, 'group'), '/画像 20 喜欢茶')
        assert '已保存' in await service.command(message(10), '/画像 20 喜欢茶')
        assert '已保存' in await service.command(message(10), '/画像 20 补充 喜欢短句')
        assert rows['profile:20']['note'] == '喜欢茶\n喜欢短句'
        assert rows['profile:20']['updated_by'] == 10
        assert rows['profile:20']['scope'] == 'group'
        assert '喜欢茶' in await service.command(message(10), '/画像 20')
        assert '已保存' in await service.command(message(10), '/画像 20 设置 喜欢咖啡')
        assert rows['profile:20']['note'] == '喜欢咖啡'
        service.enable_self_profile = True
        assert '已保存' in await service.command(message(30), '/画像 喜欢游戏')
        assert rows['profile:30']['note'] == '喜欢游戏'
        assert rows['profile:20']['note'] == '喜欢咖啡'
        assert '500' in await service.command(message(10), '/画像 20 设置 ' + '字' * 501)
    asyncio.run(run())


def test_group_profile_injection_targets_current_speaker_only():
    from qq_deepseek.core.router import Router
    from qq_deepseek.core.events import Message
    async def run():
        contexts = []
        class Chat:
            async def reply(self, key, request):
                contexts.append(await request.context_factory())
                return 'reply'
        class Commands:
            async def command(self, *args):
                return None
            async def call(self, method, key):
                return {'profile:20': {'note': 'likes tea'},
                        'profile:30': {'note': 'private secret', 'scope': 'private'}}.get(key)
        router = Router(Chat(), frozenset(), frozenset())
        router.companion_commands = Commands()
        await router.handle(Message('group', 20, 1, 99, 'hello', True))
        assert 'likes tea' in contexts[-1]
        assert 'QQ=20' in contexts[-1]
        await router.handle(Message('group', 30, 1, 99, 'hello', True))
        assert 'likes tea' not in contexts[-1]
        assert 'private secret' not in contexts[-1]
        await router.handle(Message('private', 20, None, 99, 'hello', False))
        assert 'likes tea' in contexts[-1]
        assert '私聊画像当前未建立' in contexts[-1]
    asyncio.run(run())


def test_mentions_and_numeric_profile_lookup():
    from qq_deepseek.core.events import parse_message
    from qq_deepseek.core.router import Router
    async def run():
        contexts = []
        class Chat:
            async def reply(self, key, request):
                contexts.append(await request.context_factory())
                return 'reply'
        class Commands:
            async def command(self, *args):
                return None
            async def call(self, method, key):
                return {'note': '目标喜欢茶', 'scope': 'group'} if key == 'profile:123456' else None
        router = Router(Chat(), frozenset(), frozenset())
        router.companion_commands = Commands()
        base = dict(post_type='message', message_type='group', user_id=20, self_id=99, group_id=1)
        message = parse_message(dict(base, message=[{'type':'at','data':{'qq':'99'}},
            {'type':'at','data':{'qq':'123456'}}, {'type':'text','data':{'text':'介绍一下'}}]))
        assert message.mentioned_user_ids == (123456,)
        await router.handle(message)
        assert '目标喜欢茶' in contexts[-1]
        raw = parse_message(dict(base, message='[CQ:at,qq=99] 用户123456怎么样'))
        await router.handle(raw)
        assert '目标喜欢茶' in contexts[-1]
        raw = parse_message(dict(base, message='[CQ:at,qq=99][CQ:at,qq=123456]介绍一下'))
        assert raw.mentioned_user_ids == (123456,)
    asyncio.run(run())
