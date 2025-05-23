import aiohttp
import asyncio
from aiolimiter import AsyncLimiter

class RateLimitedHTTPClient:
    def __init__(self, rate_limit: int = 10, per_seconds: int = 60):
        self.rate_limiter = AsyncLimiter(rate_limit, per_seconds)
        self.session = None
    
    async def __aenter__(self):
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=10,
            ttl_dns_cache=300,
            use_dns_cache=True
        )
        self.session = aiohttp.ClientSession(connector=connector)
        return self
    
    async def request(self, method: str, url: str, **kwargs):
        async with self.rate_limiter:
            async with self.session.request(method, url, **kwargs) as response:
                return await response.json()
