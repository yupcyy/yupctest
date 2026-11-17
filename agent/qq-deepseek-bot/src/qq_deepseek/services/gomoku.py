"""Deterministic local Gomoku; no model calls."""
import json
import random
import re
from pathlib import Path

SIZE = 15
COLS = "ABCDEFGHIJKLMNO"


def _win(board, stone):
    for y in range(SIZE):
        for x in range(SIZE):
            for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
                if all(0 <= x + dx*i < SIZE and 0 <= y + dy*i < SIZE and
                       board[y + dy*i][x + dx*i] == stone for i in range(5)):
                    return True
    return False


def _score(board, x, y, stone):
    other = "O" if stone == "X" else "X"
    score = 0
    for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
        for target, weight in ((stone, 10), (other, 9)):
            run = 1
            for sign in (-1, 1):
                i = 1
                while 0 <= x+dx*i*sign < SIZE and 0 <= y+dy*i*sign < SIZE and board[y+dy*i*sign][x+dx*i*sign] == target:
                    run += 1; i += 1
            score += weight ** min(run, 5)
    return score - (abs(x-7) + abs(y-7))


def _render(board, last=None):
    occupied = [(x, y) for y, row in enumerate(board) for x, v in enumerate(row) if v != "."]
    if occupied:
        xs, ys = zip(*occupied)
        lo_x, hi_x = max(0, min(xs)-2), min(14, max(xs)+2)
        lo_y, hi_y = max(0, min(ys)-2), min(14, max(ys)+2)
    else:
        lo_x, hi_x, lo_y, hi_y = 4, 10, 4, 10
    lines = ["   " + " ".join(COLS[lo_x:hi_x+1])]
    for y in range(lo_y, hi_y+1):
        cells = []
        for x in range(lo_x, hi_x+1):
            v = board[y][x]
            cells.append("◆" if last == (x, y) and v == "O" else {".":"·", "X":"●", "O":"○"}[v])
        lines.append(f"{y+1:>2} " + " ".join(cells))
    return "\n".join(lines)


