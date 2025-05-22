#!/usr/bin/env python3
"""Test script for the Perplexity API format."""

import os
import asyncio
import aiohttp
import json
import sys

async def test_perplexity_api():
    """Test the Perplexity API with the correct format."""
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        raise ValueError("PERPLEXITY_API_KEY environment variable is not set. Please set it before running the test.")
    
    # Test text
    test_text = "Netflix's shares dropped by 20% after announcing subscriber losses for the first time in more than 10 years."
    
    # Format the payload according to Perplexity API expectations
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Simple text-only message
    payload = {
        "model": "sonar-pro",
        "messages": [
            {"role": "system", "content": "Be precise and concise."},
            {"role": "user", "content": test_text}
        ],
        "max_tokens": 800,
        "temperature": 0.7
    }
    
    print(f"Testing Perplexity API with text-only message...")
    print(f"Payload structure: {payload}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.perplexity.ai/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                print(f"Response status: {response.status}")
                response_text = await response.text()
                print(f"Response: {response_text[:200]}..." if len(response_text) > 200 else response_text)
                
                if response.status == 200:
                    data = json.loads(response_text)
                    print("\nPerplexity report content:")
                    print("-" * 60)
                    content = data["choices"][0]["message"]["content"]
                    print(content[:500] + "..." if len(content) > 500 else content)
                    print("-" * 60)
                    print("Test successful!")
                    return True
                else:
                    print("Test failed.")
                    return False
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_perplexity_api())
