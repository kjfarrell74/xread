from celery import Celery

app = Celery('xread')
app.config_from_object('xread.settings.celery_config')

@app.task
async def process_url_task(url: str) -> dict:
    """Background task for URL processing"""
    pipeline = ScraperPipeline()
    result = await pipeline.run(url)
    return {"status": "completed", "data": result}

@app.task
async def bulk_analysis_task(urls: list) -> dict:
    """Background task for bulk URL analysis"""
    results = []
    for url in urls:
        result = await process_url_task.delay(url)
        results.append(result)
    return {"processed": len(results), "results": results}
