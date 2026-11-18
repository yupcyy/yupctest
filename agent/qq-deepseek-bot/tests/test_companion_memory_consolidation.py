from dataclasses import replace
import pytest
from qq_deepseek.services.memory_consolidation import CandidateMemory, CandidateQueue


def candidate():
    return CandidateMemory('1', 10, '喜欢茶', 'private_confirmation', ('event1',), .99, 1, 100)


def test_reject_and_delete_prevent_repromotion():
    queue = CandidateQueue()
    c = candidate()
    assert queue.propose(c)
    assert not queue.for_user(20)
    with pytest.raises(PermissionError):
        queue.review('1', user_id=20, action='approve', now=2, private=True)
    queue.review('1', user_id=10, action='reject', now=2, private=True)
    assert not queue.propose(replace(c, candidate_id='2'))
    queue.review('1', user_id=10, action='delete', now=3, private=True)
    assert queue.items['1'].content == ''


def test_fiction_sensitive_and_expiry():
    queue = CandidateQueue()
    c = candidate()
    assert not queue.propose(replace(c, source_kind='dream'))
    assert not queue.propose(c, sensitive=True)
    assert queue.propose(c)
    with pytest.raises(ValueError):
        queue.review('1', user_id=10, action='approve', now=100, private=True)


def test_private_review_commands_do_not_write_long_term_memory():
    import asyncio
    import time
    from types import SimpleNamespace
    from qq_deepseek.services.memory_service import MemoryService
    class Store:
        def add_memory(self, *args):
            raise AssertionError('review must not persist facts')
    async def run():
        service = MemoryService(Store(), 10, style_enabled=False)
        c = replace(candidate(), created_at=time.time(), expires_at=time.time() + 100)
        assert service.candidates.propose(c)
        owner = SimpleNamespace(kind='private', user_id=10)
        other = SimpleNamespace(kind='private', user_id=20)
        assert '暂无候选' in await service.command(other, '/候选记忆 查看')
        assert '不可操作' in await service.command(other, '/候选记忆 批准 1')
        assert '不会自动写入' in await service.command(owner, '/候选记忆 批准 1')
        assert service.candidates.items['1'].status == 'approved'
        assert '只允许在私聊' in await service.command(SimpleNamespace(kind='group'), '/候选记忆 查看')
    asyncio.run(run())
