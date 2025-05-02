#!/usr/bin/env python3
"""Asynchronous CLI tool to scrape tweet data from a Nitter instance, generate
image descriptions and search terms using the Google Gemini API, and save the combined data.

This module provides a comprehensive pipeline for scraping social media content from
Nitter instances (a Twitter alternative frontend), processing images with AI-generated
descriptions, and creating search terms and research questions for further analysis.
It leverages Playwright for browser automation, BeautifulSoup for HTML parsing, and
Google's Gemini API for content generation.

Key Features:
- Asynchronous scraping of tweet threads including main posts and replies.
- AI-powered image description generation with configurable limits.
- Generation of search terms and research questions based on scraped text.
- Data persistence in JSON format with metadata indexing.
- Interactive CLI with command history and autocomplete.

Usage Example:
    # Scrape a specific tweet URL and process its content
    $ python xread.py scrape https://nitter.net/user/status/123456789

    # Run in interactive mode to input URLs or manage saved data
    $ python xread.py
"""

import asyncio
import logging
import re
import json
import base64
import random
import os
import functools
import tempfile
import hashlib
from pathlib import Path
from urllib.parse import urlparse, urljoin
from datetime import datetime, timezone
from typing import Optional, Dict, List, Set, Callable, Any

import sys
import aiofiles
import aiohttp
from pydantic_settings import BaseSettings
from pydantic import Field, ValidationError, HttpUrl
from dataclasses import dataclass, field, asdict
from playwright.async_api import (
    async_playwright,
    Browser,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
)
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import WordCompleter
import google.generativeai as genai
from google.api_core import exceptions as google_api_exceptions
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import typer
import yaml
import mimetypes


# Load environment variables
load_dotenv()

# --- Constants ---
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

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""
    data_dir: Path = Field(Path(os.getenv("DATA_DIR", DEFAULT_DATA_DIR)), pre=True)
    nitter_base_url: HttpUrl = Field(
        os.getenv("NITTER_BASE_URL", DEFAULT_NITTER_BASE_URL)
    )
    max_image_downloads: int = Field(
        int(os.getenv("MAX_IMAGE_DOWNLOADS_PER_RUN", DEFAULT_MAX_IMAGE_DOWNLOADS)),
        ge=0,
    )
    gemini_api_key: Optional[str] = Field(os.getenv("GEMINI_API_KEY"), alias="GEMINI_API_KEY")
    status_id_regex: str = r"status/(\d+)"
    full_url_regex: str = (
        r"(?:https?://)?(?:www\.)?(?:twitter\.com|x\.com|nitter\.(?:net|[a-z0-9-]+))/"
        r"([^/]+)/status/(\d+)"
    )
    tweet_selectors: List[str] = field(
        default_factory=lambda: [
            ".main-thread .timeline-item",
            ".conversation .tweet-body",
            ".tweet-body",
            ".timeline-item",
        ]
    )
    retry_attempts: int = Field(DEFAULT_RETRY_ATTEMPTS, ge=1)
    retry_delay: int = Field(DEFAULT_RETRY_DELAY, ge=0)
    image_ignore_keywords: List[str] = Field(
        ['profile_images', 'avatar', 'user_media']
    )
    image_description_model: str = Field(
        os.getenv("IMAGE_DESCRIPTION_MODEL", "gemini-1.5-flash")
    )
    save_failed_html: bool = Field(bool(os.getenv("SAVE_FAILED_HTML", True)))
    text_analysis_model: str = Field(
        os.getenv("TEXT_ANALYSIS_MODEL", "gemini-1.5-flash")
    )

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'
        extra = 'ignore'
        populate_by_name = True


try:
    settings = Settings()
    gemini_needed = (
        settings.max_image_downloads > 0 or bool(settings.text_analysis_model)
    )
    if gemini_needed and not settings.gemini_api_key:
        raise ValueError(
            "GEMINI_API_KEY required if MAX_IMAGE_DOWNLOADS_PER_RUN > 0 or TEXT_ANALYSIS_MODEL is set"
        )
    if settings.save_failed_html:
        Path(FileFormats.DEBUG_DIR).mkdir(parents=True, exist_ok=True)
except (ValidationError, ValueError) as e:
    logger.error(f"Configuration error: {e}")
    typer.echo(f"Configuration error: {e}", err=True)
    typer.echo("Check environment variables or .env file.", err=True)
    sys.exit(1)


def with_retry(retries: int = None, delay: int = None):
    """Decorator to retry async functions with exponential backoff."""
    retries = retries if retries is not None else settings.retry_attempts
    delay = delay if delay is not None else settings.retry_delay

    def decorator(fn: Callable[..., Any]):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(retries):
                try:
                    if asyncio.iscoroutinefunction(fn):
                        return await fn(*args, **kwargs)
                    return await asyncio.to_thread(fn, *args, **kwargs)
                except (
                    PlaywrightTimeoutError,
                    PlaywrightError,
                    aiohttp.ClientError,
                    google_api_exceptions.GoogleAPIError,
                    google_api_exceptions.RetryError,
                    IOError,
                ) as e:
                    last_exception = e
                    is_non_retryable = isinstance(
                        e,
                        (
                            google_api_exceptions.PermissionDenied,
                            google_api_exceptions.InvalidArgument,
                            google_api_exceptions.Unauthenticated,
                        ),
                    )
                    logger.warning(
                        f"{fn.__name__} attempt {attempt+1}/{retries} failed: "
                        f"{type(e).__name__}: {e}"
                    )
                    if attempt < retries - 1 and not is_non_retryable:
                        sleep_time = delay * (2 ** attempt) + random.random()
                        logger.info(f"Retrying in {sleep_time:.2f}s...")
                        await asyncio.sleep(sleep_time)
                    else:
                        logger.error(f"{fn.__name__} failed after {retries} attempts.")
                        raise last_exception
            if last_exception:
                raise last_exception
            return None
        return wrapper
    return decorator


