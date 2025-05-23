from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends, Response
from pydantic import BaseModel
import uuid
from xread.security.auth import AuthManager, security
from xread.security.rate_limiter import RateLimiter
from xread.security_patches import SecurityValidator

app = FastAPI(title="XReader API", version="2.0.0")

# Initialize security components
auth_manager = AuthManager(secret_key="your-secret-key-here")  # Replace with environment variable in production
rate_limiter = RateLimiter(max_requests=100, window=3600)  # 100 requests per hour

class ScrapeRequest(BaseModel):
    url: str
    ai_model: str = "perplexity"
    priority: str = "normal"

@app.post("/scrape/async")
async def scrape_async(request: ScrapeRequest, user_id: str = Depends(auth_manager.verify_token)):
    """Queue URL for background processing"""
    # Rate limiting
    allowed, remaining = await rate_limiter.is_allowed(user_id)
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    # Validate URL
    if not SecurityValidator.validate_url(request.url):
        raise HTTPException(status_code=400, detail="Invalid or unauthorized URL")
    
    task = scrape_url_task.delay(request.url)
    return {"task_id": task.id, "status": "queued", "rate_limit_remaining": remaining}

@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str, user_id: str = Depends(auth_manager.verify_token)):
    """Get task status and results"""
    # Rate limiting
    allowed, remaining = await rate_limiter.is_allowed(user_id)
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    task = scrape_url_task.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": task.status,
        "result": task.result if task.ready() else None,
        "rate_limit_remaining": remaining
    }

@app.post("/login")
async def login(response: Response):
    """Generate a token for a user (simplified - implement proper user validation in production)"""
    user_id = "user-" + str(uuid.uuid4())  # Simplified user ID generation
    token = auth_manager.create_token(user_id)
    response.set_cookie(key="auth-token", value=token, httponly=True, secure=True)
    return {"message": "Logged in", "user_id": user_id}
