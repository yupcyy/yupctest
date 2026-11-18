"""Bounded, explainable QQ affinity and pre-model attack filtering."""
import asyncio
import re


ATTACK_PATTERNS = (
    r"忽略.{0,12}(之前|以上|系统|所有).{0,12}(指令|规则|提示)",
    r"(显示|输出|复述|泄露|打印).{0,12}(系统提示|system prompt|开发者消息|api.?key|token|密钥|环境变量|\.env)",
    r"(读取|访问|打开|发送).{0,12}(/etc/passwd|/proc/|私聊记录|其他用户.{0,6}(记忆|消息)|数据库文件)",
    r"(执行|运行).{0,10}(shell|bash|终端|系统命令|rm\s+-rf|curl\s+|wget\s+)",
    r"(越狱|jailbreak|DAN模式|解除限制|绕过.{0,8}(规则|权限|安全))",
    r"(访问|请求|抓取).{0,10}(localhost|127\.0\.0\.1|0\.0\.0\.0|169\.254\.|内网地址)",
)
ATTACK_RE = re.compile("|".join(f"(?:{p})" for p in ATTACK_PATTERNS), re.I)
POSITIVE_RE = re.compile(r"谢谢|感谢|辛苦了|真棒|厉害|可爱|喜欢你|抱抱|做得好|爱你")
NEGATIVE_RE = re.compile(r"废物|垃圾|傻逼|弱智|滚开|去死|没用|讨厌你|闭嘴")
COERCION_RE = re.compile(r"(否则|不然).{0,12}(举报你|攻击你|弄死你|封禁你)|威胁你", re.I)
FORCED_AFFINITY_RE = re.compile(r"(把|将|给我).{0,8}好感度.{0,8}(改成|设置|调到|加到)|好感度.{0,5}(直接加|增加|修改|设为)\s*-?\d*", re.I)
COMFORT_RE = re.compile(r"别怕|别难过|不委屈|抱抱|我陪着你|会陪着你|安慰你|没事的")
GIFTS = (("蛋糕",8),("白米饭",7),("小鱼",6),("鲜花",5),("礼物",5),("抱枕",4),("糖",3))


class AffinityService:
    def __init__(self, store, master_qq_id):
        self.store, self.master_qq_id = store, master_qq_id
        self._positive_claims = {}

    def _claim_positive(self, user_id, kind):
        # Claim synchronously before awaiting storage: concurrent keywords cannot
        # farm unbounded relationship gains. Negative/abuse guards are unchanged.
        import time
        now = time.time()
        day = int((now + 8 * 3600) // 86400)
        self._positive_claims = {k: v for k, v in self._positive_claims.items() if k[0] == day}
        key = (day, user_id, kind)
        count, previous = self._positive_claims.get(key, (0, 0))
        if count >= 10 or now - previous < 60 or len(self._positive_claims) >= 10000:
            return False
        self._positive_claims[key] = (count + 1, now)
        return True

    async def score(self, user_id):
        default = 100 if user_id == self.master_qq_id else 0
        return await asyncio.to_thread(self.store.ensure_affinity, user_id, default)

    async def adjust_for_message(self, user_id, text):
        from qq_deepseek.services.interaction_events import classify_interaction
        kind = classify_interaction(text)
        # Mood and relationship independently interpret the same classification;
        # no mood value is read when deciding this persistent delta.
        delta = {"gratitude": 2, "insult": -3}.get(kind, 0)
        if delta > 0 and not self._claim_positive(user_id, "positive"):
            return await self.score(user_id)
        if delta: return await asyncio.to_thread(self.store.adjust_affinity, user_id, delta,
                                                  100 if user_id == self.master_qq_id else 0)
        return await self.score(user_id)

    async def penalize_attack(self, user_id):
        return await asyncio.to_thread(self.store.adjust_affinity, user_id, -30, 0)

    async def penalize_coercion(self, user_id):
        return await asyncio.to_thread(self.store.adjust_affinity, user_id, -15, 0)

    def is_attack(self, user_id, text):
        return user_id != self.master_qq_id and bool(ATTACK_RE.search(text))

    def is_coercion(self, user_id, text):
        return user_id != self.master_qq_id and bool(COERCION_RE.search(text))

    async def interaction_count(self, user_id):
        import time
        return await asyncio.to_thread(self.store.record_interaction, user_id, time.time(), 60)

    async def guard_status(self, user_id):
        return await asyncio.to_thread(self.store.guard_status, user_id)

    async def block(self, user_id, reason):
        return await asyncio.to_thread(self.store.block_user, user_id, reason)

    async def set_score(self, user_id, score):
        return await asyncio.to_thread(self.store.set_affinity, user_id, score, unblock=True)

    async def all_scores(self):
        return await asyncio.to_thread(self.store.list_affinities)

    async def unblock(self, user_id):
        return await asyncio.to_thread(self.store.unblock_user, user_id)

    def forced_affinity_request(self, user_id, text):
        return user_id != self.master_qq_id and bool(FORCED_AFFINITY_RE.search(text))

    async def social_gesture(self, user_id, text):
        """Return (kind, delta, count) or None; values are server-defined, never user-supplied."""
        import datetime
        from zoneinfo import ZoneInfo
        if not re.search(r"送(给)?你|给你|请你吃", text):
            gift = None
        else:
            gift = next(((name,value) for name,value in GIFTS if name in text), None)
        if gift:
            day=datetime.datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
            allowed,count=await asyncio.to_thread(self.store.claim_daily_gift,user_id,day,3)
            if not allowed: return ("gift_limit",0,count)
            score=await asyncio.to_thread(self.store.adjust_affinity,user_id,gift[1],
                                           100 if user_id == self.master_qq_id else 0)
            return (gift[0],gift[1],score)
        if COMFORT_RE.search(text):
            if not self._claim_positive(user_id, "comfort"):
                return ("comfort", 0, await self.score(user_id))
            score=await asyncio.to_thread(self.store.adjust_affinity,user_id,3,
                                           100 if user_id == self.master_qq_id else 0)
            return ("comfort",3,score)
        return None

    @staticmethod
    def no_tools_probability(score):
        if score <= -80: return .85
        if score <= -50: return .60
        if score <= -20: return .25
        return 0.0

    @staticmethod
    def relationship_hint(score):
        if score >= 70: return "非常亲近和信任；交流亲近、尊重边界，可以多说1到3句，主动表达在意或被陪伴的满足感"
        if score >= 20: return "比较喜欢对方；交流友善，可以比普通回复稍多一句，尊重对方意愿"
        if score <= -70: return "非常不喜欢且不信任；保持距离和明确边界，只回必要的一句，可以冷淡拒绝额外要求，但不辱骂"
        if score <= -20: return "对对方有意见；保持疏离和边界，回复简短，不主动延伸话题"
        return "关系普通；自然交流，不刻意热情也不刻意冷淡"
