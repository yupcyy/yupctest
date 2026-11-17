import asyncio
from types import SimpleNamespace

from qq_deepseek.core.events import Message
from qq_deepseek.services.gomoku import GomokuService
from qq_deepseek.storage.memory_sqlite import SQLiteMemoryStore


def test_gomoku_is_local_persistent_and_validates_moves(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "game.sqlite3")
    game = GomokuService(store)
    msg = Message("private", 10, None, 99, "", False)
    assert "你执黑" in asyncio.run(game.command(msg, "/五子棋 开始"))
    answer = asyncio.run(game.command(msg, "/落子 H8"))
    assert "本鱼落在" in answer
    assert store.load_game(msg.conversation_id) is not None
    assert "不能下" in asyncio.run(game.command(msg, "/落子 H8"))
    assert "收起来" in asyncio.run(game.command(msg, "/五子棋 结束"))
    store.close()


def test_preferences_are_scoped(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "prefs.sqlite3")
    assert store.preference("private", 10, "proactive", "normal") == "normal"
    store.set_preference("private", 10, "proactive", "low")
    assert store.preference("private", 10, "proactive", "normal") == "low"
    assert store.preference("group", 10, "proactive", "normal") == "normal"
    store.close()


def test_group_pvp_and_bare_mentioned_coordinate(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "game.sqlite3")
    game = GomokuService(store, tmp_path / "qq-games")
    black = Message("group", 10, 30, 99, "", True)
    white = Message("group", 20, 30, 99, "", True)
    assert "双人棋局" in asyncio.run(game.command(black, "/五子棋 对战 20"))
    assert "QQ10 落在 H8" in asyncio.run(game.command(black, "H8"))
    assert "QQ20 落在 H9" in asyncio.run(game.command(white, "/落子 H9"))
    store.close()
