"""Web scraping functionality for extracting tweet data from Nitter instances in xread."""

import re
from typing import Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.async_api import Page

from xread.settings import settings, logger
from xread.constants import PAGE_READY_SELECTOR, TimeoutConstants, NA_PLACEHOLDER
from xread.models import ScrapedData, Post, Image
from xread.core.utils import with_retry

class NitterScraper:
    """Scrapes data from a Nitter instance using Playwright and BeautifulSoup."""
    def __init__(self):
        self.base_urls = [str(url).rstrip('/') for url in settings.nitter_instances]
        self.base_url = self.base_urls[0] if self.base_urls else str(settings.nitter_base_url).rstrip('/')

    def normalize_url(self, url: str, base_url: str = None) -> str:
        """Normalize user-provided URL to a Nitter URL."""
        url = url.strip()
        match = re.search(settings.full_url_regex, url, re.IGNORECASE)
        if match:
            user, sid = match.groups()
            return f"{base_url or self.base_url}/{user}/status/{sid}"
        raise ValueError(f"Invalid URL format: {url}")

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
                if ("Tweet not found" in html_content or
                        "Instance has been rate limited" in html_content or
                        "User not found" in html_content):
                    logger.warning(f"Content from {normalized_url} indicates error: {html_content[:200]}...")
                logger.info(f"Fetched HTML ({len(html_content)} bytes) from {normalized_url}")
                self.base_url = base_url  # Update the primary base URL to the successful one
                return html_content
            except Exception as e:
                logger.error(f"Error fetching {normalized_url}: {e}")
                # Attempt to capture partial content for diagnostics
                try:
                    partial_content = await page.content()
                    if partial_content:
                        logger.debug(f"Partial content captured despite error for {normalized_url}: {partial_content[:200]}...")
                    else:
                        logger.debug(f"No partial content available for {normalized_url}")
                except Exception as partial_e:
                    logger.debug(f"Failed to capture partial content for {normalized_url}: {partial_e}")
                continue
        logger.error(f"All Nitter instances failed for {original_url}")
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
