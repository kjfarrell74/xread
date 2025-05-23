import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Tuple

class RateLimiter:
    def __init__(self, max_requests: int = 100, window: int = 3600):
        self.max_requests = max_requests
        self.window = window
        self.requests: Dict[str, List[datetime]] = defaultdict(list)
    
    async def is_allowed(self, identifier: str) -> Tuple[bool, int]:
        """Check if request is allowed, return (allowed, remaining)"""
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=self.window)
        
        # Clean old requests
        self.requests[identifier] = [
            req_time for req_time in self.requests[identifier]
            if req_time > window_start
        ]
        
        current_requests = len(self.requests[identifier])
        
        if current_requests >= self.max_requests:
            return False, 0
        
        self.requests[identifier].append(now)
        return True, self.max_requests - current_requests - 1
