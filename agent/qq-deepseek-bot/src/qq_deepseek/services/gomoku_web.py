from __future__ import annotations

import asyncio
import json
import random
import re
import time
import uuid
from pathlib import Path

from qq_deepseek.core.prompt_manager import PromptManager
from qq_deepseek.services.gomoku import COLS, SIZE, _score, _win


class GomokuWebService:
    def __init__(self, root: Path, provider):
        self.root, self.provider = root, provider
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = asyncio.Lock()
        self.persona = PromptManager().build(tools_enabled=False)

    def _path(self, game_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", game_id):
            raise ValueError("invalid game id")
        path = self.root / f"{game_id}.json"
        if path.is_symlink():
            raise ValueError("unsafe game path")
        return path

    def _load(self, game_id: str) -> dict | None:
        path = self._path(game_id)
        if not path.is_file() or path.stat().st_size > 256 * 1024:
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, game: dict) -> None:
        path = self._path(game["game_id"])
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(game, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    async def create(self, username: str, mode: str) -> dict:
        if mode not in {"agent", "pvp"}:
            raise ValueError("invalid mode")
        now = time.time()
        game = {"game_id": uuid.uuid4().hex, "mode": mode, "black": username,
                "white": "大肥鱼" if mode == "agent" else "", "board": [["."] * SIZE for _ in range(SIZE)],
                "turn": "X", "status": "playing" if mode == "agent" else "waiting",
                "winner": "", "last": None, "chat": [], "created_at": now, "updated_at": now}
        async with self.lock:
            self._save(game)
        return game

    async def get(self, game_id: str, username: str, admin: bool = False) -> dict | None:
        async with self.lock:
            game = self._load(game_id)
        if not game or (not admin and username not in {game["black"], game["white"]}):
            return None
        return game

    async def join(self, game_id: str, username: str) -> dict:
        async with self.lock:
            game = self._load(game_id)
            if not game or game["mode"] != "pvp":
                raise ValueError("房间不存在")
            if game["white"] and username not in {game["black"], game["white"]}:
                raise ValueError("房间已满")
            if username == game["black"]:
                return game
            game["white"], game["status"], game["updated_at"] = username, "playing", time.time()
            self._save(game)
            return game

    def _agent_move(self, board):
        choices = [(x, y) for y in range(SIZE) for x in range(SIZE) if board[y][x] == "." and any(
            0 <= x + dx < SIZE and 0 <= y + dy < SIZE and board[y + dy][x + dx] != "."
            for dx in (-1, 0, 1) for dy in (-1, 0, 1))]
        return max(choices, key=lambda p: (_score(board, *p, "O"), random.random()))

    async def _say(self, game: dict, event: str) -> str:
        prompt = (f"你正在和{game['black']}下五子棋，你是白棋。{event}。"
                  "结合当前人格自然说一句不超过35字的话，可以可爱、紧张、得意或安慰，别解释算法。")
        try:
            return await asyncio.wait_for(self.provider.chat([
                {"role": "system", "content": self.persona}, {"role": "user", "content": prompt}],
                conversation_id=f"web-gomoku:{game['game_id']}", max_tokens=80), 15)
        except Exception:
            return random.choice(["鱼鳍轻轻一摆，我落这里啦。", "这一手可要看仔细喔。", "唔……本鱼认真起来了。"])

    async def move(self, game_id: str, username: str, x: int, y: int) -> dict:
        if not (0 <= x < SIZE and 0 <= y < SIZE):
            raise ValueError("落子超出棋盘")
        async with self.lock:
            game = self._load(game_id)
            if not game or game["status"] != "playing":
                raise ValueError("对局尚未开始或已经结束")
            stone = "X" if username == game["black"] else "O" if username == game["white"] else ""
            if not stone or stone != game["turn"]:
                raise ValueError("还没轮到你")
            if game["board"][y][x] != ".":
                raise ValueError("这里已经有棋子")
            game["board"][y][x], game["last"], game["updated_at"] = stone, [x, y], time.time()
            if _win(game["board"], stone):
                game["status"], game["winner"] = "finished", username
            elif all(cell != "." for row in game["board"] for cell in row):
                game["status"], game["winner"] = "finished", "draw"
            else:
                game["turn"] = "O" if stone == "X" else "X"
            self._save(game)

        if game["mode"] == "agent" and game["status"] == "playing" and game["turn"] == "O":
            async with self.lock:
                game = self._load(game_id)
                ax, ay = self._agent_move(game["board"])
                game["board"][ay][ax], game["last"] = "O", [ax, ay]
                event = f"你刚落在 {COLS[ax]}{ay + 1}"
                if _win(game["board"], "O"):
                    game["status"], game["winner"] = "finished", "大肥鱼"
                    event += "并赢下了这盘"
                else:
                    game["turn"] = "X"
                self._save(game)
            comment = await self._say(game, event)
            async with self.lock:
                game = self._load(game_id)
                game["chat"].append({"role": "agent", "text": comment, "at": time.time()})
                game["chat"] = game["chat"][-30:]
                self._save(game)
        return game

    async def chat(self, game_id: str, username: str, message: str) -> dict:
        message = " ".join(message.split())[:300]
        if not message:
            raise ValueError("消息不能为空")
        game = await self.get(game_id, username)
        if not game or game["mode"] != "agent":
            raise ValueError("当前不是人机对局")
        game["chat"].append({"role": "user", "text": message, "at": time.time()})
        context = "；".join(item["text"] for item in game["chat"][-6:])
        try:
            answer = await asyncio.wait_for(self.provider.chat([
                {"role": "system", "content": self.persona},
                {"role": "user", "content": f"你在陪{username}下五子棋。近期对话：{context}\n自然简短回复，不超过80字。"}],
                conversation_id=f"web-gomoku:{game_id}", max_tokens=140), 20)
        except Exception:
            answer = "本鱼在听，也在盯着棋盘呢。"
        async with self.lock:
            game = self._load(game_id)
            game["chat"].extend([{"role": "user", "text": message, "at": time.time()},
                                 {"role": "agent", "text": answer, "at": time.time()}])
            game["chat"] = game["chat"][-30:]
            self._save(game)
        return game
