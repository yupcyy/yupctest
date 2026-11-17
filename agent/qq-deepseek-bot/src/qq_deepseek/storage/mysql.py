"""Runtime MySQL stores. All SQL is fixed to agent_ tables; no arbitrary SQL API."""
import json, threading
from urllib.parse import urlsplit

import pymysql

from qq_deepseek.core.usage import TokenUsage


def connection_config(url, username, password):
    if url.startswith("jdbc:"): url=url[5:]
    parsed=urlsplit(url)
    if parsed.scheme not in {"mysql","mariadb"} or not parsed.hostname or not parsed.path.strip("/"):
        raise ValueError("DATABASE_URL must identify one MySQL database")
    return dict(host=parsed.hostname,port=parsed.port or 3306,database=parsed.path.strip("/"),
                user=username or parsed.username,password=password or parsed.password,charset="utf8mb4",
                autocommit=False,connect_timeout=10,read_timeout=20,write_timeout=20)


class _MySQLBase:
    def __init__(self,url,username,password):
        self.lock=threading.RLock(); self.db=pymysql.connect(**connection_config(url,username,password))
    def _ping(self): self.db.ping(reconnect=True)
    def close(self):
        with self.lock: self.db.close()


class MySQLMemoryStore(_MySQLBase):
    def __init__(self,url,username,password,max_turns=10):
        super().__init__(url,username,password); self.max_items=max(1,max_turns)*2
    def get(self,cid):
        with self.lock:
            self._ping()
            with self.db.cursor() as c:
                c.execute("SELECT role,content FROM (SELECT id,role,content FROM agent_conversation_messages WHERE conversation_id=%s ORDER BY id DESC LIMIT %s) x ORDER BY id",(cid,self.max_items)); rows=c.fetchall()
        return [{"role":r,"content":v} for r,v in rows]
    def append_exchange(self,cid,user,assistant):
        with self.lock,self.db.cursor() as c:
            self._ping(); c.executemany("INSERT INTO agent_conversation_messages(conversation_id,role,content) VALUES (%s,%s,%s)",[(cid,"user",user),(cid,"assistant",assistant)])
            c.execute("DELETE FROM agent_conversation_messages WHERE conversation_id=%s AND id NOT IN (SELECT id FROM (SELECT id FROM agent_conversation_messages WHERE conversation_id=%s ORDER BY id DESC LIMIT %s) keep_rows)",(cid,cid,self.max_items)); self.db.commit()
    def clear(self,cid):
        with self.lock,self.db.cursor() as c: self._ping(); c.execute("DELETE FROM agent_conversation_messages WHERE conversation_id=%s",(cid,)); self.db.commit()
    def add_memory(self,user_id,content,max_memories=30):
        content=content.strip()
        if not content or len(content)>400: raise ValueError("Memory length must be 1-400 characters")
        with self.lock,self.db.cursor() as c:
            self._ping(); c.execute("SELECT COUNT(*) FROM agent_memories WHERE user_id=%s",(user_id,))
            if c.fetchone()[0]>=max_memories: raise ValueError("Memory limit reached")
            c.execute("INSERT INTO agent_memories(user_id,content) VALUES (%s,%s)",(user_id,content)); self.db.commit(); return int(c.lastrowid)
    def list_memories(self,user_id,limit=30):
        with self.lock,self.db.cursor() as c: self._ping(); c.execute("SELECT id,content FROM agent_memories WHERE user_id=%s ORDER BY id DESC LIMIT %s",(user_id,limit)); return [(int(i),v) for i,v in c.fetchall()]
    def delete_memory(self,user_id,memory_id):
        with self.lock,self.db.cursor() as c: self._ping(); c.execute("DELETE FROM agent_memories WHERE user_id=%s AND id=%s",(user_id,memory_id)); self.db.commit(); return c.rowcount>0
    def observe(self,*_): return None
    def group_context(self,*_): return ""
    def reserve_proactive(self,target_id,now,cooldown):
        scope="private" if int(target_id)<0 else "group"; key=f"proactive:{scope}:{abs(int(target_id))}"
        with self.lock,self.db.cursor() as c:
            self._ping(); c.execute("SELECT last_proactive_at FROM agent_runtime_state WHERE state_key=%s FOR UPDATE",(key,)); row=c.fetchone()
            if row and row[0] is not None and now-float(row[0])<cooldown: self.db.rollback(); return False
            c.execute("INSERT INTO agent_runtime_state(state_key,last_proactive_at) VALUES (%s,%s) ON DUPLICATE KEY UPDATE last_proactive_at=VALUES(last_proactive_at)",(key,now)); self.db.commit(); return True
    def preference(self,scope,target_id,name,default):
        with self.lock,self.db.cursor() as c: self._ping(); c.execute("SELECT value FROM agent_chat_preferences WHERE scope=%s AND target_id=%s AND name=%s",(scope,target_id,name)); row=c.fetchone(); return row[0] if row else default
    def set_preference(self,scope,target_id,name,value):
        with self.lock,self.db.cursor() as c: self._ping(); c.execute("INSERT INTO agent_chat_preferences(scope,target_id,name,value) VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE value=VALUES(value)",(scope,target_id,name,value)); self.db.commit()
    def save_game(self,cid,board):
        key=f"game:{cid}"
        with self.lock,self.db.cursor() as c: self._ping(); c.execute("INSERT INTO agent_runtime_state(state_key,game_board,game_updated_at) VALUES (%s,%s,NOW(6)) ON DUPLICATE KEY UPDATE game_board=VALUES(game_board),game_updated_at=NOW(6)",(key,json.dumps(board))); self.db.commit()
    def load_game(self,cid):
        with self.lock,self.db.cursor() as c: self._ping(); c.execute("SELECT game_board FROM agent_runtime_state WHERE state_key=%s",(f"game:{cid}",)); row=c.fetchone(); return json.loads(row[0]) if row and row[0] is not None else None
    def delete_game(self,cid):
        with self.lock,self.db.cursor() as c: self._ping(); c.execute("DELETE FROM agent_runtime_state WHERE state_key=%s",(f"game:{cid}",)); self.db.commit()
    def add_style_sample(self,content,limit=12):
        content=" ".join(content.strip().split())[:80]
        if not content:return
        with self.lock,self.db.cursor() as c:
            self._ping(); c.execute("INSERT INTO agent_owner_style_samples(content) VALUES (%s)",(content,)); c.execute("DELETE FROM agent_owner_style_samples WHERE id NOT IN (SELECT id FROM (SELECT id FROM agent_owner_style_samples ORDER BY id DESC LIMIT %s) x)",(limit,)); self.db.commit()
    def style_samples(self,limit=4):
        with self.lock,self.db.cursor() as c: self._ping(); c.execute("SELECT content FROM agent_owner_style_samples ORDER BY id DESC LIMIT %s",(limit,)); return [r[0] for r in c.fetchall()]
    def affinity(self,user_id,default=0):
        with self.lock,self.db.cursor() as c: self._ping(); c.execute("SELECT affinity FROM agent_user_state WHERE user_id=%s",(user_id,)); row=c.fetchone(); return int(row[0]) if row else int(default)
    def ensure_affinity(self,user_id,default=0):
        with self.lock,self.db.cursor() as c: self._ping(); c.execute("INSERT IGNORE INTO agent_user_state(user_id,affinity) VALUES (%s,%s)",(user_id,max(-100,min(100,int(default))))); self.db.commit()
        return self.affinity(user_id,default)
    def adjust_affinity(self,user_id,delta,default=0):
        initial=max(-100,min(100,int(default)+int(delta)))
        with self.lock,self.db.cursor() as c:
            self._ping(); c.execute("INSERT INTO agent_user_state(user_id,affinity) VALUES (%s,%s) ON DUPLICATE KEY UPDATE affinity=GREATEST(-100,LEAST(100,affinity+%s))",(user_id,initial,int(delta))); self.db.commit()
            c.execute("SELECT affinity FROM agent_user_state WHERE user_id=%s",(user_id,)); return int(c.fetchone()[0])
    def set_affinity(self,user_id,score,*,unblock=False):
        score=max(-100,min(100,int(score)))
        with self.lock,self.db.cursor() as c:
            self._ping(); c.execute("INSERT INTO agent_user_state(user_id,affinity,blocked,block_reason,rate_window_start,rate_call_count) VALUES (%s,%s,%s,'',0,0) ON DUPLICATE KEY UPDATE affinity=VALUES(affinity)"+(",blocked=FALSE,block_reason='',rate_window_start=0,rate_call_count=0" if unblock else ""),(user_id,score,False)); self.db.commit(); return score
    def list_affinities(self):
        with self.lock,self.db.cursor() as c: self._ping(); c.execute("SELECT user_id,affinity,blocked,block_reason FROM agent_user_state ORDER BY affinity DESC,user_id"); return [(int(a),int(b),bool(d),e) for a,b,d,e in c.fetchall()]
    def unblock_user(self,user_id):
        with self.lock,self.db.cursor() as c: self._ping(); c.execute("UPDATE agent_user_state SET blocked=FALSE,block_reason='' WHERE user_id=%s",(user_id,)); self.db.commit(); return c.rowcount>0
    def claim_daily_gift(self,user_id,day,limit=3):
        with self.lock,self.db.cursor() as c:
            self._ping(); c.execute("INSERT IGNORE INTO agent_user_state(user_id,affinity) VALUES (%s,0)",(user_id,)); c.execute("SELECT gift_day,gift_count FROM agent_user_state WHERE user_id=%s FOR UPDATE",(user_id,)); row=c.fetchone(); count=int(row[1]) if row and str(row[0])==day else 0
            if count>=limit:self.db.rollback();return False,count
            count+=1;c.execute("UPDATE agent_user_state SET gift_day=%s,gift_count=%s WHERE user_id=%s",(day,count,user_id));self.db.commit();return True,count
    def record_interaction(self,user_id,now,window=60):
        with self.lock,self.db.cursor() as c:
            self._ping(); c.execute("INSERT IGNORE INTO agent_user_state(user_id,affinity) VALUES (%s,0)",(user_id,)); c.execute("SELECT rate_window_start,rate_call_count FROM agent_user_state WHERE user_id=%s FOR UPDATE",(user_id,)); start,count=c.fetchone(); start=float(start);count=int(count)
            if now-start>window:start,count=now,0
            count+=1;c.execute("UPDATE agent_user_state SET rate_window_start=%s,rate_call_count=%s WHERE user_id=%s",(start,count,user_id));self.db.commit();return count
    def guard_status(self,user_id):
        with self.lock,self.db.cursor() as c:self._ping();c.execute("SELECT blocked,block_reason FROM agent_user_state WHERE user_id=%s",(user_id,));row=c.fetchone();return (bool(row[0]),row[1]) if row else (False,"")
    def block_user(self,user_id,reason):
        was=self.guard_status(user_id)[0]
        with self.lock,self.db.cursor() as c:self._ping();c.execute("INSERT INTO agent_user_state(user_id,blocked,block_reason) VALUES (%s,TRUE,%s) ON DUPLICATE KEY UPDATE blocked=TRUE,block_reason=VALUES(block_reason)",(user_id,reason[:120]));self.db.commit();return not was
    def start_sleep(self,user_id,now):
        with self.lock,self.db.cursor() as c:self._ping();c.execute("INSERT INTO agent_user_state(user_id,sleep_started_at) VALUES (%s,%s) ON DUPLICATE KEY UPDATE sleep_started_at=VALUES(sleep_started_at)",(user_id,now));self.db.commit()
    def finish_sleep(self,user_id,now):
        with self.lock,self.db.cursor() as c:
            self._ping();c.execute("SELECT sleep_started_at FROM agent_user_state WHERE user_id=%s FOR UPDATE",(user_id,));row=c.fetchone()
            if not row or row[0] is None:self.db.rollback();return None
            elapsed=max(0.0,now-float(row[0]));c.execute("UPDATE agent_user_state SET sleep_started_at=NULL WHERE user_id=%s",(user_id,));self.db.commit();return elapsed


