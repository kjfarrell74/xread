"""Pipeline orchestration for scraping, processing, and saving data in xread."""

import re
import os
import asyncio
import base64
import mimetypes
import aiohttp
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from pathlib import Path

import typer
import aiofiles

from xread.settings import settings, logger
from xread.constants import ErrorMessages, FileFormats, PERPLEXITY_REPORT_PROMPT
from xread.models import ScrapedData, Post
from xread.scraper import NitterScraper
from xread.data_manager import DataManager
from xread.ai_models import PerplexityModel, GeminiModel
from xread.browser import BrowserManager
from xread.json_upgrader import upgrade_perplexity_json
from xread.utils import play_ding

class ScraperPipeline:
    """Orchestrates scraping, processing, generating search terms, and saving data."""
    def __init__(self, data_manager: DataManager):
        self.scraper = NitterScraper()
        self.data_manager = data_manager
        self.browser_manager = BrowserManager()
        self._browser_ready = False
        # Dynamically select AI model based on settings
        selected_model = settings.ai_model.lower()
        if selected_model == "gemini":
            self.ai_model = GeminiModel()
            logger.info("Using Gemini AI model for report generation.")
        else:
            self.ai_model = PerplexityModel()
            logger.info("Using Perplexity AI model for report generation.")

    async def __aenter__(self):
        """Asynchronously initialize the browser when entering the context."""
        await self.initialize_browser()
        logger.info("ScraperPipeline entered context, browser initialized.")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Asynchronously close the browser when exiting the context."""
        logger.info("ScraperPipeline exiting context, closing browser...")
        await self.close_browser()
        if exc_type:
            logger.error(f"ScraperPipeline exited with exception: {exc_type.__name__}", exc_info=(exc_type, exc_val, exc_tb))

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

            # Check if we need to override the main post based on URL status ID
            url_sid_match = re.search(r'status/(\d+)', normalized_url)
            if url_sid_match:
                url_sid = url_sid_match.group(1)
                if url_sid != scraped_data.main_post.status_id:
                    logger.info(f"URL status ID {url_sid} doesn't match main post ID {scraped_data.main_post.status_id}")

                    # Search for a matching reply with the URL status ID
                    for reply in scraped_data.replies:
                        if reply.status_id == url_sid:
                            logger.info(f"Found reply matching URL status ID {url_sid}, swapping with main post")
                            # Swap the reply with the main post
                            temp = scraped_data.main_post
                            scraped_data.main_post = reply
                            # Move the old main post to replies
                            scraped_data.replies.remove(reply)
                            scraped_data.replies.append(temp)
                            break

            return html_content, scraped_data
        finally:
            try:
                await page.close()
            except Exception as e:
                logger.warning(f"Error closing page: {e}")

    async def _generate_ai_report(self, scraped_data: ScrapedData, sid: str) -> Optional[str]:
        """Generate a factual report using the selected AI model based on the scraped text content and images."""
        return await self.ai_model.generate_report(scraped_data, sid)

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

    async def run(self, url: str) -> None:
        """Run the full pipeline: scrape, process images, generate terms, and save."""
        await self.initialize_browser()
        logger.info(f"Starting pipeline for {url}")
        
        try:
            normalized_url, sid = await self._prepare_url(url)

            # Extract the status ID directly from the URL, which might be different from the main post ID
            url_sid = None
            import re
            url_sid_match = re.search(r'status/(\d+)', url)
            if url_sid_match:
                url_sid = url_sid_match.group(1)
                logger.info(f"Extracted URL status ID: {url_sid}")

            # Check both the main post ID and URL ID
            if sid in self.data_manager.seen:
                if url_sid and url_sid != sid and url_sid not in self.data_manager.seen:
                    logger.info(f"Main post {sid} seen, but URL post {url_sid} not seen. Continuing.")
                else:
                    logger.info(f"Post {sid} seen. Skipping.")
                    typer.echo(f"Skipped (already saved): {sid}")
                    return
                
            html_content, scraped_data = await self._fetch_and_parse(normalized_url, sid)
            if not scraped_data:
                if html_content:
                    await self._save_failed_html(sid, html_content)
                return
                
            # Generate AI report with text and images using the selected model
            ai_report = await self._generate_ai_report(scraped_data, sid)
            if ai_report:
                logger.info(f"Generated AI report for post {sid}")
            else:
                logger.warning(f"Failed to generate AI report for post {sid}")
                ai_report = "Error: Failed to generate AI report."

            # Look up author profile and author note
            author_username = scraped_data.main_post.username
            author_profile = await self.data_manager.get_user_profile(author_username)
            if author_profile:
                logger.info(f"Found user profile for {author_username} in database.")
            else:
                logger.info(f"No user profile found for {author_username} in database.")
            
            author_note = None  # Assign a default value
            author_note = await self.data_manager.get_author_note(author_username)
            if author_note:
                logger.info(f"Found author note for {author_username} in database.")
            else:
                logger.info(f"No author note found for {author_username} in database.")

            # --- Integration of JSON upgrade ---
            # Convert ScrapedData to dict for upgrading
            scraped_data_dict = {
                "main_post": scraped_data.main_post.__dict__,
                "replies": [reply.__dict__ for reply in scraped_data.replies],
                "ai_report": ai_report,
                "scrape_date": datetime.now(timezone.utc).isoformat(),
                "source": None,  # Could extract from URL or elsewhere
                "topic_tags": scraped_data.main_post.topic_tags or []
            }
            if author_note:
                scraped_data_dict["author_note"] = author_note.note_content

            # Perform upgrade
            upgraded_data = upgrade_perplexity_json(scraped_data_dict)

            # Update scraped_data with upgraded data
            # Update main_post fields
            for key, value in upgraded_data.get("main_post", {}).items():
                setattr(scraped_data.main_post, key, value)

            # Update replies
            scraped_data.replies = []
            for reply_dict in upgraded_data.get("replies", []):
                # Ensure reply dates and engagement metrics are set properly
                if 'date' not in reply_dict or not reply_dict['date']:
                    reply_dict['date'] = ''
                for metric in ['likes', 'retweets', 'replies_count']:
                    if metric not in reply_dict or reply_dict.get(metric) in [0, '0', None]:
                        reply_dict[metric] = None
                # Create Post objects for replies
                reply_post = Post(**reply_dict)
                scraped_data.replies.append(reply_post)

            # Update factual_context and source in ScrapedData
            scraped_data.factual_context = upgraded_data.get("factual_context", None)
            scraped_data.source = upgraded_data.get("scrape_meta", {}).get("source", None)

            # ADD THIS SECTION TO UPDATE AUTHOR NOTE
            if author_note:
                # Ensure author_note exists in scraped_data
                if not hasattr(scraped_data, 'author_note'):
                    scraped_data.author_note = author_note
                # Update author_note in scraped_data
                scraped_data.author_note.note_content = upgraded_data.get("author_note")

            # Save results with upgraded data
            await self._save_results(scraped_data, url, ai_report, sid, author_profile, url_sid)
            # Play notification sound after successful scrape and save
            play_ding()

        except ValueError as e:
            logger.error(f"URL/Input error: {e}")
            typer.echo(f"Error: {e}", err=True)
        except Exception as e:
            logger.exception(f"Unexpected pipeline error for {url}: {e}")
            typer.echo(f"Error: An unexpected error occurred: {e}", err=True)
            if html_content and scraped_data is None:
                await self._save_failed_html(sid, html_content)
