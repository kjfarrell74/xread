from xread.plugins.base import ScraperPlugin
from xread.models import ScrapedData

class MastodonPlugin(ScraperPlugin):
    async def can_handle(self, url: str) -> bool:
        return 'mastodon' in url or '@' in url
    
    async def scrape(self, url: str) -> ScrapedData:
        # Implement Mastodon scraping
        pass