@dataclass
class Image:
    """Represents an image with its URL and optional description."""
    url: str
    description: Optional[str] = None


@dataclass
class Post:
    """Represents a post with user info, text, date, permalink, and images."""
    user: str
    username: str
    text: str
    date: str
    permalink: str
    images: List[Image] = field(default_factory=list)
    status_id: Optional[str] = None

    def __post_init__(self):
        if self.permalink and self.permalink != NA_PLACEHOLDER:
            match = re.search(settings.status_id_regex, self.permalink)
            if match:
                self.status_id = match.group(1)

    def to_dict(self) -> Dict[str, Any]:
        """Convert Post to a JSON-serializable dictionary."""
        return asdict(self)


@dataclass
class ScrapedData:
    """Holds the main post and its replies after scraping."""
    main_post: Post
    replies: List[Post]

    def get_full_text(self) -> str:
        """Combine main post text and reply texts into a single string."""
        parts = [f"Main Post (@{self.main_post.username}):\n{self.main_post.text}\n\n"]
        
        if self.replies:
            parts.append("Replies:\n")
            for i, reply in enumerate(self.replies, start=1):
                # Filter out duplicate consecutive replies
                if i > 1 and reply.text == self.replies[i-2].text and reply.username == self.replies[i-2].username:
                    continue
                parts.append(f"--- Reply {i} (@{reply.username}) ---\n{reply.text}\n")
        
        return "".join(parts).strip()


