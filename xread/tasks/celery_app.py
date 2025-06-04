from celery import Celery
import asyncio
import time

from xread.pipeline import ScraperPipeline
from xread.data_manager import AsyncDataManager

app = Celery('xread')
app.config_from_object('xread.settings.celery_config')

@app.task(bind=True, max_retries=3)
def scrape_url_task(self, url: str) -> dict:
    """Background task for URL scraping"""
    try:
        pipeline = ScraperPipeline(AsyncDataManager())
        result = asyncio.run(pipeline.run(url))
        return {"status": "success", "data": result}
    except Exception as exc:
        self.retry(countdown=60, exc=exc)

@app.task
def batch_scrape_task(urls: list) -> dict:
    """Process multiple URLs in background"""
    results = []
    for url in urls:
        result = scrape_url_task.delay(url)
        results.append(result.id)
    return {"batch_id": f"batch_{int(time.time())}", "task_ids": results}
