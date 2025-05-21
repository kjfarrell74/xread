#!/usr/bin/env python3
"""Final test script for verifying the Perplexity API integration."""

import os
import asyncio
import json
import base64
import sys
from datetime import datetime
from pathlib import Path

# Set environment variable
os.environ["PERPLEXITY_API_KEY"] = "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"

from xread.pipeline import ScraperPipeline  # Import after setting environment variable

class MockPost:
    """Mock post object for testing."""
    def __init__(self, text):
        self.text = text
        self.images = []

class MockScrapedData:
    """Mock scraped data for testing."""
    def __init__(self, text):
        self.main_post = MockPost(text)
        self.replies = []
    
    def get_full_text(self):
        """Return the main post text."""
        return self.main_post.text

async def main():
    """Test the Perplexity API integration."""
    # Create a ScraperPipeline instance
    pipeline = ScraperPipeline()
    
    # Initialize the pipeline components
    await pipeline.data_manager.initialize()
    
    # Mock data
    test_text = "Netflix's shares dropped by 20% after announcing subscriber losses for the first time in more than 10 years."
    mock_data = MockScrapedData(test_text)
    
    # Test the Perplexity API
    print("Testing Perplexity API integration...")
    report = await pipeline._generate_perplexity_report(mock_data, "test123")
    
    if report:
        print("\nPerplexity report generated successfully!")
        print("-" * 60)
        print(report[:500] + "..." if len(report) > 500 else report)
        print("-" * 60)
        
        # Save the result to a file
        os.makedirs("debug_output", exist_ok=True)
        with open(f"debug_output/perplexity_test_{datetime.now().strftime('%Y%m%d%H%M%S')}.json", "w") as f:
            json.dump({
                "test_time": datetime.now().isoformat(),
                "test_text": test_text,
                "report": report
            }, f, indent=2)
            
        print("Test completed successfully!")
        return True
    else:
        print("Failed to generate Perplexity report.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)