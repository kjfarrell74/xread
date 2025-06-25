"""Unit tests for AI model integration."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import aiohttp

from xread.ai_models import BaseAIModel, PerplexityModel, GeminiModel
from xread.models import ScrapedData, Post, Image
from xread.exceptions import AIModelError


@pytest.fixture
def mock_scraped_data():
    """Create mock scraped data for testing."""
    return ScrapedData(
        main_post=Post(
            user="Test User",
            username="testuser",
            text="Test content",
            date="2023-01-01",
            permalink="http://test.com",
            images=[],
            status_id="123"
        ),
        replies=[]
    )


@pytest.fixture
def mock_scraped_data_with_images():
    """Create mock scraped data with images for testing."""
    return ScrapedData(
        main_post=Post(
            user="Test User", 
            username="testuser",
            text="Test content with image",
            date="2023-01-01",
            permalink="http://test.com",
            images=[Image(url="http://test.com/image.jpg")],
            status_id="123"
        ),
        replies=[]
    )


class TestBaseAIModel:
    """Test cases for BaseAIModel abstract class."""
    
    def test_base_ai_model_is_abstract(self):
        """Test that BaseAIModel cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseAIModel()


class TestPerplexityModel:
    """Test cases for PerplexityModel."""
    
    def test_perplexity_model_initialization_with_api_key(self):
        """Test PerplexityModel initializes with provided API key."""
        model = PerplexityModel(api_key="test_key")
        assert model.api_key == "test_key"
    
    def test_perplexity_model_initialization_missing_api_key(self):
        """Test PerplexityModel raises error when no API key provided."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('xread.settings.settings') as mock_settings:
                mock_settings.perplexity_api_key = None
                with pytest.raises(ValueError, match="Perplexity API key is required"):
                    PerplexityModel()
    
    @pytest.mark.asyncio
    async def test_generate_report_success(self, mock_scraped_data):
        """Test successful report generation."""
        with patch('xread.ai_models.aiohttp.ClientSession') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json.return_value = {"choices": [{"message": {"content": "Test report"}}]}
            mock_session.return_value.__aenter__.return_value.post.return_value = mock_response
            
            model = PerplexityModel(api_key="test_key")
            report = await model.generate_report(mock_scraped_data, "test_sid")
            assert report == "Test report"
    
    @pytest.mark.asyncio
    async def test_generate_report_no_text(self):
        """Test generate_report with empty text content."""
        model = PerplexityModel(api_key="test_key")
        scraped_data = ScrapedData(
            main_post=Post(
                user="Test User",
                username="testuser", 
                text="",
                date="2023-01-01",
                permalink="http://test.com",
                images=[],
                status_id="123"
            ),
            replies=[]
        )
        
        result = await model.generate_report(scraped_data, "123")
        assert "No text content provided" in result
    
    @pytest.mark.asyncio
    async def test_generate_report_error_handling(self, mock_scraped_data):
        """Test error handling in report generation."""
        with patch('xread.ai_models.aiohttp.ClientSession') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_session.return_value.__aenter__.return_value.post.return_value = mock_response
            
            model = PerplexityModel(api_key="test_key")
            report = await model.generate_report(mock_scraped_data, "test_sid")
            assert "Error" in report
    
    def test_normalize_image_url(self):
        """Test URL normalization for Nitter images."""
        model = PerplexityModel(api_key="test_key")
        
        # Test URL decoding
        encoded_url = "https://nitter.net/pic/media%2Ftest.jpg"
        result = model._normalize_image_url(encoded_url)
        assert "media/test.jpg" in result
        
        # Test regular URL passthrough
        regular_url = "https://example.com/image.jpg"
        result = model._normalize_image_url(regular_url)
        assert result == regular_url
    
    def test_convert_to_twitter_url(self):
        """Test conversion of Nitter URLs to Twitter URLs."""
        model = PerplexityModel(api_key="test_key")
        
        # Test successful conversion
        nitter_url = "https://nitter.net/pic/orig/media%2FabcDEF123.jpg"
        result = model._convert_to_twitter_url(nitter_url)
        assert "https://pbs.twimg.com/media/abcDEF123.jpg" == result
        
        # Test non-Nitter URL
        regular_url = "https://example.com/image.jpg"
        result = model._convert_to_twitter_url(regular_url)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_make_text_only_api_call_success(self):
        """Test successful text-only API call."""
        model = PerplexityModel(api_key="test_key")
        
        # Mock successful response
        mock_response_data = {
            "choices": [
                {
                    "message": {
                        "content": "Test report content"
                    }
                }
            ]
        }
        
        with patch('aiohttp.ClientSession') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_response_data)
            
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_session.return_value)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_session.return_value.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_session.return_value.post.return_value.__aexit__ = AsyncMock(return_value=None)
            
            headers = {"Authorization": "Bearer test_key", "Content-Type": "application/json"}
            payload = {"messages": [{"role": "user", "content": "test"}]}
            
            result = await model._make_text_only_api_call(headers, payload, "123")
            assert result == "Test report content"


class TestGeminiModel:
    """Test cases for GeminiModel."""
    
    def test_gemini_model_initialization_with_api_key(self):
        """Test GeminiModel initializes with provided API key."""
        model = GeminiModel(api_key="test_key")
        assert model.api_key == "test_key"
    
    def test_gemini_model_initialization_missing_api_key(self):
        """Test GeminiModel raises error when no API key provided."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('xread.settings.settings') as mock_settings:
                mock_settings.gemini_api_key = None
                with pytest.raises(ValueError, match="Gemini API key is required"):
                    GeminiModel()
    
    @pytest.mark.asyncio
    async def test_gemini_generate_report_no_text(self):
        """Test Gemini generate_report with empty text content."""
        model = GeminiModel(api_key="test_key")
        scraped_data = ScrapedData(
            main_post=Post(
                user="Test User",
                username="testuser",
                text="",
                date="2023-01-01",
                permalink="http://test.com",
                images=[],
                status_id="123"
            ),
            replies=[]
        )
        
        result = await model.generate_report(scraped_data, "123")
        assert "No text content provided" in result


if __name__ == '__main__':
    pytest.main([__file__])
