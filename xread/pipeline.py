"""Pipeline orchestration for scraping, processing, and saving data in xread."""

from __future__ import annotations # For forward references

import re
import os
import asyncio
import base64
import mimetypes
import aiohttp
from typing import Optional, List, Dict, Any, Tuple, Type # Added Type
from types import TracebackType # For __aexit__
from datetime import datetime, timezone
from pathlib import Path

import typer
import aiofiles

from xread.settings import settings, logger
from xread.constants import ErrorMessages, FileFormats, PERPLEXITY_REPORT_PROMPT
from xread.models import ScrapedData, Post, UserProfile, AuthorNote # Added UserProfile, AuthorNote for type hints
from xread.scraper import NitterScraper
from xread.data_manager import DataManager
from xread.ai_models import PerplexityModel, GeminiModel, BaseAIModel # Added BaseAIModel
from xread.browser import BrowserManager
from xread.json_upgrader import upgrade_perplexity_json
from xread.utils import play_ding
from xread.exceptions import ( # Import custom exceptions
    XReadError,
    ScrapingError,
    AIModelError,
    DatabaseError,
    ConfigurationError,
    FileOperationError
)

class ScraperPipeline:
    """Orchestrates scraping, processing, generating search terms, and saving data."""
    scraper: NitterScraper
    data_manager: DataManager
    browser_manager: BrowserManager
    _browser_ready: bool
    ai_model: BaseAIModel # Use BaseAIModel for the type hint

    def __init__(self, data_manager: DataManager) -> None:
        self.scraper = NitterScraper()
        self.data_manager = data_manager
        self.browser_manager = BrowserManager()
        self._browser_ready = False
        # Dynamically select AI model based on settings
        selected_model_name: str = settings.ai_model.lower() # type hint for selected_model_name
        if selected_model_name == "gemini":
            self.ai_model = GeminiModel()
            logger.info("Using Gemini AI model for report generation.")
        else: # Default to Perplexity
            self.ai_model = PerplexityModel()
            logger.info("Using Perplexity AI model for report generation.")

    async def __aenter__(self) -> ScraperPipeline:
        """Asynchronously initialize the browser when entering the context."""
        await self.initialize_browser()
        logger.info("ScraperPipeline entered context, browser initialized.")
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType]
    ) -> None:
        """Asynchronously close the browser when exiting the context."""
        logger.info("ScraperPipeline exiting context, closing browser...")
        await self.close_browser()
        if exc_type:
            logger.error(f"ScraperPipeline exited with exception: {exc_type.__name__}", exc_info=(exc_type, exc_val, exc_tb))

    async def initialize_browser(self) -> None: # Already correct
        """Launch the Playwright browser if not already started."""
        if not self._browser_ready:
            await self.browser_manager.__aenter__()
            self._browser_ready = True

    async def close_browser(self) -> None:
        """Close the Playwright browser if it is running."""
        if self._browser_ready:
            await self.browser_manager.__aexit__(None, None, None)
            self._browser_ready = False

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
        except IOError as e:
            logger.error(f"File operation error saving failed HTML to {fpath}: {e}", exc_info=True)
            # Not raising FileOperationError here as this is a helper utility, not critical path
        except Exception as e:
            logger.error(f"Unexpected error saving failed HTML to {fpath}: {e}", exc_info=True)

    async def _prepare_url(self, url: str) -> Tuple[str, str]: # Use Tuple from typing
        """Prepare and normalize the URL for scraping, extracting the status ID."""
        try:
            normalized_url: str = self.scraper.normalize_url(url)
        except ValueError as e:
            logger.error(f"Invalid URL format for '{url}': {e}", exc_info=True)
            raise ScrapingError(f"Invalid URL format: {url}") from e

        sid_match: Optional[re.Match[str]] = re.search(settings.status_id_regex, normalized_url)
        if not sid_match or not sid_match.group(1):
            logger.error(f"Could not extract status ID from normalized URL: {normalized_url}")
            raise ScrapingError(f"Status ID extraction failed for URL: {normalized_url}")
        sid: str = sid_match.group(1)
        return normalized_url, sid

    async def _fetch_and_parse(self, normalized_url: str, sid: str) -> Tuple[Optional[str], ScrapedData]:
        """Fetch HTML content and parse it into structured data."""
        page = await self.browser_manager.new_page() # Page type is from playwright
        html_content: Optional[str] = None
        try:
            html_content = await self.scraper.fetch_html(page, normalized_url)
            scraped_data: ScrapedData = self.scraper.parse_html(html_content) # parse_html returns ScrapedData

            # Post-parsing logic, e.g., overriding main post based on URL SID
            if scraped_data.main_post: # Ensure main_post exists
                url_sid_match_in_parse = re.search(r'status/(\d+)', normalized_url)
                if url_sid_match_in_parse:
                    url_sid_from_norm = url_sid_match_in_parse.group(1)
                    if url_sid_from_norm != scraped_data.main_post.status_id:
                        logger.info(f"URL status ID {url_sid_from_norm} doesn't match main post ID {scraped_data.main_post.status_id}. Attempting to find and swap.")
                        original_main_post = scraped_data.main_post
                        found_and_swapped = False
                        for i, reply in enumerate(scraped_data.replies):
                            if reply.status_id == url_sid_from_norm:
                                logger.info(f"Found reply matching URL status ID {url_sid_from_norm}, swapping with main post.")
                                scraped_data.main_post = reply
                                scraped_data.replies.pop(i) # Remove the swapped reply
                                scraped_data.replies.append(original_main_post) # Add old main post as a reply
                                found_and_swapped = True
                                break
                        if not found_and_swapped:
                            logger.warning(f"Could not find reply matching URL SID {url_sid_from_norm} to swap with main post.")
            
            return html_content, scraped_data # html_content can be None if fetch_html returns None but doesn't raise
        except ScrapingError: # Let ScrapingError from fetch_html/parse_html propagate
            # Save HTML if parsing failed or fetch indicated an error that parse_html would catch
            if html_content: # html_content might be set even if parse_html fails
                 await self._save_failed_html(sid, html_content)
            raise
        except Exception as e: # Catch any other unexpected error during fetch/parse
            logger.error(f"Unexpected error during fetch and parse for {normalized_url}: {e}", exc_info=True)
            if html_content:
                await self._save_failed_html(sid, html_content)
            raise ScrapingError(f"Unexpected error processing {normalized_url}") from e
        finally:
            if page and not page.is_closed():
                try:
                    await page.close()
                except Exception as e: # PlaywrightError might be more specific if available
                    logger.warning(f"Error closing page for {normalized_url}: {e}", exc_info=True)

    async def _generate_ai_report(self, scraped_data: ScrapedData, sid: str) -> Optional[str]:
        """Generate a factual report. AIModel methods should raise AIModelError or ConfigurationError."""
        try:
            return await self.ai_model.generate_report(scraped_data, sid)
        except ConfigurationError: # Let ConfigurationError propagate
            raise
        except AIModelError: # Let AIModelError propagate
            raise
        except Exception as e: # Catch any other unexpected error from AI model
            logger.error(f"Unexpected error generating AI report for {sid}: {e}", exc_info=True)
            raise AIModelError(f"Unexpected error during AI report generation for {sid}") from e

    async def _save_results(
        self,
        scraped_data: ScrapedData,
        url: str,
        ai_report: Optional[str],
        sid: str,
        author_profile: Optional['UserProfile'] = None,
        url_sid: Optional[str] = None
    ) -> None:
        """Save the scraped data along with the generated AI report processed for factual context."""
        # If the URL status ID is available and different from the main post ID,
        # use it to override the main post's status ID for saving
        if url_sid and url_sid != sid:
            logger.info(f"Using URL status ID {url_sid} for saving instead of main post ID {sid}")
            # Clone the main post and update its status_id
            import copy
            modified_data = copy.deepcopy(scraped_data)
            modified_data.main_post.status_id = url_sid
            author_note = await self.data_manager.get_author_note(scraped_data.main_post.username)
            saved_sid = await self.data_manager.save(modified_data, url, ai_report, author_profile, author_note)
        else:
            author_note = await self.data_manager.get_author_note(scraped_data.main_post.username)
            saved_sid = await self.data_manager.save(scraped_data, url, ai_report, author_profile, author_note)

        if saved_sid:
            logger.info(f"Successfully saved post {sid}")
            typer.echo(f"Success: Saved post {sid}.")
        else:
            save_id = url_sid if url_sid else sid
            if save_id and save_id not in self.data_manager.seen:
                typer.echo(f"Error: Failed to save data for post {save_id}.", err=True)

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

    async def run(self, url: str) -> Optional[ScrapedData]: # Return type updated
        """Run the full pipeline: scrape, process images, generate terms, and save."""
        # Browser initialization is handled by __aenter__ when used as a context manager
        # await self.initialize_browser() # This call is redundant if used as context manager
        logger.info(f"Starting pipeline for {url}")
        
        # Declare variables that might be used in finally or except blocks before try
        normalized_url: Optional[str] = None
        sid: Optional[str] = None # sid can be None if _prepare_url fails before assignment
        html_content: Optional[str] = None # For saving failed HTML
        scraped_data_obj: Optional[ScrapedData] = None # To hold the result

        try:
            normalized_url, sid = await self._prepare_url(url)

            url_sid_match_direct: Optional[re.Match[str]] = re.search(r'status/(\d+)', url)
            url_sid: Optional[str] = url_sid_match_direct.group(1) if url_sid_match_direct else None
            if url_sid:
                logger.info(f"Extracted URL status ID (direct from input): {url_sid}")

            if sid in self.data_manager.seen:
                logger.info(f"Post {sid} (from normalized URL) has already been processed. Skipping.")
                typer.echo(f"Skipped (already saved): {sid}")
                return None

            html_content, scraped_data_obj = await self._fetch_and_parse(normalized_url, sid)

            ai_report_content: Optional[str] = await self._generate_ai_report(scraped_data_obj, sid)
            if not ai_report_content:
                 logger.warning(f"AI report generation returned None/empty for post {sid} without raising error. Defaulting to error message.")
                 ai_report_content = "Error: AI report generation failed or returned no content."
            
            author_username: str = scraped_data_obj.main_post.username
            author_profile: Optional[UserProfile] = await self.data_manager.get_user_profile(author_username)
            author_note_obj: Optional[AuthorNote] = await self.data_manager.get_author_note(author_username)

            # --- JSON upgrade ---
            # Ensure scraped_data_obj and its main_post are not None before accessing __dict__
            if not scraped_data_obj or not scraped_data_obj.main_post:
                raise XReadError("Scraped data or main post is missing before JSON upgrade.")

            scraped_data_dict: Dict[str, Any] = {
                "main_post": scraped_data_obj.main_post.__dict__,
                "replies": [reply.__dict__ for reply in scraped_data_obj.replies],
                "ai_report": ai_report_content, # Use the fetched ai_report_content
                "scrape_date": datetime.now(timezone.utc).isoformat(), # current time
                "source": None,  # Placeholder, could be derived from URL or context
                "topic_tags": scraped_data_obj.main_post.topic_tags or []
            }
            if author_note_obj: # Check if author_note_obj is not None
                scraped_data_dict["author_note"] = author_note_obj.note_content

            upgraded_data: Dict[str, Any] = upgrade_perplexity_json(scraped_data_dict)

            # Update main_post fields from upgraded_data
            main_post_upgraded_data = upgraded_data.get("main_post", {})
            for key, value in main_post_upgraded_data.items():
                if hasattr(scraped_data_obj.main_post, key):
                    setattr(scraped_data_obj.main_post, key, value)

            # Update replies from upgraded_data
            upgraded_replies_data = upgraded_data.get("replies", [])
            new_replies: List[Post] = []
            for reply_dict in upgraded_replies_data:
                # Ensure essential fields for Post creation, providing defaults if necessary
                reply_dict.setdefault('user', 'Unknown User')
                reply_dict.setdefault('username', 'unknown_username')
                reply_dict.setdefault('text', '')
                reply_dict.setdefault('date', '') # Default to empty string if missing
                reply_dict.setdefault('permalink', f"#{reply_dict.get('status_id', 'unknown_id')}")
                reply_dict.setdefault('images', [])
                # Ensure engagement metrics are suitable for int conversion or None
                for metric in ['likes', 'retweets', 'replies_count']:
                    if metric not in reply_dict or reply_dict.get(metric) in [0, '0', None, 'N/A', '']:
                        reply_dict[metric] = None # Pydantic will handle Optional[int]
                    else: # try to convert to int, if fails set to None
                        try:
                            reply_dict[metric] = int(reply_dict[metric])
                        except (ValueError, TypeError):
                            reply_dict[metric] = None
                
                # Handle topic_tags specifically if it exists in reply_dict and is not a list
                if 'topic_tags' in reply_dict and not isinstance(reply_dict['topic_tags'], list):
                    reply_dict['topic_tags'] = [str(reply_dict['topic_tags'])] if reply_dict['topic_tags'] else []
                elif 'topic_tags' not in reply_dict:
                     reply_dict['topic_tags'] = []


                try:
                    reply_post_obj: Post = Post(**reply_dict)
                    new_replies.append(reply_post_obj)
                except Exception as post_creation_err: # Catch error during Post creation
                    logger.error(f"Error creating Post object from reply dict {reply_dict}: {post_creation_err}", exc_info=True)
            scraped_data_obj.replies = new_replies
            
            scraped_data_obj.factual_context = upgraded_data.get("factual_context")
            scraped_data_obj.source = upgraded_data.get("scrape_meta", {}).get("source")
            
            # Update author_note on scraped_data_obj if applicable
            upgraded_author_note_content = upgraded_data.get("author_note")
            if upgraded_author_note_content:
                if author_note_obj: # If an AuthorNote object was fetched
                    author_note_obj.note_content = upgraded_author_note_content
                    # If scraped_data_obj might not have author_note attached yet
                    if not hasattr(scraped_data_obj, 'author_note') or scraped_data_obj.author_note is None:
                         scraped_data_obj.author_note = author_note_obj
                elif hasattr(scraped_data_obj, 'author_note') and scraped_data_obj.author_note is not None:
                    # If there's an existing AuthorNote object on scraped_data for some reason
                    scraped_data_obj.author_note.note_content = upgraded_author_note_content
                # else: no existing AuthorNote object to update, and none was fetched, so can't store upgraded note directly on ScrapedData without creating one.

            await self._save_results(scraped_data_obj, url, ai_report_content, sid, author_profile, url_sid)
            
            play_ding()
            return scraped_data_obj

        except ConfigurationError as e:
            logger.error(f"Configuration error in pipeline for {url}: {e}", exc_info=True)
            raise
        except ScrapingError as e:
            logger.error(f"Scraping error in pipeline for {url}: {e}", exc_info=True)
            raise
        except AIModelError as e:
            logger.error(f"AI Model error in pipeline for {url}: {e}", exc_info=True)
            raise
        except DatabaseError as e:
            logger.error(f"Database error in pipeline for {url}: {e}", exc_info=True)
            raise
        except FileOperationError as e:
            logger.error(f"File operation error in pipeline for {url}: {e}", exc_info=True)
            raise
        except XReadError as e:
            logger.error(f"Application error in pipeline for {url}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.critical(f"Unexpected critical error in pipeline for {url}: {e}", exc_info=True)
            raise XReadError(f"An unexpected critical error occurred in the pipeline processing {url}.") from e
        # Browser closing is handled by __aexit__
