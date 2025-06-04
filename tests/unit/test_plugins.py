import pytest
from xread.plugins.manager import PluginManager
from xread.plugins.base import ScraperPlugin, AIModelPlugin

# Mock plugin classes for testing
class MockScraperPlugin(ScraperPlugin):
    async def can_handle(self, url: str) -> bool:
        return url.startswith("http://mock.com")

    async def scrape(self, url: str) -> dict:
        return {"mock_data": True}

class MockAIModelPlugin(AIModelPlugin):
    async def generate_report(self, scraped_data: dict, sid: str) -> str:
        return "Mock report"

def test_plugin_loading():
    manager = PluginManager()
    assert len(manager.scraper_plugins) > 0, "No scraper plugins loaded"
    assert isinstance(manager.ai_plugins, list)

@pytest.mark.asyncio
async def test_get_scraper_for_url():
    manager = PluginManager(extra_plugin_dirs=["tests/mocks"])  # Assume a mock directory for testing
    scraper = await manager.get_scraper_for_url("http://mock.com/example")
    assert scraper is not None, "Scraper not found for mock URL"
    assert isinstance(scraper, ScraperPlugin), "Returned object is not a ScraperPlugin"

@pytest.mark.asyncio
async def test_get_ai_model_plugins():
    manager = PluginManager()
    ai_plugins = manager.get_ai_model_plugins()
    assert isinstance(ai_plugins, list)

# Add more tests as needed based on plugin behavior
