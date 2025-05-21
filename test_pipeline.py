#!/usr/bin/env python3
"""Test script for the modified pipeline with Perplexity API integration."""

import os
import asyncio
import sys
from xread.pipeline import ScraperPipeline

async def test_pipeline():
    """Test the pipeline with a sample URL."""
    # Check for Perplexity API key
    if not os.getenv("PERPLEXITY_API_KEY"):
        print("Error: PERPLEXITY_API_KEY environment variable not found.")
        print("Please set it with: export PERPLEXITY_API_KEY=your_api_key_here")
        sys.exit(1)

    # URL to test
    test_url = "https://twitter.com/elonmusk/status/1516600269899026432"
    print(f"Testing pipeline with URL: {test_url}")

    # Set up pipeline
    pipeline = ScraperPipeline()
    await pipeline.data_manager.initialize()
    await pipeline.initialize_browser()

    try:
        # Run pipeline
        print("Running pipeline...")
        await pipeline.run(test_url)
        print("Pipeline execution completed.")
    finally:
        # Clean up
        await pipeline.close_browser()
        print("Browser closed.")

if __name__ == "__main__":
    asyncio.run(test_pipeline())