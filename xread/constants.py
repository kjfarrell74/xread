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
    API_KEY_MISSING = "GEMINI_API_KEY required if MAX_IMAGE_DOWNLOADS_PER_RUN > 0 or TEXT_ANALYSIS_MODEL is set"
    BROWSER_NOT_LAUNCHED = "Browser not launched."
    FETCH_FAILED = "Fetch failed."
    PARSE_FAILED = "Parse failed."

# Prompt templates for Gemini API
SEARCH_TERM_PROMPT = """
Analyze the following text content scraped from a social media thread (main post
and replies). Identify the key claims, topics, or entities mentioned.
Based on these key elements, generate a list of 8-10 effective search engine
query terms that someone could use to find the latest, reliable information or
fact-checks regarding these claims/topics.
Categorize the search terms into types such as factual claims, entities, and
topics if applicable. Format the output as a categorized list, with each search
term on a new line, starting with a bullet point (*).

Scraped Text Content:
---
{scraped_text}
---

Generated Search Terms:
"""

RESEARCH_QUESTIONS_PROMPT = """
Analyze the following text content scraped from a social media thread (main post
and replies). Identify the key claims, topics, or controversial points 
mentioned. Based on these elements, generate a list of 3-5 specific research questions that
could guide deeper investigation into the content. These questions should
encourage fact-checking, exploration of context, or understanding of
implications. Format the output as a simple list, with each question on a new line,
starting with a bullet point (*).

Scraped Text Content:
---
{scraped_text}
---

Generated Research Questions:
"""