def load_instructions(filepath: Path = Path("instructions.yaml")) -> Dict[str, Any]:
    """Load custom instructions from a YAML file if present."""
    if not filepath.exists():
        return {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            instructions = yaml.safe_load(f) or {}
        instructions.pop('report_style_guide', None)
        instructions.pop('report_format', None)
        instructions.pop('default_report_output_subdir', None)
        logger.info(f"Loaded instructions from {filepath}.")
        return instructions
    except yaml.YAMLError as e:
        logger.error(f"Error loading YAML file {filepath}: {e}")
    except IOError as e:
        logger.error(f"File reading error for {filepath}: {e}")
    return {}


class DataManager:
    """Handles saving and loading scraped data to/from JSON files."""
    def __init__(self):
        self.data_dir = settings.data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.data_dir / 'index.json'
        self.cache_dir = self.data_dir / 'cache'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / 'image_descriptions.json'
        self.image_cache: Dict[str, str] = {}
        self.index: Dict[str, Any] = {'posts': {}, 'latest_scrape': None}
        self.seen: Set[str] = set()

    async def initialize(self) -> None:
        """Initialize the data manager by loading index and cache."""
        await self._load_index()
        await self._load_cache()

    async def _load_index(self) -> None:
        if self.index_file.exists():
            try:
                async with aiofiles.open(self.index_file, mode='r', encoding='utf-8') as f:
                    self.index = json.loads(await f.read())
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading index.json: {e}. Resetting index.")
                self.index = {'posts': {}, 'latest_scrape': None}
        self.seen = set(self.index.get('posts', {}).keys())

    async def _load_cache(self) -> None:
        if self.cache_file.exists():
            try:
                async with aiofiles.open(self.cache_file, mode='r', encoding='utf-8') as f:
                    self.image_cache = json.loads(await f.read())
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading image cache: {e}. Starting empty.")
                self.image_cache = {}

    async def _save_index(self) -> None:
        try:
            async with aiofiles.open(self.index_file, mode='w', encoding='utf-8') as f:
                await f.write(json.dumps(self.index, indent=2))
        except IOError as e:
            logger.error(f"Error saving index.json: {e}")

    async def _save_cache(self) -> None:
        try:
            async with aiofiles.open(self.cache_file, mode='w', encoding='utf-8') as f:
                await f.write(json.dumps(self.image_cache, indent=2, ensure_ascii=False))
        except IOError as e:
            logger.error(f"Error saving image cache: {e}")

    async def save(
        self,
        data: ScrapedData,
        original_url: str,
        search_terms: Optional[str] = None,
        research_questions: Optional[str] = None,
    ) -> Optional[str]:
        """Save scraped data, search terms, and research questions to a JSON file."""
        sid = data.main_post.status_id
        if not sid:
            first_reply_sid = next((r.status_id for r in data.replies if r.status_id), None)
            if first_reply_sid:
                sid = first_reply_sid
                logger.warning(f"Main post missing ID, using first reply ID: {sid}")
            else:
                logger.error("No status ID found in main post or replies. Skipping save.")
                return None

        if sid in self.seen:
            logger.info(f"Post {sid} already saved. Skipping.")
            return None

        meta = {
            'original_url': original_url,
            'author': data.main_post.username,
            'scrape_date': datetime.now(timezone.utc).isoformat(),
            'replies_count': len(data.replies)
        }
        self.index['posts'][sid] = meta
        self.index['latest_scrape'] = meta['scrape_date']
        await self._save_index()

        post_file = self.data_dir / f'post_{sid}.json'
        final_output = {
            'main_post': data.main_post.to_dict(),
            'replies': [r.to_dict() for r in data.replies],
            'suggested_search_terms': search_terms,
            'research_questions': research_questions
        }
        try:
            post_json = json.dumps(final_output, indent=2, ensure_ascii=False)
            async with aiofiles.open(post_file, mode='w', encoding='utf-8') as f:
                await f.write(post_json)
            self.seen.add(sid)
            logger.info(f"Saved post {sid} to {post_file}")
            return sid
        except (IOError, TypeError) as e:
            logger.error(f"Error saving post {post_file}: {e}")
            if sid in self.index['posts']:
                del self.index['posts'][sid]
                await self._save_index()
            return None

    async def load_post_data(self, status_id: str) -> Optional[ScrapedData]:
        """Load the scraped data (main_post, replies) from a saved JSON post file."""
        post_file = self.data_dir / f'post_{status_id}.json'
        if not post_file.exists():
            logger.warning(f"Post file not found for ID: {status_id}")
            return None
        try:
            async with aiofiles.open(post_file, mode='r', encoding='utf-8') as f:
                full_content = json.loads(await f.read())
            main_post_dict = full_content.get('main_post')
            replies_list_dict = full_content.get('replies', [])
            if not main_post_dict:
                logger.error(f"Main post data missing in file {post_file}")
                return None
            main_post = Post(**main_post_dict)
            main_post.images = [
                Image(**img_dict) for img_dict in main_post_dict.get('images', []) if isinstance(img_dict, dict)
            ]
            replies: List[Post] = []
            for reply_dict in replies_list_dict:
                if isinstance(reply_dict, dict):
                    reply = Post(**reply_dict)
                    reply.images = [
                        Image(**img_dict) for img_dict in reply_dict.get('images', []) if isinstance(img_dict, dict)
                    ]
                    replies.append(reply)
                else:
                    logger.warning(f"Skipping malformed reply data in file {post_file}")
            logger.info(f"Loaded scraped data for ID: {status_id}")
            return ScrapedData(main_post=main_post, replies=replies)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading/decoding {post_file}: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error reconstructing data for {post_file}: {e}")
            return None

    def list_meta(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """List saved post metadata, sorted by scrape date (descending)."""
        posts = [{'status_id': sid, **meta} for sid, meta in self.index.get('posts', {}).items()]
        posts.sort(key=lambda x: x.get('scrape_date', ''), reverse=True)
        return posts[:limit] if limit else posts

    def count(self) -> int:
        """Return total number of saved posts."""
        return len(self.index.get('posts', {}))

    async def delete(self, status_id: str) -> bool:
        """Delete a saved post by status ID."""
        if status_id not in self.index.get('posts', {}):
            logger.warning(f"Post {status_id} not found.")
            return False
        post_file = self.data_dir / f"post_{status_id}.json"
        if post_file.exists():
            try:
                post_file.unlink()
                logger.info(f"Deleted file {post_file}")
            except IOError as e:
                logger.error(f"Error deleting file {post_file}: {e}")
        self.index['posts'].pop(status_id, None)
        self.seen.discard(status_id)
        await self._save_index()
        logger.info(f"Removed post {status_id} from index.")
        return True


class NitterScraper:
    """Scrapes data from a Nitter instance using Playwright and BeautifulSoup."""
    def __init__(self):
        self.base_url = str(settings.nitter_base_url).rstrip('/')

    def normalize_url(self, url: str) -> str:
        """Normalize user-provided URL to a Nitter URL."""
        url = url.strip()
        match = re.search(settings.full_url_regex, url, re.IGNORECASE)
        if match:
            user, sid = match.groups()
            return f"{self.base_url}/{user}/status/{sid}"
        raise ValueError(f"Invalid URL format: {url}")

    @with_retry()
    async def fetch_html(self, page: Page, url: str) -> Optional[str]:
        """Use Playwright to fetch page HTML content."""
        logger.info(f"Fetching HTML from {url}")
        try:
            response = await page.goto(url, wait_until='networkidle', timeout=TimeoutConstants.PLAYWRIGHT_PAGE_LOAD_MS)
            if not response:
                logger.warning(f"No response for {url}")
                return None
            if response.status != 200:
                if 300 <= response.status < 400:
                    logger.warning(f"Redirected from {url} (Status: {response.status}). Stopping.")
                    return None
                logger.warning(f"Non-200 response for {url}: Status {response.status}")
                if response.status >= 500:
                    return None
            try:
                await page.wait_for_selector(PAGE_READY_SELECTOR, state='visible', timeout=TimeoutConstants.PLAYWRIGHT_SELECTOR_MS)
                logger.info(f"Found '{PAGE_READY_SELECTOR}'")
            except PlaywrightTimeoutError:
                logger.warning(f"'{PAGE_READY_SELECTOR}' not found/visible. Proceeding anyway.")
            await page.wait_for_timeout(TimeoutConstants.PLAYWRIGHT_POST_LOAD_DELAY_MS)
            html_content = await page.content()
            if not html_content:
                logger.warning(f"Empty HTML from {url}")
                return None
            if ("Tweet not found" in html_content or
                    "Instance has been rate limited" in html_content or
                    "User not found" in html_content):
                logger.warning(f"Content from {url} indicates error.")
            logger.info(f"Fetched HTML ({len(html_content)} bytes) from {url}")
            return html_content
        except PlaywrightTimeoutError as e:
            logger.error(f"Playwright timeout for {url}: {e}")
            return None
        except PlaywrightError as e:
            logger.error(f"Playwright error fetching {url}: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected fetch error for {url}: {e}")
            return None

    def parse_html(self, html: str) -> Optional[ScrapedData]:
        """Parse HTML content and extract main post and replies."""
        if not html:
            logger.error("Parsing skipped: No HTML.")
            return None
        soup = BeautifulSoup(html, 'html.parser')
        error_text = soup.find(
            string=re.compile("Tweet not found|Instance has been rate limited|User not found", re.IGNORECASE)
        )
        if error_text:
            logger.error("Parsing failed: Page indicates error.")
            return None
        combined_selector = ", ".join(settings.tweet_selectors)
        all_posts = soup.select(combined_selector)
        if not all_posts:
            logger.warning(f"No elements matched selectors: {settings.tweet_selectors}")
            return None
        valid_posts = [
            el for el in all_posts
            if el.select_one('.username, .handle') and el.select_one('.tweet-content, .content')
        ]
        if not valid_posts:
            logger.warning("Elements matched but none contained username/content.")
            return None
        main_element = valid_posts[0]
        reply_elements = valid_posts[1:]
        try:
            main_post = self._extract_post_data(main_element)
            replies = [self._extract_post_data(el) for el in reply_elements]
            # Filter out exact duplicate replies based on status_id or permalink
            unique_replies: Dict[str, Post] = {}
            main_key = main_post.status_id or main_post.permalink
            for reply in replies:
                key = reply.status_id or reply.permalink
                if key and key != NA_PLACEHOLDER and key not in unique_replies and key != main_key:
                    unique_replies[key] = reply
            replies = list(unique_replies.values())
        except Exception as e:
            logger.exception(f"Error extracting post data: {e}")
            return None
        logger.info(f"Parsed main post and {len(replies)} unique replies.")
        return ScrapedData(main_post=main_post, replies=replies)

    def _extract_post_data(self, element) -> Post:
        """Extract post details (user, text, date, images) from a BeautifulSoup element."""
        def get_text(selector: str) -> str:
            node = element.select_one(selector)
            text = node.get_text(strip=True) if node else NA_PLACEHOLDER
            if selector in ('.username', '.handle') and text.startswith('@'):
                return text[1:]
            return text or NA_PLACEHOLDER

        user = get_text('.fullname')
        if user == NA_PLACEHOLDER:
            user = get_text('.username')
        username = get_text('.username') or get_text('.handle')
        text_content = get_text('.tweet-content') or get_text('.content')
        date_node = element.select_one('.tweet-date a, .tweet-link')
        date = date_node.get('title', NA_PLACEHOLDER) if date_node else NA_PLACEHOLDER
        permalink = (
            urljoin(self.base_url, date_node.get('href', NA_PLACEHOLDER))
            if date_node else NA_PLACEHOLDER
        )
        if date == NA_PLACEHOLDER and date_node:
            date = date_node.get_text(strip=True)
        img_urls: Set[str] = set()
        for img_cont in element.select('.attachments .attachment.image, .attachments .video-container'):
            link = img_cont.select_one('a.still-image, a.video-thumbnail')
            img = img_cont.select_one('img')
            src = link.get('href') if link else (img.get('src') if img else None)
            if (
                src and isinstance(src, str) and
                not any(k in src for k in settings.image_ignore_keywords)
            ):
                img_urls.add(urljoin(self.base_url, src))
        images = [Image(url=url) for url in sorted(img_urls)]
        return Post(
            user=user,
            username=username,
            text=text_content,
            date=date,
            permalink=permalink,
            images=images
        )


class GeminiApiError(Exception):
    """Custom exception for Gemini API errors."""
    pass

class RateLimiter:
    """Manages API rate limits to prevent throttling or bans."""
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.request_times: List[float] = []
        self._lock = asyncio.Lock()
        
    async def acquire(self) -> None:
        """Wait if necessary to comply with rate limits."""
        async with self._lock:
            now = time.time()
            # Remove timestamps older than 1 minute
            self.request_times = [t for t in self.request_times if now - t < 60]
            
            if len(self.request_times) >= self.requests_per_minute:
                oldest = min(self.request_times)
                sleep_time = max(0, 60 - (now - oldest))
                if sleep_time > 0:
                    logger.info(f"Rate limit: waiting {sleep_time:.2f}s")
                    await asyncio.sleep(sleep_time)
                    
            self.request_times.append(time.time())

class GeminiProcessor:
    """Manages Gemini API interactions for image description and text analysis."""
    def __init__(self, data_manager: DataManager):
        self.image_model: Optional[genai.GenerativeModel] = None
        self.text_model: Optional[genai.GenerativeModel] = None
        self.api_key_valid = False
        self.rate_limiter = RateLimiter(requests_per_minute=60)
        if settings.gemini_api_key:
            try:
                genai.configure(api_key=settings.gemini_api_key)
                model_loaded = False
                if settings.max_image_downloads > 0 and settings.image_description_model:
                    try:
                        self.image_model = genai.GenerativeModel(settings.image_description_model)
                        logger.info(f"Initialized image model '{settings.image_description_model}'")
                        model_loaded = True
                    except Exception as e:
                        logger.error(f"Failed to load image model '{settings.image_description_model}': {e}")
                if settings.text_analysis_model:
                    try:
                        self.text_model = genai.GenerativeModel(settings.text_analysis_model)
                        logger.info(f"Initialized text model '{settings.text_analysis_model}'")
                        model_loaded = True
                    except Exception as e:
                        logger.error(f"Failed to load text model '{settings.text_analysis_model}': {e}")
                self.api_key_valid = model_loaded
                if not self.api_key_valid:
                    logger.warning("API key provided, but no Gemini models could be loaded.")
            except Exception as e:
                logger.error(f"Failed to configure Gemini SDK: {e}")
        else:
            logger.warning("GEMINI_API_KEY not found. Gemini features disabled.")
        self.max_downloads = settings.max_image_downloads
        self.downloaded_count = 0
        self.data_manager = data_manager

    async def process_images(self, item: Post, session: aiohttp.ClientSession, item_type: str = "post") -> None:
        """Process images in a post or reply to generate descriptions.
        
        Args:
            item: The Post object containing images to process.
            session: The aiohttp ClientSession for downloading images.
            item_type: String indicating if this is a 'post' or 'reply' (default: 'post').
        """
        if not self.api_key_valid or not self.image_model or settings.max_image_downloads <= 0:
            return
        if not item.images:
            return
        remaining = self.max_downloads - self.downloaded_count
        logger.info(f"Processing up to {remaining} images for {item_type} {item.status_id or 'N/A'}...")
        tasks = []
        for img in item.images:
            if self.downloaded_count >= self.max_downloads:
                break
            tasks.append(asyncio.create_task(self._process_single_image(session, img)))
        for img in item.images[len(tasks):]:
            img.description = "Skipped (limit reached)"
        if tasks:
            await asyncio.gather(*tasks)

    @with_retry()
    async def _process_single_image(self, session: aiohttp.ClientSession, image: Image) -> None:
        """Download an image and generate its description via the Gemini API."""
        temp_file_path = None
        cache_key = hashlib.sha256(image.url.encode()).hexdigest()
        try:
            if cache_key in self.data_manager.image_cache:
                image.description = self.data_manager.image_cache[cache_key]
                logger.info(f"Used cached description for {image.url}")
                self.downloaded_count += 1
                logger.info(f"Image count: {self.downloaded_count}/{self.max_downloads}")
                return

            logger.info(f"Downloading image: {image.url}")
            async with asyncio.timeout(TimeoutConstants.IMAGE_DOWNLOAD_SECONDS):
                async with session.get(image.url) as resp:
                    resp.raise_for_status()
                    content = await resp.read()
            if not content:
                logger.warning(f"Empty download {image.url}")
                image.description = "Error: Empty download"
                return
            if len(content) > MAX_IMAGE_SIZE:
                logger.warning(f"Image {image.url} too large")
                image.description = "Error: Image too large"
                return
            temp_dir = Path(tempfile.gettempdir())
            temp_dir.mkdir(exist_ok=True)
            temp_suff = Path(urlparse(image.url).path).suffix or ".tmp"
            with tempfile.NamedTemporaryFile(delete=False, suffix=temp_suff, dir=temp_dir) as tmpf:
                tmpf.write(content)
                temp_file_path = Path(tmpf.name)
            await self.rate_limiter.acquire()
            image.description = await self._describe_image_native(temp_file_path, content)
            self.downloaded_count += 1
            logger.info(f"Described {image.url}. Image count: {self.downloaded_count}/{self.max_downloads}")
            if image.description and not image.description.startswith("Error:"):
                self.data_manager.image_cache[cache_key] = image.description
                await self.data_manager._save_cache()
        except Exception as e:
            err_msg = f"Error processing image: {e.__class__.__name__}"
            logger.warning(f"{err_msg} for {image.url}")
            image.description = image.description or err_msg
        finally:
            if temp_file_path and temp_file_path.exists():
                try:
                    temp_file_path.unlink()
                except IOError as e:
                    logger.warning(f"Failed to delete temp file {temp_file_path}: {e}")

    @with_retry()
    async def _describe_image_native(self, path: Path, image_bytes: bytes) -> str:
        """Use Gemini API to describe an image."""
        if not self.api_key_valid or not self.image_model:
            raise GeminiApiError("Image model not available.")
        try:
            if not image_bytes:
                logger.warning(f"{path} empty.")
                raise GeminiApiError("Image file empty.")
            logger.info(f"Describing {path} ({len(image_bytes)} bytes) via Gemini...")
            mime_type, _ = mimetypes.guess_type(str(path))
            mime_type = mime_type if mime_type and mime_type.startswith('image/') else "image/jpeg"
            image_part = {"mime_type": mime_type, "data": image_bytes}
            prompt_parts = ["Describe this image objectively.", image_part]
            response = await self.image_model.generate_content_async(prompt_parts)
            if not response.candidates:
                if response.prompt_feedback and response.prompt_feedback.block_reason:
                    raise GeminiApiError(f"Blocked ({response.prompt_feedback.block_reason.name})")
                raise GeminiApiError("No candidates")
            if response.text:
                desc = response.text.strip()
                if "cannot fulfill" in desc.lower() or "unable to process" in desc.lower():
                    raise GeminiApiError("API refused.")
                return desc
            raise GeminiApiError("No text in response.")
        except google_api_exceptions.InvalidArgument as e:
            if "API key not valid" in str(e):
                self.api_key_valid = False
            raise GeminiApiError(f"Invalid Argument ({e})")
        except google_api_exceptions.PermissionDenied as e:
            self.api_key_valid = False
            raise GeminiApiError(f"Permission Denied ({e})")
        except google_api_exceptions.ResourceExhausted as e:
            raise GeminiApiError(f"Rate limit ({e})")
        except google_api_exceptions.GoogleAPIError as e:
            raise GeminiApiError(f"API Error ({e.__class__.__name__})")
        except Exception as e:
            logger.exception(f"Unexpected desc error {path}: {e}")
            raise GeminiApiError(f"Unexpected ({e.__class__.__name__})")

    async def generate_text_native(self, prompt: str, task_description: str) -> Optional[str]:
        """Generate text using the Gemini API for the given prompt."""
        if not self.api_key_valid or not self.text_model:
            reason = "API client/key invalid" if not self.api_key_valid else "Text model init failed"
            logger.error(f"Cannot perform '{task_description}': {reason}.")
            raise GeminiApiError(f"Cannot perform '{task_description}'. Reason: {reason}.")
        logger.info(f"Sending prompt to Gemini API for '{task_description}'...")
        try:
            response = await self.text_model.generate_content_async([prompt])
            if not response.candidates:
                block_reason = (
                    response.prompt_feedback.block_reason.name
                    if response.prompt_feedback and response.prompt_feedback.block_reason
                    else "Unknown"
                )
                logger.warning(f"Gemini blocked for '{task_description}'. Reason: {block_reason}.")
                raise GeminiApiError(f"Blocked by API ({block_reason}) for '{task_description}'.")
            if not response.text:
                logger.warning(f"Gemini response empty for '{task_description}'.")
                raise GeminiApiError(f"API response empty for '{task_description}'.")
            text_content = response.text.strip()
            if "cannot fulfill" in text_content.lower() or "unable to process" in text_content.lower():
                logger.warning(f"Generated content for '{task_description}' contains refusal.")
                return f"Warning: Refusal\n{text_content}"
            logger.info(f"Successfully generated content for '{task_description}'.")
            return text_content
        except google_api_exceptions.InvalidArgument as e:
            if "API key not valid" in str(e):
                self.api_key_valid = False
            logger.error(f"Invalid Argument for '{task_description}': {e}")
            raise GeminiApiError(f"Invalid Argument ({e})")
        except google_api_exceptions.PermissionDenied as e:
            self.api_key_valid = False
            logger.error(f"Permission Denied for '{task_description}': {e}")
            raise GeminiApiError(f"Permission Denied ({e})")
        except google_api_exceptions.ResourceExhausted as e:
            logger.error(f"Rate limit for '{task_description}': {e}")
            raise GeminiApiError(f"Rate limit ({e})")
        except google_api_exceptions.GoogleAPIError as e:
            logger.error(f"API Error for '{task_description}': {e}")
            raise GeminiApiError(f"API Error ({e.__class__.__name__})")
        except Exception as e:
            logger.exception(f"Unexpected error during '{task_description}': {e}")
            raise GeminiApiError(f"Unexpected ({e.__class__.__name__})")


class BrowserManager:
    """Manages a Playwright browser instance."""
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.playwright: Optional[Playwright] = None
        self._entered = False

    async def __aenter__(self):
        logger.info("Launching Playwright browser.")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.firefox.launch(headless=True)
        logger.info("Using Firefox.")
        self._entered = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        logger.info("Closing Playwright browser.")
        try:
            if self.browser and self.browser.is_connected():
                await self.browser.close()
        except Exception as e:
            logger.error(f"Error closing browser: {e}", exc_info=True)
        try:
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            logger.error(f"Error stopping playwright: {e}", exc_info=True)
        self._entered = False
        logger.info("Browser closed.")

    async def new_page(self) -> Page:
        """Create a new browser page with a standard user agent."""
        if not self._entered or not self.browser:
            raise RuntimeError("Browser not launched.")
        ctx = await self.browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0'
        )
        page = await ctx.new_page()
        logger.debug("New browser page created.")
        return page


class ScraperPipeline:
    """Orchestrates scraping, processing, generating search terms, and saving data."""
    def __init__(self):
        self.scraper = NitterScraper()
        self.data_manager = DataManager()
        self.gemini_processor = GeminiProcessor(self.data_manager)
        self.browser_manager = BrowserManager()
        self._browser_ready = False
        self.instructions = load_instructions()

    async def initialize_browser(self) -> None:
        """Launch the Playwright browser if not already started."""
        if not self._browser_ready:
            await self.browser_manager.__aenter__()
            self._browser_ready = True

    async def close_browser(self) -> None:
        """Close the Playwright browser if it is running."""
        if self._browser_ready:
            await self.browser_manager.__aexit__(None, None, None)
            self._browser_ready = False

    def reload_instructions(self) -> None:
        """Reload custom instructions from file."""
        logger.info("Reloading instructions...")
        self.instructions = load_instructions()
        logger.info("Instructions reloaded.")

    async def _save_failed_html(self, sid: Optional[str], html: Optional[str]) -> None:
        """Save fetched HTML content to a debug file if parsing fails."""
        if not settings.save_failed_html or not html:
            return
        sid_val = sid or f"unknown_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        fpath = Path(FileFormats.DEBUG_DIR) / f"{FileFormats.FAILED_PARSE_PREFIX}{sid_val}{FileFormats.HTML_EXTENSION}"
        fpath.parent.mkdir(parents=True, exist_ok=True)
        try:
            async with aiofiles.open(fpath, 'w', encoding='utf-8') as f:
                await f.write(html)
            logger.info(f"Saved failed HTML to {fpath}")
        except Exception as e:
            logger.error(f"Could not save failed HTML to {fpath}: {e}")

    async def _prepare_url(self, url: str) -> tuple[str, Optional[str]]:
        """Prepare and normalize the URL for scraping, extracting the status ID."""
        normalized_url = self.scraper.normalize_url(url)
        sid_match = re.search(settings.status_id_regex, normalized_url)
        sid = sid_match.group(1) if sid_match else None
        if not sid:
            raise ValueError("Status ID extraction failed.")
        return normalized_url, sid

    async def _fetch_and_parse(self, normalized_url: str, sid: str) -> tuple[Optional[str], Optional[ScrapedData]]:
        """Fetch HTML content and parse it into structured data."""
        page = await self.browser_manager.new_page()
        try:
            html_content = await self.scraper.fetch_html(page, normalized_url)
            if not html_content:
                logger.error(f"Fetch failed for {normalized_url}")
                typer.echo(f"Error: {ErrorMessages.FETCH_FAILED}", err=True)
                return None, None

            scraped_data = self.scraper.parse_html(html_content)
            if not scraped_data:
                logger.error(f"Parse failed for {normalized_url}")
                typer.echo(f"Error: {ErrorMessages.PARSE_FAILED}", err=True)
                await self._save_failed_html(sid, html_content)
                return html_content, None
            return html_content, scraped_data
        finally:
            try:
                await page.close()
            except Exception as e:
                logger.warning(f"Error closing page: {e}")

    async def _process_media(self, scraped_data: ScrapedData, sid: str) -> None:
        """Process images in the scraped data if conditions are met."""
        if not (
            self.gemini_processor.api_key_valid and 
            self.gemini_processor.image_model and 
            settings.max_image_downloads > 0
        ):
            logger.info("Image processing skipped (API invalid, model missing, or limit 0).")
            return
        
        async with aiohttp.ClientSession() as session:
            logger.info(f"Processing images for post {sid}...")
            await self.gemini_processor.process_images(scraped_data.main_post, session, "post")
            for reply in scraped_data.replies:
                if self.gemini_processor.downloaded_count >= settings.max_image_downloads:
                    break
                await self.gemini_processor.process_images(reply, session, "reply")

    async def _generate_search_terms(self, scraped_data: ScrapedData, sid: str) -> Optional[str]:
        """Generate search terms based on scraped text content."""
        if not (self.gemini_processor.api_key_valid and self.gemini_processor.text_model):
            logger.info("Search term generation skipped (API invalid or text model missing).")
            return "Skipped: API invalid or text model missing."

        logger.info(f"Generating search terms for post {sid}...")
        full_text = scraped_data.get_full_text()
        if full_text.strip():
            prompt = SEARCH_TERM_PROMPT.format(scraped_text=full_text)
            search_terms = await self.gemini_processor.generate_text_native(
                prompt, f"Search Term Generation (Post ID: {sid})"
            )
            if search_terms and (search_terms.startswith("Error:") or search_terms.startswith("Warning:")):
                logger.warning(f"Gemini issue generating search terms for {sid}: {search_terms}")
            return search_terms
        logger.warning(f"Post {sid} has no text content for search term generation.")
        return "Info: No text content provided for analysis."

    async def _generate_research_questions(self, scraped_data: ScrapedData, sid: str) -> Optional[str]:
        """Generate research questions based on scraped text content."""
        if not (self.gemini_processor.api_key_valid and self.gemini_processor.text_model):
            logger.info("Research questions generation skipped (API invalid or text model missing).")
            return "Skipped: API invalid or text model missing."

        logger.info(f"Generating research questions for post {sid}...")
        full_text = scraped_data.get_full_text()
        if full_text.strip():
            prompt = RESEARCH_QUESTIONS_PROMPT.format(scraped_text=full_text)
            research_questions = await self.gemini_processor.generate_text_native(
                prompt, f"Research Questions Generation (Post ID: {sid})"
            )
            if research_questions and (research_questions.startswith("Error:") or research_questions.startswith("Warning:")):
                logger.warning(f"Gemini issue generating research questions for {sid}: {research_questions}")
            return research_questions
        logger.warning(f"Post {sid} has no text content for research questions generation.")
        return "Info: No text content provided for analysis."

    async def _save_results(self, scraped_data: ScrapedData, url: str, search_terms: Optional[str], research_questions: Optional[str], sid: str) -> None:
        """Save the scraped data along with generated content."""
        saved_sid = await self.data_manager.save(scraped_data, url, search_terms, research_questions)
        if saved_sid:
            logger.info(f"Successfully saved post {saved_sid}")
            typer.echo(f"Success: Saved post {saved_sid}.")
        else:
            if sid and sid not in self.data_manager.seen:
                typer.echo(f"Error: Failed to save data for post {sid}.", err=True)

    async def run(self, url: str) -> None:
        """Run the full pipeline: scrape, process images, generate terms, and save."""
        await self.initialize_browser()
        logger.info(f"Starting pipeline for {url}")
        self.gemini_processor.downloaded_count = 0
        
        try:
            normalized_url, sid = await self._prepare_url(url)
            if sid in self.data_manager.seen:
                logger.info(f"Post {sid} seen. Skipping.")
                typer.echo(f"Skipped (already saved): {sid}")
                return
                
            html_content, scraped_data = await self._fetch_and_parse(normalized_url, sid)
            if not scraped_data:
                if html_content:
                    await self._save_failed_html(sid, html_content)
                return
                
            await self._process_media(scraped_data, sid)
            search_terms = await self._generate_search_terms(scraped_data, sid)
            research_questions = await self._generate_research_questions(scraped_data, sid)
            
            await self._save_results(scraped_data, url, search_terms, research_questions, sid)
        except ValueError as e:
            logger.error(f"URL/Input error: {e}")
            typer.echo(f"Error: {e}", err=True)
        except Exception as e:
            logger.exception(f"Unexpected pipeline error for {url}: {e}")
            typer.echo(f"Error: An unexpected error occurred: {e}", err=True)
            if html_content and scraped_data is None:
                await self._save_failed_html(sid, html_content)


# --- CLI Application ---
app = typer.Typer(name="xread", invoke_without_command=True, no_args_is_help=False)


async def run_interactive_mode_async(pipeline: ScraperPipeline) -> None:
    """Run interactive mode for URL input or commands."""
    print("XReader CLI (Gemini Image Desc + Search Terms)")
    print("Enter URL to scrape, or command:")
    print("  help, list [limit], stats, delete <id>, reload_instructions, quit")

    commands = [
        'scrape', 'list', 'stats', 'delete', 'help', 'quit', 'exit', 'reload_instructions'
    ]
    command_completer = WordCompleter(commands, ignore_case=True)
    history = FileHistory(str(settings.data_dir / FileFormats.HISTORY_FILE))
    session = PromptSession(
        history=history,
        completer=command_completer,
        enable_history_search=True
    )

    await pipeline.initialize_browser()
    try:
        while True:
            try:
                user_input = await session.prompt_async('> ')
            except (EOFError, KeyboardInterrupt):
                print("\nExiting.")
                break
            if not user_input:
                continue

            parts = user_input.split(maxsplit=1)
            cmd = parts[0].lower()
            args_str = parts[1] if len(parts) > 1 else ""

            if cmd in ("quit", "exit"):
                print("Goodbye.")
                break
            elif cmd == "reload_instructions":
                pipeline.reload_instructions()
                print("Instructions reloaded.")
            elif cmd == "help":
                print("\nAvailable commands:")
                print("  <URL>                      Scrape URL (saves data + generates search terms).")
                print("  list [limit]               List saved post metadata.")
                print("  stats                      Show count of saved posts.")
                print("  delete <id>                Delete a saved post by status ID.")
                print("  reload_instructions        Reload instructions from instructions.yaml (if used).")
                print("  help                       Show this help message.")
                print("  quit / exit                Exit the application.\n")
            elif cmd == "list":
                try:
                    limit = int(args_str.split(maxsplit=1)[0]) if args_str and args_str.split(maxsplit=1)[0].isdigit() else None
                except ValueError:
                    print("Invalid limit.")
                    continue
                list_posts(pipeline, limit)
            elif cmd == "stats":
                show_stats(pipeline)
            elif cmd == "delete":
                delete_id = args_str.strip()
                if delete_id:
                    await delete_post(pipeline, delete_id)
                else:
                    print("Usage: delete <status_id>")
            elif cmd == "scrape":
                url_to_scrape = args_str.strip()
                if url_to_scrape:
                    await pipeline.run(url_to_scrape)
                else:
                    print("Usage: scrape <url>")
            elif urlparse(user_input).scheme in ['http', 'https']:
                await pipeline.run(user_input)
            else:
                print(f"Unknown command/URL: {user_input}. Type 'help'.")
    finally:
        logger.info("Closing browser after interactive session...")
        await pipeline.close_browser()
        logger.info("Browser closed.")


@app.command(name="scrape")
async def scrape_command(url: str = typer.Argument(..., help="Tweet/Nitter URL to scrape")) -> None:
    """Scrape URL, process images, generate search terms, and save combined data."""
    pipeline = ScraperPipeline()
    await pipeline.data_manager.initialize()
    logger.info(f"Scraping URL via command: {url}")
    await pipeline.run(url)


@app.command(name="list")
def list_posts(limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Max posts to list.")) -> None:
    """List saved post metadata."""
    pipeline = ScraperPipeline()
    logger.info(f"Listing posts with limit: {limit}")
    posts = pipeline.data_manager.list_meta(limit)
    if not posts:
        print("No saved posts found.")
        return
    print("\n--- Saved Posts ---")
    for meta in posts:
        sid = meta.get('status_id', 'N/A')
        author = meta.get('author', 'Unk')
        date_str = meta.get('scrape_date', 'Unk')
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            fmt_date = dt.strftime('%Y-%m-%d %H:%M')
        except Exception:
            fmt_date = date_str
        print(f"ID: {sid:<20} Author: @{author:<18} Scraped: {fmt_date}")
    print("-------------------\n")


@app.command(name="stats")
def show_stats() -> None:
    """Show count of saved posts."""
    pipeline = ScraperPipeline()
    count = pipeline.data_manager.count()
    print(f"Total saved posts: {count}")


@app.command(name="delete")
async def delete_post(status_id: str = typer.Argument(..., help="Status ID to delete.")) -> None:
    """Delete a saved post by status ID."""
    pipeline = ScraperPipeline()
    await pipeline.data_manager.initialize()
    logger.info(f"Deleting post {status_id}")
    if await pipeline.data_manager.delete(status_id):
        print(f"Deleted post {status_id}.")
    else:
        print(f"Could not delete post {status_id} (not found or error).")


async def async_main() -> None:
    """Main async entry point."""
    pipeline = ScraperPipeline()
    is_interactive = len(sys.argv) <= 1 or sys.argv[1] not in app.registered_commands
    try:
        await pipeline.data_manager.initialize()
        if is_interactive:
            await run_interactive_mode_async(pipeline)
        else:
            browser_needed = any(cmd_name in sys.argv for cmd_name in ['scrape'])
            if browser_needed:
                await pipeline.initialize_browser()
            try:
                app()
            finally:
                if browser_needed:
                    await pipeline.close_browser()
    except Exception as e:
        logger.exception("Fatal error in main execution:")
        typer.echo(f"Fatal Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(async_main())
