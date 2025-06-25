#!/usr/bin/env python3
"""Final test script for verifying the Perplexity API integration."""

import os
import asyncio
import json
import base64
import sys
from datetime import datetime
from pathlib import Path

# Ensure environment variable is set (should be set externally or in a .env file)
if not os.getenv("PERPLEXITY_API_KEY"):
    raise ValueError("PERPLEXITY_API_KEY environment variable is not set. Please set it before running the test.")

from xread.pipeline import ScraperPipeline  # Import after setting environment variable

async def main():
    """Test the Perplexity API integration with a real tweet URL and image uploads."""
    from xread.data_manager import AsyncDataManager
    from xread.pipeline import ScraperPipeline

    # The tweet URL to test
    tweet_url = "https://x.com/JessePeltan/status/1931116506773135381"

    # Create a ScraperPipeline instance with a data manager
    data_manager = AsyncDataManager()
    pipeline = ScraperPipeline(data_manager)

    # Initialize the pipeline components
    await data_manager.initialize()
    await pipeline.initialize_browser()

    print(f"Scraping tweet: {tweet_url}")
    normalized_url, sid = await pipeline._prepare_url(tweet_url)
    html_content, scraped_data = await pipeline._fetch_and_parse(normalized_url, sid)
    await pipeline.close_browser()

    if not scraped_data:
        print("Failed to scrape the tweet or parse its content.")
        return False

    print("Generating Perplexity report (with images if available)...")
    report = await pipeline.ai_model.generate_report(scraped_data, sid)

    if report:
        print("\nPerplexity report generated successfully!")
        print("-" * 60)
        print(report[:500] + ("..." if len(report) > 500 else ""))
        print("-" * 60)
        # Save the result to a file
        os.makedirs("debug_output", exist_ok=True)
        with open(f"debug_output/perplexity_test_{datetime.now().strftime('%Y%m%d%H%M%S')}.json", "w") as f:
            json.dump({
                "test_time": datetime.now().isoformat(),
                "tweet_url": tweet_url,
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
