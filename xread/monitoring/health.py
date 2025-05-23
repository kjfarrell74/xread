from fastapi import FastAPI
from typing import Dict, Any
import asyncio

health_app = FastAPI()

@health_app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Comprehensive health check"""
    checks = {
        "database": await check_database(),
        "redis": await check_redis(),
        "ai_apis": await check_ai_apis(),
        "disk_space": check_disk_space()
    }
    
    overall_status = "healthy" if all(checks.values()) else "unhealthy"
    
    return {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "checks": checks
    }

async def check_database() -> bool:
    try:
        manager = AsyncDataManager()
        await manager.initialize()
        return True
    except:
        return False
