from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
import uuid

app = FastAPI(title="XReader API", version="2.0.0")

class ScrapeRequest(BaseModel):
    url: str
    ai_model: str = "perplexity"
    priority: str = "normal"

@app.post("/scrape/async")
async def scrape_async(request: ScrapeRequest):
    """Queue URL for background processing"""
    task = scrape_url_task.delay(request.url)
    return {"task_id": task.id, "status": "queued"}

@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Get task status and results"""
    task = scrape_url_task.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": task.status,
        "result": task.result if task.ready() else None
    }
