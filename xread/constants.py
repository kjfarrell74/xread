"""Constants and configuration classes for the xread application."""

from pathlib import Path

# Global constants
DEFAULT_DATA_DIR = Path("scraped_data")
DEFAULT_NITTER_BASE_URL = "https://nitter.net"
DEFAULT_MAX_IMAGE_DOWNLOADS = 5
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_DELAY = 2
MAX_IMAGE_SIZE = 10 * 1024 * 1024     # 10MB
NA_PLACEHOLDER = "N/A"
PAGE_READY_SELECTOR = "div.container"

class TimeoutConstants:
    """Constants for various timeout durations used in the application."""
    PLAYWRIGHT_PAGE_LOAD_MS = 35000
    PLAYWRIGHT_SELECTOR_MS = 7000
    PLAYWRIGHT_POST_LOAD_DELAY_MS = 3000
    IMAGE_DOWNLOAD_SECONDS = 10

class FileFormats:
    """Constants for file and directory naming conventions."""
    DEBUG_DIR = "debug_output"
    HISTORY_FILE = ".xread_history"
    INDEX_FILE = "index.json"
    CACHE_DIR = "cache"
    POST_PREFIX = "post_"
    JSON_EXTENSION = ".json"
    FAILED_PARSE_PREFIX = "failed_parse_"
    HTML_EXTENSION = ".html"

class ErrorMessages:
    """Constants for error message strings."""
    API_KEY_MISSING = "PERPLEXITY_API_KEY required for report generation"
    BROWSER_NOT_LAUNCHED = "Browser not launched."
    FETCH_FAILED = "Fetch failed."
    PARSE_FAILED = "Parse failed."
    PERPLEXITY_API_FAILED = "Failed to generate Perplexity report."

# Prompt templates
# Define the Perplexity prompt template for reference
PERPLEXITY_REPORT_PROMPT = """
Please provide a comprehensive, detailed, and factual analysis of the following Twitter/X thread.
Pay close attention to ALL of the following requirements:

1. ACCURACY: Ensure 100% factual accuracy. When presenting claims, clearly distinguish between verified facts and opinions expressed in the thread.

2. OBJECTIVITY: Maintain complete neutrality and avoid any political, social, or ideological bias.
   Do not take sides in any contentious issues mentioned in the thread.

3. COMPLETENESS: Include ALL key points, arguments, claims, and perspectives expressed by ALL users in the thread.

4. IMAGES: Pay special attention to any images in the thread. Describe what each image shows in detail.
   For each image, analyze its relevance to the discussion and how it supports or relates to the text.

5. CONTEXT: Provide comprehensive background information and broader context to help fully understand the thread.
   Include relevant historical, social, technical, or industry context that helps explain the discussion.

6. STRUCTURE: Organize your analysis clearly with:
   - A thorough summary of the main post
   - A detailed breakdown of the key themes and perspectives in the replies
   - A section specifically analyzing any images
   - Background context for the topic being discussed
   - Where appropriate, factual information that adds context to claims made in the thread

7. FACTUAL CORRECTION: If you detect any demonstrably false claims in the thread, note them objectively along with correct factual information.

8. MULTI-FACETED ANALYSIS: Present ALL sides of any debate or disagreement appearing in the thread without favoring any particular viewpoint.

Remember that your analysis will serve as a comprehensive record and reference for this content. Be thorough, neutral, and exacting in your factual presentation.

Thread Content:
---
{scraped_text}
---
"""

# Define the Gemini prompt template with specific instruction for Factual Context section
GEMINI_REPORT_PROMPT = """
Please provide a comprehensive, detailed, and factual analysis of the following Twitter/X thread.
Pay close attention to ALL of the following requirements:

1. ACCURACY: Ensure 100% factual accuracy. When presenting claims, clearly distinguish between verified facts and opinions expressed in the thread.

2. OBJECTIVITY: Maintain complete neutrality and avoid any political, social, or ideological bias.
   Do not take sides in any contentious issues mentioned in the thread.

3. COMPLETENESS: Include ALL key points, arguments, claims, and perspectives expressed by ALL users in the thread.

4. IMAGES: Pay special attention to any images in the thread. Describe what each image shows in detail.
   For each image, analyze its relevance to the discussion and how it supports or relates to the text.

5. CONTEXT: Provide comprehensive background information and broader context to help fully understand the thread.
   Include relevant historical, social, technical, or industry context that helps explain the discussion.

6. STRUCTURE: Organize your analysis clearly with:
   - A thorough summary of the main post
   - A detailed breakdown of the key themes and perspectives in the replies
   - A section specifically analyzing any images
   - Background context for the topic being discussed
   - Where appropriate, factual information that adds context to claims made in the thread

7. FACTUAL CORRECTION: If you detect any demonstrably false claims in the thread, note them objectively along with correct factual information.

8. MULTI-FACETED ANALYSIS: Present ALL sides of any debate or disagreement appearing in the thread without favoring any particular viewpoint.

9. FACTUAL CONTEXT SECTION: After your analysis, add a section titled 'Factual Context'. Bullet every factual claim, labeling each as [Verified Fact], [Claim as Fact], or [Opinion]. Do not summarize.

Remember that your analysis will serve as a comprehensive record and reference for this content. Be thorough, neutral, and exacting in your factual presentation.

Thread Content:
---
{scraped_text}
---
"""
