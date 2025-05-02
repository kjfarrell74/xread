"""Browser management functionality for Playwright in xread."""

from typing import Optional
from playwright.async_api import async_playwright, Browser, Page, Playwright

from xread.settings import logger

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
