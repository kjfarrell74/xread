from typing import List, Dict, Any, Optional
import importlib
import pkgutil
import logging
import os
from pathlib import Path
from xread.plugins.base import ScraperPlugin, AIModelPlugin

class PluginManager:
    def __init__(self, config: Dict[str, Any] = None, extra_plugin_dirs: List[str] = None):
        self.scraper_plugins: List[ScraperPlugin] = []
        self.ai_plugins: List[AIModelPlugin] = []
        self.config = config or {}
        self.extra_plugin_dirs = extra_plugin_dirs or []
        self.logger = logging.getLogger(__name__)
        self._plugin_registry: Dict[str, Any] = {}
        self.load_plugins()

    def load_plugins(self):
        """Dynamically load all plugins from plugins directory and extra directories"""
        plugin_dirs = self._discover_plugin_directories()
        
        for plugin_dir in plugin_dirs:
            self._load_plugins_from_directory(plugin_dir)
            
        self.logger.info(f"Loaded {len(self.scraper_plugins)} scraper plugins and {len(self.ai_plugins)} AI plugins")
    
    def _discover_plugin_directories(self) -> List[str]:
        """Discover all available plugin directories."""
        plugin_dirs = ['xread/plugins']
        
        # Add user-specified extra directories
        plugin_dirs.extend(self.extra_plugin_dirs)
        
        # Check for plugins in standard locations
        standard_locations = [
            os.path.expanduser('~/.xread/plugins'),
            '/usr/local/share/xread/plugins',
            './plugins'
        ]
        
        for location in standard_locations:
            if os.path.isdir(location):
                plugin_dirs.append(location)
                
        return plugin_dirs
    
    def _load_plugins_from_directory(self, plugin_dir: str):
        """Load plugins from a specific directory."""
        try:
            if not os.path.exists(plugin_dir):
                return
                
            for finder, name, ispkg in pkgutil.iter_modules([plugin_dir]):
                if name.startswith('plugin_'):
                    try:
                        module = self._import_plugin_module(plugin_dir, name)
                        self._register_plugins_from_module(module, name)
                    except Exception as e:
                        self.logger.error(f"Failed to load plugin {name} from {plugin_dir}: {e}")
        except Exception as e:
            self.logger.error(f"Failed to scan plugin directory {plugin_dir}: {e}")
    
    def _import_plugin_module(self, plugin_dir: str, name: str):
        """Import a plugin module from the specified directory."""
        if plugin_dir == 'xread/plugins':
            return importlib.import_module(f'xread.plugins.{name}')
        else:
            # External: import by path
            import importlib.util
            module_path = os.path.join(plugin_dir, f"{name}.py")
            spec = importlib.util.spec_from_file_location(name, module_path)
            if not spec or not spec.loader:
                raise ImportError(f"Cannot load spec for {name}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    
    def _register_plugins_from_module(self, module, module_name: str):
        """Register plugins found in a module."""
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type):
                if issubclass(attr, ScraperPlugin) and attr is not ScraperPlugin:
                    plugin_instance = self._instantiate_plugin(attr)
                    self.register_scraper_plugin(plugin_instance, f"{module_name}.{attr_name}")
                elif issubclass(attr, AIModelPlugin) and attr is not AIModelPlugin:
                    plugin_instance = self._instantiate_plugin(attr)
                    self.register_ai_plugin(plugin_instance, f"{module_name}.{attr_name}")

    def register_scraper_plugin(self, plugin: ScraperPlugin, name: str):
        """Register a scraper plugin with the manager."""
        self.scraper_plugins.append(plugin)
        self._plugin_registry[name] = plugin
        self.logger.info(f"Registered scraper plugin: {name}")
    
    def register_ai_plugin(self, plugin: AIModelPlugin, name: str):
        """Register an AI model plugin with the manager."""
        self.ai_plugins.append(plugin)
        self._plugin_registry[name] = plugin
        self.logger.info(f"Registered AI plugin: {name}")
    
    def _instantiate_plugin(self, plugin_cls):
        """Instantiate plugin, passing config if accepted."""
        import inspect
        try:
            sig = inspect.signature(plugin_cls)
            plugin_config = self.config.get('plugins', {}).get(plugin_cls.__name__, {})
            if 'config' in sig.parameters:
                return plugin_cls(config=plugin_config)
            return plugin_cls()
        except Exception as e:
            self.logger.warning(f"Failed to instantiate plugin {plugin_cls.__name__}: {e}")
            return plugin_cls()

    async def get_scraper_for_url(self, url: str) -> ScraperPlugin:
        """Find appropriate scraper plugin for URL"""
        for plugin in self.scraper_plugins:
            try:
                if await plugin.can_handle(url):
                    return plugin
            except Exception as e:
                self.logger.warning(f"Plugin {type(plugin).__name__} failed to check URL {url}: {e}")
        raise ValueError(f"No scraper plugin found for URL: {url}")

    def get_ai_model_plugins(self) -> List[AIModelPlugin]:
        """Return all registered AIModelPlugin instances"""
        return self.ai_plugins
    
    def get_plugin_by_name(self, name: str) -> Optional[Any]:
        """Get a specific plugin by name."""
        return self._plugin_registry.get(name)
    
    def list_plugins(self) -> Dict[str, List[str]]:
        """List all registered plugins by type."""
        return {
            'scrapers': [type(p).__name__ for p in self.scraper_plugins],
            'ai_models': [type(p).__name__ for p in self.ai_plugins]
        }
    
    def reload_plugins(self):
        """Reload all plugins from directories."""
        self.scraper_plugins.clear()
        self.ai_plugins.clear()
        self._plugin_registry.clear()
        self.load_plugins()
