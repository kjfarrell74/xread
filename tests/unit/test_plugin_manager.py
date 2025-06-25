"""Unit tests for PluginManager functionality."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path

from xread.plugins.manager import PluginManager
from xread.plugins.base import ScraperPlugin, AIModelPlugin
from xread.models import ScrapedData, Post


class MockScraperPlugin(ScraperPlugin):
    """Mock scraper plugin for testing."""
    
    async def can_handle(self, url: str) -> bool:
        return 'test.com' in url
    
    async def scrape(self, url: str) -> ScrapedData:
        return ScrapedData(
            main_post=Post(
                user="Test User",
                username="testuser",
                text="Test content",
                date="2023-01-01",
                permalink=url,
                images=[],
                status_id="123"
            ),
            replies=[]
        )


class MockAIModelPlugin(AIModelPlugin):
    """Mock AI model plugin for testing."""
    
    async def generate_report(self, scraped_data: ScrapedData, sid: str) -> str:
        return f"Test report for {sid}"


class TestPluginManager:
    """Test cases for PluginManager."""
    
    def test_plugin_manager_initialization(self):
        """Test plugin manager initializes correctly."""
        manager = PluginManager(config={'test': 'value'})
        assert manager.config == {'test': 'value'}
        assert isinstance(manager.scraper_plugins, list)
        assert isinstance(manager.ai_plugins, list)
        assert manager.extra_plugin_dirs == []
    
    def test_register_scraper_plugin(self):
        """Test registering a scraper plugin."""
        manager = PluginManager()
        plugin = MockScraperPlugin()
        
        manager.register_scraper_plugin(plugin, "test_scraper")
        
        assert len(manager.scraper_plugins) == 1
        assert manager.scraper_plugins[0] == plugin
        assert manager._plugin_registry["test_scraper"] == plugin
    
    def test_register_ai_plugin(self):
        """Test registering an AI model plugin."""
        manager = PluginManager()
        plugin = MockAIModelPlugin()
        
        manager.register_ai_plugin(plugin, "test_ai")
        
        assert len(manager.ai_plugins) == 1
        assert manager.ai_plugins[0] == plugin
        assert manager._plugin_registry["test_ai"] == plugin
    
    @pytest.mark.asyncio
    async def test_get_scraper_for_url_success(self):
        """Test getting appropriate scraper for URL."""
        manager = PluginManager()
        plugin = MockScraperPlugin()
        manager.register_scraper_plugin(plugin, "test_scraper")
        
        result = await manager.get_scraper_for_url("https://test.com/status/123")
        assert result == plugin
    
    @pytest.mark.asyncio
    async def test_get_scraper_for_url_no_match(self):
        """Test error when no scraper can handle URL."""
        manager = PluginManager()
        plugin = MockScraperPlugin()
        manager.register_scraper_plugin(plugin, "test_scraper")
        
        with pytest.raises(ValueError, match="No scraper plugin found"):
            await manager.get_scraper_for_url("https://other.com/status/123")
    
    def test_get_plugin_by_name(self):
        """Test getting plugin by name."""
        manager = PluginManager()
        plugin = MockScraperPlugin()
        manager.register_scraper_plugin(plugin, "test_scraper")
        
        result = manager.get_plugin_by_name("test_scraper")
        assert result == plugin
        
        result = manager.get_plugin_by_name("nonexistent")
        assert result is None
    
    def test_list_plugins(self):
        """Test listing all registered plugins."""
        manager = PluginManager()
        scraper_plugin = MockScraperPlugin()
        ai_plugin = MockAIModelPlugin()
        
        manager.register_scraper_plugin(scraper_plugin, "test_scraper")
        manager.register_ai_plugin(ai_plugin, "test_ai")
        
        plugin_list = manager.list_plugins()
        assert "scrapers" in plugin_list
        assert "ai_models" in plugin_list
        assert "MockScraperPlugin" in plugin_list["scrapers"]
        assert "MockAIModelPlugin" in plugin_list["ai_models"]
    
    def test_discover_plugin_directories(self):
        """Test plugin directory discovery."""
        with patch('os.path.isdir') as mock_isdir:
            mock_isdir.return_value = True
            
            manager = PluginManager(extra_plugin_dirs=['/custom/plugins'])
            directories = manager._discover_plugin_directories()
            
            assert 'xread/plugins' in directories
            assert '/custom/plugins' in directories
    
    @patch('xread.plugins.manager.pkgutil.iter_modules')
    @patch('xread.plugins.manager.importlib.import_module')
    def test_load_plugins_from_directory(self, mock_import, mock_iter):
        """Test loading plugins from a directory."""
        # Mock module discovery
        mock_iter.return_value = [
            (None, 'plugin_test', False)
        ]
        
        # Mock module with plugin class
        mock_module = Mock()
        mock_module.__dict__ = {
            'TestPlugin': MockScraperPlugin,
            'other_class': str  # Non-plugin class
        }
        mock_import.return_value = mock_module
        
        # Mock dir() to return our plugin class
        with patch('builtins.dir', return_value=['TestPlugin', 'other_class']):
            with patch('builtins.getattr', side_effect=lambda m, n: getattr(mock_module, n)):
                manager = PluginManager()
                manager._load_plugins_from_directory('xread/plugins')
        
        # Should have registered one scraper plugin
        assert len(manager.scraper_plugins) >= 1
    
    def test_reload_plugins(self):
        """Test reloading plugins clears existing ones."""
        manager = PluginManager()
        manager.register_scraper_plugin(MockScraperPlugin(), "test")
        
        assert len(manager.scraper_plugins) == 1
        
        with patch.object(manager, 'load_plugins'):
            manager.reload_plugins()
        
        # Should be cleared (load_plugins is mocked so won't add new ones)
        assert len(manager.scraper_plugins) == 0
        assert len(manager._plugin_registry) == 0


if __name__ == '__main__':
    pytest.main([__file__])