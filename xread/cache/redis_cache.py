import aioredis
import json
import hashlib
from typing import Optional, Any, Union
from datetime import timedelta

class RedisCache:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis: Optional[aioredis.Redis] = None
    
    async def connect(self):
        self.redis = await aioredis.from_url(self.redis_url)
    
    async def get(self, key: str) -> Optional[Any]:
        if not self.redis:
            await self.connect()
        
        value = await self.redis.get(key)
        if value:
            return json.loads(value)
        return None
    
    async def set(self, key: str, value: Any, ttl: Union[int, timedelta] = 3600):
        if not self.redis:
            await self.connect()
        
        if isinstance(ttl, timedelta):
            ttl = int(ttl.total_seconds())
        
        await self.redis.setex(key, ttl, json.dumps(value, default=str))
    
    def cache_key(self, prefix: str, *args) -> str:
        """Generate cache key from prefix and arguments"""
        key_data = f"{prefix}:{':'.join(str(arg) for arg in args)}"
        return hashlib.md5(key_data.encode()).hexdigest()
