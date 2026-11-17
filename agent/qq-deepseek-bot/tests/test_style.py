import asyncio

from qq_deepseek.core.events import Message
from qq_deepseek.services.memory_service import MemoryService
from qq_deepseek.storage.memory_sqlite import SQLiteMemoryStore


def test_only_owner_private_messages_feed_style_adapter(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "style.sqlite3")
    service = MemoryService(store, master_qq_id=10, style_enabled=True)
    owner = Message("private", 10, None, 99, "", False)
    other = Message("private", 20, None, 99, "", False)
    group = Message("group", 10, 30, 99, "", False)
    asyncio.run(service.style.observe(owner, "其实我觉得这样也挺好"))
    asyncio.run(service.style.observe(other, "别人的说话方式"))
    asyncio.run(service.style.observe(group, "群里的说话方式"))
    asyncio.run(service.style.observe(owner, "/help"))
    assert store.style_samples() == ["其实我觉得这样也挺好"]
    context = asyncio.run(service.context_for("private:10"))
    assert "适配句长、语气和措辞" in context
    assert "别人的说话方式" not in context
    assert "其实我觉得这样也挺好" not in asyncio.run(service.context_for("private:20"))
    store.close()


def test_style_samples_are_bounded_and_truncated(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "style.sqlite3")
    for i in range(20): store.add_style_sample(f"{i}:" + "长" * 100)
    samples = store.style_samples(20)
    assert len(samples) == 12
    assert all(len(item) <= 80 for item in samples)
    store.close()
