"""Browser management functionality for Playwright in xread."""

from __future__ import annotations # For forward references

from typing import Optional, Type
from types import TracebackType # For __aexit__
from playwright.async_api import async_playwright, Browser, Page, Playwright, BrowserContext

from xread.settings import logger

class BrowserManager:
    """Manages a Playwright browser instance."""
    def __init__(self) -> None:
        self.browser: Optional[Browser] = None
        self.playwright: Optional[Playwright] = None
        self._entered: bool = False

    async def __aenter__(self) -> BrowserManager:
        logger.info("Launching Playwright browser.")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.firefox.launch(headless=True)
        logger.info("Using Firefox.")
        self._entered = True
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType]
    ) -> None:
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
            # Consider replacing RuntimeError with a custom exception if available e.g. BrowserError
            raise RuntimeError("BrowserManager is not active or browser not launched. Use 'async with BrowserManager() as bm:'.")
        
        # Type hint for ctx
        ctx: BrowserContext = await self.browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0'
        )
        page: Page = await ctx.new_page()
        logger.debug("New browser page created.")
        return page
