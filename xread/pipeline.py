"""Pipeline orchestration for scraping, processing, and saving data in xread."""

import re
import aiohttp
from typing import Optional
from datetime import datetime
from pathlib import Path

import typer
import aiofiles

from xread.settings import settings, logger
from xread.constants import ErrorMessages, SEARCH_TERM_PROMPT, RESEARCH_QUESTIONS_PROMPT, FileFormats
from xread.models import ScrapedData
from xread.utils import load_instructions
from xread.scraper import NitterScraper
from xread.data_manager import DataManager
from xread.gemini import GeminiProcessor
from xread.browser import BrowserManager

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
