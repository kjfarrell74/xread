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
from xread.exceptions import FetchError, ParseError
from xread.scraper import NitterScraper
from xread.data_manager import DataManager
from xread.ai_models import AIModelFactory, AIModelError, BaseAIModel
from xread.browser import BrowserManager

class ScraperPipeline:
    """Orchestrates scraping, processing, generating search terms, and saving data."""
    def __init__(self):
        self.scraper = NitterScraper()
        self.data_manager = DataManager()
        self.ai_model: Optional[BaseAIModel] = None
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

    async def _fetch_and_parse(self, normalized_url: str, sid: str) -> ScrapedData:
        """Fetch HTML content and parse it into structured data."""
        page = await self.browser_manager.new_page()
        html_content: Optional[str] = None # Ensure html_content is defined for _save_failed_html
        try:
            html_content = await self.scraper.fetch_html(page, normalized_url)
            if not html_content:
                logger.error(f"Fetch failed for {normalized_url}")
                typer.echo(f"Error: {ErrorMessages.FETCH_FAILED}", err=True)
                raise FetchError(f"Failed to fetch HTML for {normalized_url}")

            scraped_data = self.scraper.parse_html(html_content)
            if not scraped_data:
                logger.error(f"Parse failed for {normalized_url}")
                typer.echo(f"Error: {ErrorMessages.PARSE_FAILED}", err=True)
                await self._save_failed_html(sid, html_content) # html_content will be available here
                raise ParseError(f"Failed to parse HTML for {normalized_url}")
            return scraped_data
        finally:
            try:
                await page.close()
            except Exception as e:
                logger.warning(f"Error closing page: {e}")

    async def _process_media(self, scraped_data: ScrapedData, sid: str) -> None:
        """Process images in the scraped data if conditions are met."""
        if not (self.ai_model and settings.max_image_downloads > 0):
            logger.info("Image processing skipped (AI model not configured or max_image_downloads is 0).")
            return
        
        try:
            async with aiohttp.ClientSession() as session:
                logger.info(f"Processing images for post {sid}...")
                await self.ai_model.process_images(scraped_data.main_post, session, "post")
                for reply in scraped_data.replies:
                    if self.ai_model.downloaded_count >= settings.max_image_downloads:
                        break
                    await self.ai_model.process_images(reply, session, "reply")
        except AIModelError as e:
            logger.warning(f"AI image processing failed for post {sid}: {e}")

    async def _generate_search_terms(self, scraped_data: ScrapedData, sid: str) -> Optional[str]:
        """Generate search terms based on scraped text content."""
        if not self.ai_model:
            logger.info("Search term generation skipped (AI model not available).")
            return "Skipped: AI model not available."

        logger.info(f"Generating search terms for post {sid}...")
        full_text = scraped_data.get_full_text()
        if full_text.strip():
            try:
                prompt = SEARCH_TERM_PROMPT.format(scraped_text=full_text)
                search_terms = await self.ai_model.generate_text_native(
                    prompt, f"Search Term Generation (Post ID: {sid})"
                )
                # The model methods now raise AIModelError instead of returning "Error:..."
                # So, the check below might be less relevant unless the model can still return such strings for non-fatal warnings.
                if search_terms and (search_terms.startswith("Error:") or search_terms.startswith("Warning:")):
                     logger.warning(f"AI model returned a warning/error string for search terms for {sid}: {search_terms}")
                return search_terms
            except AIModelError as e:
                logger.warning(f"AI search term generation failed for post {sid}: {e}")
                return "Error: Search term generation failed."
        logger.warning(f"Post {sid} has no text content for search term generation.")
        return "Info: No text content provided for analysis."

    async def _generate_research_questions(self, scraped_data: ScrapedData, sid: str) -> Optional[str]:
        """Generate research questions based on scraped text content."""
        if not self.ai_model:
            logger.info("Research questions generation skipped (AI model not available).")
            return "Skipped: AI model not available."

        logger.info(f"Generating research questions for post {sid}...")
        full_text = scraped_data.get_full_text()
        if full_text.strip():
            try:
                prompt = RESEARCH_QUESTIONS_PROMPT.format(scraped_text=full_text)
                research_questions = await self.ai_model.generate_text_native(
                    prompt, f"Research Questions Generation (Post ID: {sid})"
                )
                if research_questions and (research_questions.startswith("Error:") or research_questions.startswith("Warning:")):
                    logger.warning(f"AI model returned a warning/error string for research questions for {sid}: {research_questions}")
                return research_questions
            except AIModelError as e:
                logger.warning(f"AI research questions generation failed for post {sid}: {e}")
                return "Error: Research questions generation failed."
        logger.warning(f"Post {sid} has no text content for research questions generation.")
        return "Info: No text content provided for analysis."

    async def _save_results(self, scraped_data: ScrapedData, url: str, search_terms: Optional[str], research_questions: Optional[str], sid: str, author_profile: Optional['UserProfile'] = None) -> None:
        """Save the scraped data along with generated content and author profile."""
        saved_sid = await self.data_manager.save(scraped_data, url, search_terms, research_questions, author_profile)
        if saved_sid:
            logger.info(f"Successfully saved post {saved_sid}")
            typer.echo(f"Success: Saved post {saved_sid}.")
        else:
            if sid and sid not in self.data_manager.seen:
                typer.echo(f"Error: Failed to save data for post {sid}.", err=True)

    async def _ensure_ai_model(self) -> bool:
        """Initialise the configured AI model the first time it is needed."""
        if self.ai_model:
            return True
        model_type = settings.ai_model_type
        try:
            if model_type == "gemini":
                cfg = {
                    "api_key": settings.gemini_api_key,
                    "image_model": settings.image_description_model,
                    "text_model": settings.text_analysis_model,
                    "max_image_downloads": settings.max_image_downloads,
                }
            elif model_type == "claude":
                cfg = {
                    "api_key": settings.claude_api_key,
                    "model": settings.claude_model,
                    "max_image_downloads": settings.max_image_downloads,
                }
            else:
                cfg = {}
            self.ai_model = await AIModelFactory.create(model_type, self.data_manager, cfg)
            return True
        except (ValueError, AIModelError) as e:
            logger.error(f"AI model init error: {e}")
            self.ai_model = None
            return False

    async def run(self, url: str) -> None:
        """Run the full pipeline: scrape, process images, generate terms, and save."""
        # Ensure model
        if not await self._ensure_ai_model():
            typer.echo("Error: AI model could not be initialised. Aborting.", err=True)
            return

        await self.initialize_browser()
        logger.info(f"Starting pipeline for {url} (model: {settings.ai_model_type})")
        self.ai_model.downloaded_count = 0
        
        try:
            normalized_url, sid = await self._prepare_url(url)
            if sid in self.data_manager.seen:
                logger.info(f"Post {sid} seen. Skipping.")
                typer.echo(f"Skipped (already saved): {sid}")
                return

            scraped_data = await self._fetch_and_parse(normalized_url, sid)
            
            await self._process_media(scraped_data, sid)
            search_terms = await self._generate_search_terms(scraped_data, sid)
            research_questions = await self._generate_research_questions(scraped_data, sid)
            
            author_username = scraped_data.main_post.username
            author_profile = await self.data_manager.get_user_profile(author_username)
            if author_profile:
                logger.info(f"Found user profile for {author_username} in database.")
            else:
                logger.info(f"No user profile found for {author_username} in database.")
            
            await self._save_results(scraped_data, url, search_terms, research_questions, sid, author_profile)
        
        except FetchError as e:
            logger.error(f"Fetch error processing {url}: {e}")
            # typer.echo is handled in _fetch_and_parse
            return
        except ParseError as e:
            logger.error(f"Parse error processing {url}: {e}")
            # typer.echo and _save_failed_html are handled in _fetch_and_parse
            return
        except ValueError as e: # Handles errors from _prepare_url
            logger.error(f"URL/Input error for {url}: {e}")
            typer.echo(f"Error: {e}", err=True)
            return
        except Exception as e: # General catch-all for other unexpected errors
            logger.exception(f"Unexpected pipeline error for {url}: {e}")
            typer.echo(f"Error: An unexpected error occurred processing {url}: {e}", err=True)
            return