class MySQLUsageStore(_MySQLBase):
    def insert(self,usage):
        with self.lock,self.db.cursor() as c:self._ping();c.execute("INSERT IGNORE INTO agent_llm_usage(request_id,created_at,model,conversation_id,operation,prompt_tokens,completion_tokens,cache_hit_tokens,cache_miss_tokens) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",(usage.request_id,usage.created_at,usage.model,usage.conversation_id,usage.operation,usage.prompt_tokens,usage.completion_tokens,usage.cache_hit_tokens,usage.cache_miss_tokens));self.db.commit();return c.rowcount==1
    def rows(self,*,since=None,until=None,conversation_id=None,limit=10000):
        if not 1<=limit<=100000:raise ValueError("limit must be between 1 and 100000")
        conditions=[];params=[]
        if since is not None:conditions.append("created_at >= %s");params.append(since)
        if until is not None:conditions.append("created_at < %s");params.append(until)
        if conversation_id is not None:conditions.append("conversation_id=%s");params.append(conversation_id)
        query="SELECT request_id,created_at,model,conversation_id,operation,prompt_tokens,completion_tokens,cache_hit_tokens,cache_miss_tokens FROM agent_llm_usage"+(" WHERE "+" AND ".join(conditions) if conditions else "")+" ORDER BY created_at DESC,request_id DESC LIMIT %s";params.append(limit)
        with self.lock,self.db.cursor() as c:self._ping();c.execute(query,params);rows=c.fetchall()
        return [TokenUsage(*r[:4],r[5],r[6],r[7],r[8],r[4]) for r in rows]
