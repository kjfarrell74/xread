from abc import ABC, abstractmethod
from xread.models import ScrapedData

class ScraperPlugin(ABC):
    @abstractmethod
    async def can_handle(self, url: str) -> bool:
        pass
    
    @abstractmethod
    async def scrape(self, url: str) -> ScrapedData:
        pass

class AIModelPlugin(ABC):
    @abstractmethod
    async def generate_report(self, data: ScrapedData) -> str:
        pass
