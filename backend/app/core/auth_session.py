import time
from typing import Dict
from sqlalchemy.orm import Session
from app.core.redis_client import get_redis
from app.models.domain import PlanConfig

class AuthSessionManager:
    def __init__(self):
        # Fallback in-memory store if Redis is unavailable
        # Structure: { user_id: { jti: timestamp, ... } }
        self._memory_store: Dict[int, Dict[str, float]] = {}

    def get_max_sessions(self, db: Session, plan_type: str) -> int:
        plan = db.query(PlanConfig).filter(PlanConfig.plan_type == plan_type).first()
        if plan:
            return plan.max_sessions
        # Default fallback
        if plan_type == "premium": return 10
        if plan_type == "pro": return 5
        return 2

    def add_session(self, db: Session, user_id: int, jti: str, plan_type: str):
        max_sess = self.get_max_sessions(db, plan_type)
        redis = get_redis()
        current_time = time.time()
        
        if redis:
            key = f"auth:sessions:{user_id}"
            # Add new session
            redis.zadd(key, {jti: current_time})
            # Get total count
            count = redis.zcard(key)
            if count > max_sess:
                # Remove oldest elements (lowest scores)
                to_remove = count - max_sess
                redis.zremrangebyrank(key, 0, to_remove - 1)
        else:
            # In-memory fallback
            if user_id not in self._memory_store:
                self._memory_store[user_id] = {}
            
            self._memory_store[user_id][jti] = current_time
            
            if len(self._memory_store[user_id]) > max_sess:
                # Sort by timestamp and remove oldest
                sorted_sessions = sorted(self._memory_store[user_id].items(), key=lambda x: x[1])
                to_remove = len(self._memory_store[user_id]) - max_sess
                for oldest_jti, _ in sorted_sessions[:to_remove]:
                    del self._memory_store[user_id][oldest_jti]

    def is_session_valid(self, user_id: int, jti: str) -> bool:
        redis = get_redis()
        if redis:
            key = f"auth:sessions:{user_id}"
            score = redis.zscore(key, jti)
            return score is not None
        else:
            # In-memory fallback
            user_sessions = self._memory_store.get(user_id, {})
            return jti in user_sessions

    def revoke_session(self, user_id: int, jti: str):
        redis = get_redis()
        if redis:
            key = f"auth:sessions:{user_id}"
            redis.zrem(key, jti)
        else:
            # In-memory fallback
            if user_id in self._memory_store and jti in self._memory_store[user_id]:
                del self._memory_store[user_id][jti]

    def revoke_all(self, user_id: int, keep_jti: str | None = None):
        """ออกจากระบบทุกอุปกรณ์ (เว้น keep_jti) — ใช้หลังเปลี่ยน/รีเซ็ตรหัสผ่าน"""
        redis = get_redis()
        if redis:
            key = f"auth:sessions:{user_id}"
            for member in redis.zrange(key, 0, -1):
                jti = member.decode() if isinstance(member, bytes) else member
                if jti != keep_jti:
                    redis.zrem(key, member)
        else:
            sessions = self._memory_store.get(user_id, {})
            for jti in list(sessions):
                if jti != keep_jti:
                    del sessions[jti]


auth_session_manager = AuthSessionManager()
