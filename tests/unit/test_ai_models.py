import pytest
from unittest.mock import patch, AsyncMock
from xread.ai_models import PerplexityModel, BaseAIModel
from xread.models import ScrapedData

@pytest.fixture
def mock_scraped_data():
    return ScrapedData(main_post={}, replies=[])

@pytest.mark.asyncio
async def test_perplexity_model_generate_report(mock_scraped_data):
    with patch('xread.ai_models.aiohttp.ClientSession') as mock_session:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": "Mock report"}}]}
        mock_session.return_value.__aenter__.return_value.post.return_value = mock_response
        
        model = PerplexityModel(api_key="test_key")
        report = await model.generate_report(mock_scraped_data, "test_sid")
        assert report == "Mock report"

@pytest.mark.asyncio
async def test_perplexity_model_error_handling(mock_scraped_data):
    with patch('xread.ai_models.aiohttp.ClientSession') as mock_session:
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_session.return_value.__aenter__.return_value.post.return_value = mock_response
        
        model = PerplexityModel(api_key="test_key")
        report = await model.generate_report(mock_scraped_data, "test_sid")
        assert "Error" in report  # Check for error message in report

# Add more tests as needed, e.g., for fallback strategies
