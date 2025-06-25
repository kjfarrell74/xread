"""Web scraping functionality for extracting tweet data from Nitter instances in xread."""

import re
from typing import Optional, Dict, Set
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from xread.constants import PAGE_READY_SELECTOR, TimeoutConstants, NA_PLACEHOLDER
from xread.core.utils import with_retry
from xread.exceptions import NetworkError, ParseError, InvalidURLError
from xread.models import ScrapedData, Post, Image
from xread.settings import settings, logger

class NitterScraper:
    """Scrapes data from a Nitter instance using Playwright and BeautifulSoup."""
    def __init__(self):
        self.base_urls = [str(url).rstrip('/') for url in settings.nitter_instances]
        self.base_url = self.base_urls[0] if self.base_urls else str(settings.nitter_base_url).rstrip('/')

    def _normalize_url_pattern(self, url: str) -> tuple[str, str]:
        """Extract user and status ID from URL pattern."""
        url = url.strip()
        match = re.search(settings.full_url_regex, url, re.IGNORECASE)
        if match:
            return match.groups()
        raise InvalidURLError(f"Invalid URL format: {url}")

    def normalize_url(self, url: str, base_url: str = None) -> str:
        """Normalize user-provided URL to a Nitter URL."""
        user, sid = self._normalize_url_pattern(url)
        return f"{base_url or self.base_url}/{user}/status/{sid}"

    async def fetch_html(self, page: Page, url: str) -> Optional[str]:
        """Use Playwright to fetch page HTML content, trying multiple Nitter instances if necessary."""
        original_url = url
        for base_url in self.base_urls:
            normalized_url = self.normalize_url(original_url, base_url)
            logger.info(f"Fetching HTML from {normalized_url} using base {base_url}")
            try:
                response = await page.goto(normalized_url, wait_until='load', timeout=TimeoutConstants.PLAYWRIGHT_PAGE_LOAD_MS)
                if not response:
                    logger.warning(f"No response for {normalized_url}")
                    continue
                if response.status != 200:
                    if 300 <= response.status < 400:
                        logger.warning(f"Redirected from {normalized_url} (Status: {response.status}). Stopping.")
                        continue
                    logger.warning(f"Non-200 response for {normalized_url}: Status {response.status}")
                    if response.status >= 500:
                        logger.warning(f"Server error (Status: {response.status}) for {normalized_url}. Stopping.")
                        continue
                try:
                    await page.wait_for_selector(PAGE_READY_SELECTOR, state='visible', timeout=TimeoutConstants.PLAYWRIGHT_SELECTOR_MS)
                    logger.info(f"Found '{PAGE_READY_SELECTOR}'")
                except Exception:
                    logger.warning(f"'{PAGE_READY_SELECTOR}' not found/visible. Proceeding anyway.")
                await page.wait_for_timeout(TimeoutConstants.PLAYWRIGHT_POST_LOAD_DELAY_MS)
                html_content = await page.content()
                if not html_content:
                    logger.warning(f"Empty HTML from {normalized_url}")
                    continue
                if self._is_error_content(html_content):
                    logger.warning(f"Content from {normalized_url} indicates error: {html_content[:200]}...")
                logger.info(f"Fetched HTML ({len(html_content)} bytes) from {normalized_url}")
                self.base_url = base_url  # Update the primary base URL to the successful one
                return html_content
            except PlaywrightTimeoutError as e:
                logger.error(f"Timeout error fetching {normalized_url}: {e}")
                await self._handle_fetch_error(e, normalized_url, page)
                continue
            except aiohttp.ClientError as e:
                logger.error(f"Client error fetching {normalized_url}: {e}")
                await self._handle_fetch_error(e, normalized_url, page)
                continue
            except Exception as e:
                logger.error(f"Unexpected error fetching {normalized_url}: {e}")
                await self._handle_fetch_error(e, normalized_url, page)
                continue
        
        logger.error(f"All Nitter instances failed for {original_url}")
        raise NetworkError(f"All Nitter instances failed for {original_url}")

    def _is_error_content(self, html_content: str) -> bool:
        """
        Check if the HTML content contains known error indicators.
        """
        return any(
            err in html_content
            for err in ("Tweet not found", "Instance has been rate limited", "User not found")
        )

    async def _handle_fetch_error(self, e: Exception, normalized_url: str, page: Page) -> None:
        """Handle errors during HTML fetching."""
        logger.error(f"Error fetching {normalized_url}: {e}")
        try:
            partial_content = await page.content()
            if partial_content:
                logger.debug(f"Partial content captured despite error for {normalized_url}: {partial_content[:200]}...")
            else:
                logger.debug(f"No partial content available for {normalized_url}")
        except Exception as partial_e:
            logger.debug(f"Failed to capture partial content for {normalized_url}: {partial_e}")

    def parse_html(self, html: str) -> Optional[ScrapedData]:
        """Parse HTML content and extract main post and replies."""
        if not html:
            logger.error("Parsing skipped: No HTML.")
            return None
        soup = BeautifulSoup(html, 'html.parser')
        if not self._validate_content(soup):
            return None
        combined_selector = ", ".join(settings.tweet_selectors)
        all_posts = soup.select(combined_selector)
        valid_posts = self._filter_valid_posts(all_posts)
        if not valid_posts:
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

    def _validate_content(self, soup: BeautifulSoup) -> bool:
        """Validate that the content doesn't contain error messages."""
        error_text = soup.find(
            string=re.compile("Tweet not found|Instance has been rate limited|User not found", re.IGNORECASE)
        )
        if error_text:
            logger.error("Parsing failed: Page indicates error.")
            return False
        return True

    def _filter_valid_posts(self, all_posts: list) -> list:
        valid_posts = [
            el for el in all_posts
            if el.select_one('.username, .handle') and el.select_one('.tweet-content, .content')
        ]
        if not valid_posts:
            logger.warning("Elements matched but none contained username/content.")
        return valid_posts

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
