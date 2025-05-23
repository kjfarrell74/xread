from prometheus_client import Counter, Histogram, Gauge, start_http_server
import time
import functools

# Metrics
SCRAPES_TOTAL = Counter('xread_scrapes_total', 'Total scrapes', ['status', 'source'])
SCRAPE_DURATION = Histogram('xread_scrape_duration_seconds', 'Scrape duration')
AI_REQUESTS_TOTAL = Counter('xread_ai_requests_total', 'AI API requests', ['model', 'status'])
ACTIVE_SCRAPES = Gauge('xread_active_scrapes', 'Currently active scrapes')

def track_scrape_metrics(func):
    """Decorator to track scraping metrics"""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        ACTIVE_SCRAPES.inc()
        
        try:
            result = await func(*args, **kwargs)
            SCRAPES_TOTAL.labels(status='success', source='nitter').inc()
            return result
        except Exception as e:
            SCRAPES_TOTAL.labels(status='error', source='nitter').inc()
            raise
        finally:
            ACTIVE_SCRAPES.dec()
            SCRAPE_DURATION.observe(time.time() - start_time)
    
    return wrapper