class GomokuService:
    def __init__(self, store, file_root: Path | None = None):
        self.store = store
        self.file_root = file_root
        if file_root: file_root.mkdir(parents=True, exist_ok=True)

    def _pvp_path(self, group_id):
        return self.file_root / f"group-{int(group_id)}.json" if self.file_root and group_id else None

    def _pvp_load(self, group_id):
        path = self._pvp_path(group_id)
        if not path or not path.is_file() or path.is_symlink(): return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _pvp_save(self, group_id, game):
        path = self._pvp_path(group_id); temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(game), encoding="utf-8"); temporary.replace(path)

    def _pvp_delete(self, group_id):
        path = self._pvp_path(group_id)
        if path: path.unlink(missing_ok=True)

    async def command(self, message, text):
        bare_move = text.upper().replace(" ", "")
        coordinate = bool(re.fullmatch(r"[A-O](?:[1-9]|1[0-5])", bare_move))
        if not (text.startswith("/五子棋") or text.startswith("/落子") or (message.mentioned and coordinate)):
            return None
        key = message.conversation_id
        arg = (text.replace("/五子棋", "", 1).strip() if text.startswith("/五子棋") else
               text.replace("/落子", "", 1).strip() if text.startswith("/落子") else bare_move)
        if arg in {"", "帮助"}:
            return ("五子棋：/五子棋 开始（人机）；/五子棋 对战 QQ号；/五子棋 加入；"
                    "/落子 H8，或@本鱼直接说 H8；/五子棋 棋盘；/五子棋 结束。")
        if message.kind == "group" and arg.startswith("对战"):
            target = arg.replace("对战", "", 1).strip()
            if target and not target.isdigit(): return "用法：/五子棋 对战 QQ号；也可不填QQ号等待群友加入。"
            game = {"board": [["."]*SIZE for _ in range(SIZE)], "black": message.user_id,
                    "white": int(target) if target else 0, "turn": "X"}
            self._pvp_save(message.group_id, game)
            return (f"双人棋局已创建，QQ{message.user_id} 执黑。" +
                    (f"等待 QQ{target} 落子。" if target else "群友发送 /五子棋 加入 即可执白。"))
        if message.kind == "group" and arg == "加入":
            game = self._pvp_load(message.group_id)
            if not game: return "本群没有等待中的双人棋局。"
            if game["white"] and game["white"] != message.user_id: return "这盘已经有对手啦。"
            if game["black"] == message.user_id: return "你已经执黑，等另一位群友加入。"
            game["white"] = message.user_id; self._pvp_save(message.group_id, game)
            return f"QQ{message.user_id} 加入并执白，黑棋先走。\n" + _render(game["board"])
        if arg == "开始":
            board = [["."]*SIZE for _ in range(SIZE)]
            self.store.save_game(key, board)
            return "开局，你执黑 ●。用 /落子 H8。\n" + _render(board)
        if arg == "结束":
            pvp = self._pvp_load(message.group_id)
            if pvp and message.user_id in {pvp["black"], pvp["white"]}:
                self._pvp_delete(message.group_id); return "这盘双人棋局收起来啦。"
            self.store.delete_game(key); return "这盘收起来啦。"
        pvp = self._pvp_load(message.group_id) if message.kind == "group" else None
        if pvp and arg == "棋盘":
            return _render(pvp["board"]) + f"\n当前轮到 {'黑棋' if pvp['turn'] == 'X' else '白棋'}。"
        pvp_move = arg.upper().replace(" ", "")
        if pvp and re.fullmatch(r"[A-O](?:[1-9]|1[0-5])", pvp_move):
            if not pvp["white"]:
                return "还在等待另一位群友加入。"
            stone = "X" if message.user_id == pvp["black"] else "O" if message.user_id == pvp["white"] else ""
            if not stone: return "你不是这盘棋的玩家。"
            if stone != pvp["turn"]: return "还没轮到你。"
            x, y = COLS.index(pvp_move[0]), int(pvp_move[1:])-1
            if pvp["board"][y][x] != ".": return "这个位置已经有棋子了。"
            pvp["board"][y][x] = stone
            if _win(pvp["board"], stone):
                self._pvp_delete(message.group_id)
                return _render(pvp["board"], (x,y)) + f"\nQQ{message.user_id} 赢了！"
            pvp["turn"] = "O" if stone == "X" else "X"; self._pvp_save(message.group_id, pvp)
            return _render(pvp["board"], (x,y)) + f"\nQQ{message.user_id} 落在 {pvp_move}。"
        board = self.store.load_game(key)
        if board is None: return "还没开局，用 /五子棋 开始。"
        if arg == "棋盘": return _render(board)
        move = arg.upper().replace(" ", "")
        if len(move) < 2 or move[0] not in COLS or not move[1:].isdigit(): return "落子格式例如：/落子 H8"
        x, y = COLS.index(move[0]), int(move[1:])-1
        if not 0 <= y < SIZE or board[y][x] != ".": return "这个位置不能下，换一格吧。"
        board[y][x] = "X"
        if _win(board, "X"): self.store.delete_game(key); return _render(board) + "\n你赢了，本鱼认输。"
        choices = [(x, y) for y in range(SIZE) for x in range(SIZE) if board[y][x] == "." and any(
            0 <= x+dx < SIZE and 0 <= y+dy < SIZE and board[y+dy][x+dx] != "." for dx in (-1,0,1) for dy in (-1,0,1))]
        best = max(choices, key=lambda p: (_score(board, *p, "O"), random.random()))
        board[best[1]][best[0]] = "O"; self.store.save_game(key, board)
        suffix = f"\n本鱼落在 {COLS[best[0]]}{best[1]+1}。"
        if _win(board, "O"): self.store.delete_game(key); suffix += "这盘本鱼赢啦。"
        return _render(board, best) + suffix
