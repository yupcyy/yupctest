"""SQLite backed conversation history + explicit, owner-scoped facts."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


class SQLiteMemoryStore:
    def __init__(self, path: str | Path, max_turns: int = 10):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.max_items = max(1, max_turns) * 2
        self.db = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        self.db.execute('PRAGMA busy_timeout=10000')
        self.db.execute('PRAGMA journal_mode=WAL')
        with self.lock, self.db:
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS group_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
                    content TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_group_observations ON group_observations(group_id,id);
                CREATE TABLE IF NOT EXISTS proactive_state (
                    group_id INTEGER PRIMARY KEY, last_sent REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_conv_history
                ON conversation_messages(conversation_id, id);
                CREATE TABLE IF NOT EXISTS user_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_user_memories
                ON user_memories(user_id, id);
                CREATE TABLE IF NOT EXISTS chat_preferences (
                    scope TEXT NOT NULL, target_id INTEGER NOT NULL, name TEXT NOT NULL,
                    value TEXT NOT NULL, PRIMARY KEY(scope,target_id,name)
                );
                CREATE TABLE IF NOT EXISTS gomoku_games (
                    conversation_id TEXT PRIMARY KEY, board TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS owner_style_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS user_affinity (
                    user_id INTEGER PRIMARY KEY,
                    score INTEGER NOT NULL CHECK(score BETWEEN -100 AND 100),
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS interaction_guard (
                    user_id INTEGER PRIMARY KEY,
                    blocked INTEGER NOT NULL DEFAULT 0,
                    window_start REAL NOT NULL DEFAULT 0,
                    call_count INTEGER NOT NULL DEFAULT 0,
                    reason TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS sleep_sessions (
                    user_id INTEGER PRIMARY KEY,
                    slept_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS affinity_daily_gifts (
                    user_id INTEGER NOT NULL,
                    gift_day TEXT NOT NULL,
                    gift_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(user_id,gift_day)
                );
            ''')

    def get(self, conversation_id: str) -> list[dict[str, str]]:
        with self.lock:
            rows = self.db.execute('''
                SELECT role,content FROM (
                    SELECT id, role, content FROM conversation_messages
                    WHERE conversation_id=? ORDER BY id DESC LIMIT ?
                ) ORDER BY id ASC
            ''', (conversation_id,self.max_items)).fetchall()
        return [{'role':role, 'content':content} for role,content in rows]

    def append_exchange(self, conversation_id: str, user: str, assistant: str) -> None:
        with self.lock, self.db:
            self.db.executemany(
                'INSERT INTO conversation_messages(conversation_id,role,content) VALUES (?,?,?)',
                [(conversation_id,'user',user),(conversation_id,'assistant',assistant)])
            self.db.execute('''
                DELETE FROM conversation_messages WHERE conversation_id=? AND id NOT IN (
                    SELECT id FROM conversation_messages WHERE conversation_id=?
                    ORDER BY id DESC LIMIT ?
                )
            ''',(conversation_id,conversation_id,self.max_items))

    def clear(self, conversation_id: str) -> None:
        with self.lock, self.db:
            self.db.execute('DELETE FROM conversation_messages WHERE conversation_id=?',(conversation_id,))

    def add_memory(self, user_id: int, content: str, max_memories: int = 30) -> int:
        content=content.strip()
        if not content or len(content)>400:
            raise ValueError('Memory length must be 1-400 characters')
        with self.lock, self.db:
            count=self.db.execute('SELECT COUNT(*) FROM user_memories WHERE user_id=?',(user_id,)).fetchone()[0]
            if count>=max_memories:
                raise ValueError('Memory limit reached')
            cur=self.db.execute('INSERT INTO user_memories(user_id,content) VALUES (?,?)',(user_id,content))
            return int(cur.lastrowid)

    def list_memories(self,user_id:int,limit:int=30)->list[tuple[int,str]]:
        with self.lock:
            return [(int(i),c) for i,c in self.db.execute(
                'SELECT id,content FROM user_memories WHERE user_id=? ORDER BY id DESC LIMIT ?',
                (user_id,limit)).fetchall()]

    def delete_memory(self,user_id:int,memory_id:int)->bool:
        with self.lock,self.db:
            cursor=self.db.execute('DELETE FROM user_memories WHERE user_id=? AND id=?',(user_id,memory_id))
            return cursor.rowcount>0

    def close(self)->None:
        with self.lock:
            self.db.close()

    def observe(self, group_id, user_id, content):
        with self.lock, self.db:
            self.db.execute('INSERT INTO group_observations(group_id,user_id,content) VALUES (?,?,?)',
                            (group_id, user_id, content[:1000]))
            self.db.execute('DELETE FROM group_observations WHERE group_id=? AND id NOT IN '
                '(SELECT id FROM group_observations WHERE group_id=? ORDER BY id DESC LIMIT 40)',
                (group_id, group_id))

    def group_context(self, group_id):
        with self.lock:
            rows = self.db.execute('SELECT user_id,content FROM (SELECT id,user_id,content '
                'FROM group_observations WHERE group_id=? ORDER BY id DESC LIMIT 20) ORDER BY id',
                (group_id,)).fetchall()
        return '\n'.join(f'QQ{uid}: {content}' for uid, content in rows)

    def reserve_proactive(self, group_id, now, cooldown):
        with self.lock, self.db:
            row = self.db.execute('SELECT last_sent FROM proactive_state WHERE group_id=?', (group_id,)).fetchone()
            if row and now - row[0] < cooldown:
                return False
            self.db.execute('INSERT OR REPLACE INTO proactive_state VALUES (?,?)', (group_id, now))
            return True

    def preference(self, scope, target_id, name, default):
        with self.lock:
            row = self.db.execute('SELECT value FROM chat_preferences WHERE scope=? AND target_id=? AND name=?',
                                  (scope,target_id,name)).fetchone()
        return row[0] if row else default

    def set_preference(self, scope, target_id, name, value):
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO chat_preferences VALUES (?,?,?,?)',
                            (scope,target_id,name,value))

    def save_game(self, conversation_id, board):
        import json
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO gomoku_games(conversation_id,board) VALUES (?,?)',
                            (conversation_id,json.dumps(board)))

    def load_game(self, conversation_id):
        import json
        with self.lock:
            row=self.db.execute('SELECT board FROM gomoku_games WHERE conversation_id=?',(conversation_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def delete_game(self, conversation_id):
        with self.lock,self.db: self.db.execute('DELETE FROM gomoku_games WHERE conversation_id=?',(conversation_id,))

    def add_style_sample(self, content, limit=12):
        content = " ".join(content.strip().split())[:80]
        if not content: return
        with self.lock, self.db:
            self.db.execute('INSERT INTO owner_style_samples(content) VALUES (?)', (content,))
            self.db.execute('DELETE FROM owner_style_samples WHERE id NOT IN '
                            '(SELECT id FROM owner_style_samples ORDER BY id DESC LIMIT ?)', (limit,))

    def style_samples(self, limit=4):
        with self.lock:
            return [row[0] for row in self.db.execute(
                'SELECT content FROM owner_style_samples ORDER BY id DESC LIMIT ?', (limit,)).fetchall()]

    def affinity(self, user_id, default=0):
        with self.lock:
            row = self.db.execute('SELECT score FROM user_affinity WHERE user_id=?',(user_id,)).fetchone()
        return int(row[0]) if row else int(default)

    def ensure_affinity(self, user_id, default=0):
        with self.lock, self.db:
            self.db.execute('INSERT OR IGNORE INTO user_affinity(user_id,score) VALUES (?,?)',
                            (user_id, max(-100, min(100, int(default)))))
        return self.affinity(user_id, default)

    def adjust_affinity(self, user_id, delta, default=0):
        with self.lock, self.db:
            current = self.affinity(user_id, default)
            score = max(-100, min(100, current + int(delta)))
            self.db.execute('INSERT OR REPLACE INTO user_affinity(user_id,score,updated_at) '
                            'VALUES (?,?,CURRENT_TIMESTAMP)', (user_id,score))
            return score

    def set_affinity(self, user_id, score, *, unblock=False):
        score = max(-100, min(100, int(score)))
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO user_affinity(user_id,score,updated_at) '
                            'VALUES (?,?,CURRENT_TIMESTAMP)', (user_id,score))
            if unblock:
                self.db.execute('INSERT INTO interaction_guard(user_id,blocked,window_start,call_count,reason) '
                                "VALUES (?,0,0,0,'') ON CONFLICT(user_id) DO UPDATE SET "
                                "blocked=0,window_start=0,call_count=0,reason=''", (user_id,))
        return score

    def list_affinities(self):
        with self.lock:
            return [(int(uid),int(score),bool(blocked),reason) for uid,score,blocked,reason in self.db.execute(
                'SELECT a.user_id,a.score,COALESCE(g.blocked,0),COALESCE(g.reason,\'\') '
                'FROM user_affinity a LEFT JOIN interaction_guard g ON g.user_id=a.user_id '
                'ORDER BY a.score DESC,a.user_id').fetchall()]

    def unblock_user(self, user_id):
        with self.lock,self.db:
            cursor=self.db.execute("UPDATE interaction_guard SET blocked=0,reason='' WHERE user_id=?",(user_id,))
            return cursor.rowcount > 0

    def claim_daily_gift(self, user_id, day, limit=3):
        with self.lock,self.db:
            row=self.db.execute('SELECT gift_count FROM affinity_daily_gifts WHERE user_id=? AND gift_day=?',
                                (user_id,day)).fetchone()
            count=int(row[0]) if row else 0
            if count >= limit: return False, count
            count += 1
            self.db.execute('INSERT OR REPLACE INTO affinity_daily_gifts VALUES (?,?,?)',(user_id,day,count))
            return True, count

    def record_interaction(self, user_id, now, window=60):
        with self.lock, self.db:
            row = self.db.execute('SELECT window_start,call_count FROM interaction_guard WHERE user_id=?',
                                  (user_id,)).fetchone()
            start, count = (row if row else (now, 0))
            if now - start > window: start, count = now, 0
            count += 1
            self.db.execute('INSERT INTO interaction_guard(user_id,window_start,call_count) VALUES (?,?,?) '
                            'ON CONFLICT(user_id) DO UPDATE SET window_start=excluded.window_start, '
                            'call_count=excluded.call_count', (user_id,start,count))
            return count

    def guard_status(self, user_id):
        with self.lock:
            row = self.db.execute('SELECT blocked,reason FROM interaction_guard WHERE user_id=?',
                                  (user_id,)).fetchone()
        return (bool(row[0]), row[1]) if row else (False, '')

    def block_user(self, user_id, reason):
        with self.lock, self.db:
            was = self.guard_status(user_id)[0]
            self.db.execute('INSERT INTO interaction_guard(user_id,blocked,reason) VALUES (?,1,?) '
                            'ON CONFLICT(user_id) DO UPDATE SET blocked=1,reason=excluded.reason',
                            (user_id,reason[:120]))
            return not was

    def start_sleep(self, user_id, now):
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO sleep_sessions(user_id,slept_at) VALUES (?,?)',(user_id,now))

    def finish_sleep(self, user_id, now):
        with self.lock, self.db:
            row=self.db.execute('SELECT slept_at FROM sleep_sessions WHERE user_id=?',(user_id,)).fetchone()
            if not row: return None
            self.db.execute('DELETE FROM sleep_sessions WHERE user_id=?',(user_id,))
            return max(0.0, now-float(row[0]))
