"""Web scraping functionality for extracting tweet data from Nitter instances in xread."""

import re
from typing import Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.async_api import Page, Error as PlaywrightError # Import PlaywrightError

from xread.settings import settings, logger
from xread.constants import PAGE_READY_SELECTOR, TimeoutConstants, NA_PLACEHOLDER
from xread.models import ScrapedData, Post, Image
from xread.utils import with_retry
from xread.exceptions import ScrapingError # Import custom exception

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
            except Exception:
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
        except PlaywrightError as e: # Catch Playwright specific errors
            logger.error(f"Playwright error fetching {url}: {e}", exc_info=True)
            raise ScrapingError(f"Playwright operation failed while fetching {url}") from e
        except Exception as e: # Catch any other exceptions
            logger.error(f"Generic error fetching {url}: {e}", exc_info=True)
            raise ScrapingError(f"Failed to fetch {url} due to an unexpected error") from e

    def parse_html(self, html: str) -> ScrapedData: # Changed return type to ScrapedData (non-optional)
        """Parse HTML content and extract main post and replies."""
        if not html:
            logger.error("Parsing skipped: No HTML content provided.")
            raise ScrapingError("Cannot parse empty HTML content.") # Raise error
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check for explicit error messages in the page
        error_messages = ["Tweet not found", "Instance has been rate limited", "User not found"]
        for error_msg in error_messages:
            if error_msg in html: # Check raw HTML as well, sometimes error messages are not in specific tags
                 logger.error(f"Parsing failed: Page indicates error: '{error_msg}'")
                 raise ScrapingError(f"Page indicates error: '{error_msg}'")

        combined_selector = ", ".join(settings.tweet_selectors)
        all_posts = soup.select(combined_selector)
        if not all_posts:
            logger.warning(f"No elements matched selectors: {settings.tweet_selectors}. HTML might be unexpected.")
            # Consider if this should be an error or if an empty ScrapedData is valid in some cases.
            # For now, let's assume it's an error if no posts are found.
            raise ScrapingError(f"No tweet elements found using selectors: {settings.tweet_selectors}")
            
        valid_posts = [
            el for el in all_posts
            if el.select_one('.username, .handle') and el.select_one('.tweet-content, .content')
        ]
        if not valid_posts:
            logger.warning("Elements matched tweet selectors, but no valid posts with username/content found.")
            raise ScrapingError("No valid tweet content (username/text) found in matched elements.")
            
        main_element = valid_posts[0]
        reply_elements = valid_posts[1:]
        
        try:
            main_post = self._extract_post_data(main_element)
            if not main_post.text or main_post.text == NA_PLACEHOLDER: # Ensure main post has content
                logger.error("Main post parsing resulted in empty text content.")
                raise ScrapingError("Failed to extract valid text content for the main post.")

            replies = [self._extract_post_data(el) for el in reply_elements]
            # Filter out exact duplicate replies and replies identical to main post
            unique_replies: Dict[str, Post] = {}
            main_post_key = main_post.status_id or main_post.permalink # Use a more descriptive name
            if main_post_key and main_post_key != NA_PLACEHOLDER:
                 # This logic implies we don't want the main post to appear as a reply
                 # If main_post_key is None or NA, it might be an issue with main_post extraction
                 pass

            for reply in replies:
                reply_key = reply.status_id or reply.permalink
                # Ensure reply is valid, not a duplicate of another reply, and not a duplicate of the main post
                if reply_key and reply_key != NA_PLACEHOLDER and \
                   reply_key not in unique_replies and \
                   reply_key != main_post_key:
                    unique_replies[reply_key] = reply
            
            final_replies = list(unique_replies.values())
            logger.info(f"Parsed main post and {len(final_replies)} unique replies.")
            return ScrapedData(main_post=main_post, replies=final_replies)

        except Exception as e: # Catch any other error during data extraction
            logger.error(f"Error extracting post data: {e}", exc_info=True)
            raise ScrapingError(f"Failed to extract post data due to an unexpected error: {e}") from e

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
