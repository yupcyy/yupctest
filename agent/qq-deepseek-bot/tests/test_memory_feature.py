import asyncio
from types import SimpleNamespace
from qq_deepseek.storage.memory_sqlite import SQLiteMemoryStore
from qq_deepseek.services.memory_service import MemoryService
from qq_deepseek.core.router import Router
from qq_deepseek.core.events import Message


def test_persistence_and_isolation(tmp_path):
    path=tmp_path/'agent.sqlite3'
    store=SQLiteMemoryStore(path,max_turns=2)
    store.append_exchange('private:10','hi','hello')
    store.append_exchange('private:20','private','secret')
    i=store.add_memory(10,'likes rice')
    assert store.list_memories(20)==[]
    assert store.delete_memory(20,i) is False
    store.close()
    store=SQLiteMemoryStore(path,max_turns=2)
    assert store.get('private:10')[1]['content']=='hello'
    assert store.list_memories(10)[0][1]=='likes rice'
    store.clear('private:10')
    assert store.get('private:10')==[]
    store.close()


def test_master_private_only(tmp_path):
    store=SQLiteMemoryStore(tmp_path/'a.sqlite3')
    service=MemoryService(store,master_qq_id=10)
    store.add_memory(10,'secret')
    assert '主人' in asyncio.run(service.context_for('private:10'))
    assert 'secret' in asyncio.run(service.context_for('private:10'))
    group_context = asyncio.run(service.context_for('group:30:user:10'))
    assert 'Master' in group_context
    assert 'secret' not in group_context
    assert 'Master' not in asyncio.run(service.context_for('group:30:user:20'))
    assert 'secret' not in asyncio.run(service.context_for('private:20'))
    store.close()


def test_memory_commands_private_and_authorized(tmp_path):
    store=SQLiteMemoryStore(tmp_path/'a.sqlite3')
    service=MemoryService(store,10)
    def msg(kind, uid):
        return Message(kind,uid,100 if kind=='group' else None,999,'',False)
    assert '私聊' in asyncio.run(service.command(msg('group',10),'/remember secret'))
    assert '已记住' in asyncio.run(service.command(msg('private',20),'/remember blue'))
    assert 'blue' in asyncio.run(service.command(msg('private',20),'/memory'))
    assert '当前没有' in asyncio.run(service.command(msg('private',10),'/memory'))
    store.close()


def test_router_passes_memory_commands(tmp_path):
    store=SQLiteMemoryStore(tmp_path/'a.sqlite3')
    service=MemoryService(store,10)
    chat=SimpleNamespace(reply=None,reset=None)
    router=Router(chat,frozenset(),frozenset(),service)
    msg=Message('private',20,None,999,'/remember hello',False)
    assert '已记住' in asyncio.run(router.handle(msg))
    store.close()
