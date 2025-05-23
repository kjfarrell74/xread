from typing import List, Dict, Any
import importlib
import pkgutil
from xread.plugins.base import ScraperPlugin, AIModelPlugin

class PluginManager:
    def __init__(self, config: Dict[str, Any] = None, extra_plugin_dirs: List[str] = None):
        self.scraper_plugins: List[ScraperPlugin] = []
        self.ai_plugins: List[AIModelPlugin] = []
        self.config = config or {}
        self.extra_plugin_dirs = extra_plugin_dirs or []
        self.load_plugins()

    def load_plugins(self):
        """Dynamically load all plugins from plugins directory and extra directories"""
        plugin_dirs = ['xread/plugins'] + self.extra_plugin_dirs
        for plugin_dir in plugin_dirs:
            for finder, name, ispkg in pkgutil.iter_modules([plugin_dir]):
                if name.startswith('plugin_'):
                    # Support both xread.plugins and external dirs
                    if plugin_dir == 'xread/plugins':
                        module = importlib.import_module(f'xread.plugins.{name}')
                    else:
                        # External: import by path
                        import importlib.util
                        import os
                        module_path = os.path.join(plugin_dir, f"{name}.py")
                        spec = importlib.util.spec_from_file_location(name, module_path)
                        if not spec or not spec.loader:
                            continue
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                    # Auto-register plugins based on base class
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if isinstance(attr, type):
                            if issubclass(attr, ScraperPlugin) and attr is not ScraperPlugin:
                                self.scraper_plugins.append(self._instantiate_plugin(attr))
                            elif issubclass(attr, AIModelPlugin) and attr is not AIModelPlugin:
                                self.ai_plugins.append(self._instantiate_plugin(attr))

    def _instantiate_plugin(self, plugin_cls):
        """Instantiate plugin, passing config if accepted."""
        import inspect
        try:
            sig = inspect.signature(plugin_cls)
            if 'config' in sig.parameters:
                return plugin_cls(config=self.config)
            return plugin_cls()
        except Exception:
            return plugin_cls()

    async def get_scraper_for_url(self, url: str) -> ScraperPlugin:
        """Find appropriate scraper plugin for URL"""
        for plugin in self.scraper_plugins:
            if await plugin.can_handle(url):
                return plugin
        raise ValueError(f"No scraper plugin found for URL: {url}")

    def get_ai_model_plugins(self) -> List[AIModelPlugin]:
        """Return all registered AIModelPlugin instances"""
        return self.ai_plugins
