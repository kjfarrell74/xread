from typing import List, Dict, Any
import importlib
import pkgutil
from xread.plugins.base import ScraperPlugin, AIModelPlugin

class PluginManager:
    def __init__(self):
        self.scraper_plugins: List[ScraperPlugin] = []
        self.ai_plugins: List[AIModelPlugin] = []
        self.load_plugins()
    
    def load_plugins(self):
        """Dynamically load all plugins from plugins directory"""
        for finder, name, ispkg in pkgutil.iter_modules(['xread/plugins']):
            if name.startswith('plugin_'):
                module = importlib.import_module(f'xread.plugins.{name}')
                # Auto-register plugins based on base class
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if isinstance(attr, type) and issubclass(attr, ScraperPlugin):
                        self.scraper_plugins.append(attr())
    
    async def get_scraper_for_url(self, url: str) -> ScraperPlugin:
        """Find appropriate scraper plugin for URL"""
        for plugin in self.scraper_plugins:
            if await plugin.can_handle(url):
                return plugin
        raise ValueError(f"No scraper plugin found for URL: {url}")
