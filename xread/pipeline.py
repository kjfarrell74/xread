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
# No AI model factory or base classes needed as Perplexity is directly integrated.
from xread.browser import BrowserManager

class ScraperPipeline:
    """Orchestrates scraping, processing, generating search terms, and saving data."""
    def __init__(self):
        self.scraper = NitterScraper()
        self.data_manager = DataManager()
        self.browser_manager = BrowserManager()
        self._browser_ready = False

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

    async def _process_images_perplexity(self, scraped_data: ScrapedData, sid: str) -> List[Dict[str, Any]]:
        """Process images for use with Perplexity AI API."""
        api_key = os.getenv("PERPLEXITY_API_KEY")
        if not api_key:
            logger.error("Perplexity API key not found in environment variables.")
            return []
            
        # List to store base64-encoded images
        processed_images = []
        
        logger.info(f"Processing images for post {sid} to include in Perplexity prompt...")
        
        try:
            async with aiohttp.ClientSession() as session:
                # Process images from the main post
                main_post_images = await self._download_and_encode_images(scraped_data.main_post, session)
                processed_images.extend(main_post_images)
                
                # Process images from all replies for comprehensive analysis
                for reply in scraped_data.replies:
                    reply_images = await self._download_and_encode_images(reply, session)
                    processed_images.extend(reply_images)

                    # Limit total number of images to avoid making prompt too large, but increase the limit
                    if len(processed_images) >= 10:  # Increased from 4 to 10 for more comprehensive image analysis
                        logger.info(f"Reached maximum number of images for Perplexity (10). Skipping remaining images.")
                        break
            
            logger.info(f"Processed {len(processed_images)} images for Perplexity API")
        except Exception as e:
            logger.error(f"Error processing images for Perplexity: {e}")
            logger.info("Proceeding with text content only for Perplexity report generation.")
            processed_images = []
            
        return processed_images

    async def _download_and_encode_images(self, post: Post, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        """Download images and encode them for use with Perplexity API."""
        image_data_list = []

        for img in post.images:
            # Make sure we have a valid URL - sometimes Nitter URLs need modification
            image_url = img.url
            if "nitter.net/pic/" in image_url:
                # Handle Nitter URLs which may need special processing
                logger.info(f"Detected Nitter image URL: {image_url}")
                # Some Nitter instances use this format
                if "%2F" in image_url:
                    # URL decode the path
                    from urllib.parse import unquote
                    decoded_url = unquote(image_url)
                    logger.info(f"Decoded Nitter URL: {decoded_url}")
                    image_url = decoded_url

            logger.info(f"Downloading image: {image_url}")

            try:
                async with asyncio.timeout(20):  # Increase timeout for image download
                    # Try multiple ways to download the image
                    try:
                        async with session.get(image_url, allow_redirects=True) as resp:
                            if resp.status != 200:
                                logger.warning(f"Failed to download image {image_url}, status: {resp.status}, trying alternate methods...")
                                # If this fails, we'll try other methods below
                                raise aiohttp.ClientError(f"Failed with status {resp.status}")

                            content = await resp.read()
                    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                        logger.warning(f"Primary download method failed: {e}, trying alternate method...")
                        # Some Nitter images require a different approach
                        # Try a direct media URL if possible
                        if "nitter.net/pic/orig/media" in image_url:
                            # Try to extract the media path and construct a direct URL
                            import re
                            media_match = re.search(r'media%2F([^\.]+\.[^\.]+)', image_url)
                            if media_match:
                                media_id = media_match.group(1)
                                alternate_url = f"https://pbs.twimg.com/media/{media_id}"
                                logger.info(f"Trying alternate URL: {alternate_url}")

                                async with session.get(alternate_url, allow_redirects=True) as alt_resp:
                                    if alt_resp.status != 200:
                                        logger.warning(f"Alternate download failed: {alternate_url}, status: {alt_resp.status}")
                                        continue

                                    content = await alt_resp.read()
                            else:
                                logger.warning(f"Could not extract media ID from URL: {image_url}")
                                continue
                        else:
                            logger.warning(f"No alternate method available for {image_url}")
                            continue

                    # Skip if image is too large (10MB limit)
                    if len(content) > 10 * 1024 * 1024:
                        logger.warning(f"Image {image_url} too large (> 10MB), skipping")
                        continue

                    # Determine the mime type
                    mime_type, _ = mimetypes.guess_type(img.url)
                    mime_type = mime_type if mime_type and mime_type.startswith('image/') else "image/jpeg"

                    # Encode the image in base64
                    base64_encoded = base64.b64encode(content).decode('utf-8')

                    # Since we're having issues with base64 encoding, let's try to convert
                    # Nitter URLs to direct Twitter URLs that Perplexity might be able to access
                    original_url = None
                    if "nitter.net/pic/orig/media" in image_url:
                        # Extract media ID and create direct Twitter URL
                        import re
                        media_match = re.search(r'media%2F([^\.]+\.[^\.]+)', image_url) or re.search(r'media/([^\.]+\.[^\.]+)', image_url)
                        if media_match:
                            media_id = media_match.group(1)
                            # Use direct Twitter media URL
                            original_url = f"https://pbs.twimg.com/media/{media_id}"
                            logger.info(f"Converted to Twitter media URL: {original_url}")

                    # Add to list with the format we need for later conversion
                    image_data_list.append({
                        "source": {
                            "media_type": mime_type,
                            "data": base64_encoded
                        },
                        "original_url": original_url or image_url  # Store original or converted URL
                    })

                    logger.info(f"Successfully processed image {img.url}")

                    # Increased limit from 2 to 5 images per post for more comprehensive analysis
                    if len(image_data_list) >= 5:
                        break

            except Exception as e:
                logger.warning(f"Error processing image {img.url}: {e}")

        return image_data_list

    async def _generate_perplexity_report(self, scraped_data: ScrapedData, sid: str) -> Optional[str]:
        """
        Generate a factual report using Perplexity AI API based on the scraped text content and images.
        """
        api_key = os.getenv("PERPLEXITY_API_KEY")
        if not api_key:
            logger.error("Perplexity API key not found in environment variables.")
            return None

        full_text = scraped_data.get_full_text()
        if not full_text.strip():
            logger.warning(f"Post {sid} has no text content for report generation.")
            return "Info: No text content provided for analysis."
            
        # Process images to include in the prompt
        image_content = await self._process_images_perplexity(scraped_data, sid)
        # Filter out video thumbnails (e.g., Twitter Amplify) to avoid invalid media
        original_count = len(image_content)
        image_content = [img for img in image_content
                         if 'amplify_video_thumb' not in (img.get('original_url') or '')]
        if len(image_content) < original_count:
            logger.info(f"Filtered out {original_count - len(image_content)} video thumbnails for post {sid}")
        
        # Generate prompt text
        prompt_text = PERPLEXITY_REPORT_PROMPT.format(scraped_text=full_text)
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "sonar-pro",
            "messages": [],
            "max_tokens": 2000,  # Increased token limit for more detailed reports
            "temperature": 0.1  # Lower temperature for more factual, consistent output
        }

        # Prepare messages for Perplexity API
        system_message = {"role": "system", "content": "You are an expert analyst who provides comprehensive, detailed, and 100% factually accurate reports. Maintain complete objectivity and neutrality. Avoid any political, social, or ideological bias. Thoroughly describe any images in the content. Provide in-depth analysis with relevant context. Structure your response clearly with organized sections."}
        user_message = {"role": "user", "content": prompt_text}

        # First attempt: Multimodal call with images if available
        if image_content:
            logger.info(f"Attempting multimodal Perplexity API call for post {sid}")
            multimodal_content = []
            multimodal_content.append({
                "type": "text",
                "text": prompt_text
            })
            for img in image_content:
                if 'original_url' in img and img['original_url']:
                    multimodal_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": img['original_url']
                        }
                    })
                    logger.info(f"Added image with direct URL: {img['original_url']}")
                else:
                    logger.warning(f"Skipping image without original URL: {img.get('original_url', 'N/A')}")
            
            user_message["content"] = multimodal_content
            messages = [user_message]  # Only user message for multimodal call
            payload["messages"] = messages
            
            try:
                # Log the payload for debugging (only the structure, not the actual image data)
                debug_payload = payload.copy()
                debug_payload["messages"] = [debug_payload["messages"][0].copy()]
                if isinstance(debug_payload["messages"][0]["content"], list):
                    for i, item in enumerate(debug_payload["messages"][0]["content"]):
                        if item.get("type") == "image_url" and "image_url" in item:
                            url = item["image_url"]["url"]
                            if url.startswith("data:"):
                                # Truncate the base64 data for logging
                                parts = url.split(",")
                                if len(parts) > 1:
                                    debug_payload["messages"][0]["content"][i]["image_url"]["url"] = f"{parts[0]},<base64_data_truncated>"

                logger.info(f"Sending multimodal request to Perplexity API for post {sid} with payload structure: {debug_payload}")

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://api.perplexity.ai/chat/completions",
                        headers=headers,
                        json=payload
                    ) as response:
                        if response.status != 200:
                            logger.error(f"Multimodal Perplexity API call returned status code {response.status} for post {sid}")
                            # Log the error response
                            error_body = await response.text()
                            logger.error(f"Error response: {error_body}")
                            raise Exception(f"Multimodal API call failed with status {response.status}. Details: {error_body}")
                        data = await response.json()
                        logger.info(f"Multimodal Perplexity API request successful for post {sid}")
                        return data["choices"][0]["message"]["content"]
            except Exception as e:
                logger.exception(f"Error in multimodal Perplexity API call for post {sid}: {e}")
                logger.info(f"Falling back to text-only Perplexity API call for post {sid}")

        # Fallback: Text-only call if no images or if multimodal call failed
        logger.info(f"Attempting text-only Perplexity API call for post {sid}")
        messages = [system_message, user_message] # System message + user message for text-only call
        payload["messages"] = messages

        try:
            logger.info(f"Sending text-only request to Perplexity API for post {sid}")
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status != 200:
                        logger.error(f"Text-only Perplexity API call returned status code {response.status} for post {sid}")
                        error_body = await response.text()
                        logger.error(f"Error response: {error_body}")
                        return f"Error: Text-only Perplexity API call failed with status {response.status}. Details: {error_body}"
                    data = await response.json()
                    logger.info(f"Text-only Perplexity API request successful for post {sid}")
                    return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.exception(f"Error in text-only Perplexity API call for post {sid}: {e}")
            import traceback
            error_traceback = traceback.format_exc()
            logger.error(f"Traceback: {error_traceback}")
            return f"Error: Failed to generate Perplexity report (both multimodal and text-only attempts failed). Exception: {e}. Check logs for details."

    async def _save_results(
        self,
        scraped_data: ScrapedData,
        url: str,
        perplexity_report: Optional[str],
        sid: str,
        author_profile: Optional['UserProfile'] = None,
        url_sid: Optional[str] = None
    ) -> None:
        """Save the scraped data along with the generated Perplexity report and author profile."""
        # If the URL status ID is available and different from the main post ID,
        # use it to override the main post's status ID for saving
        if url_sid and url_sid != sid:
            logger.info(f"Using URL status ID {url_sid} for saving instead of main post ID {sid}")
            # Clone the main post and update its status_id
            import copy
            modified_data = copy.deepcopy(scraped_data)
            modified_data.main_post.status_id = url_sid
            saved_sid = await self.data_manager.save(modified_data, url, perplexity_report, author_profile)
        else:
            saved_sid = await self.data_manager.save(scraped_data, url, perplexity_report, author_profile)

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
                
            # Generate Perplexity report with text and images
            perplexity_report = await self._generate_perplexity_report(scraped_data, sid)
            if perplexity_report:
                logger.info(f"Generated Perplexity report for post {sid}")
            else:
                logger.warning(f"Failed to generate Perplexity report for post {sid}")
                perplexity_report = "Error: Failed to generate Perplexity report."

            # Look up author profile
            author_username = scraped_data.main_post.username
            author_profile = await self.data_manager.get_user_profile(author_username)
            if author_profile:
                logger.info(f"Found user profile for {author_username} in database.")
            else:
                logger.info(f"No user profile found for {author_username} in database.")

            await self._save_results(scraped_data, url, perplexity_report, sid, author_profile, url_sid)
        except ValueError as e:
            logger.error(f"URL/Input error: {e}")
            typer.echo(f"Error: {e}", err=True)
        except Exception as e:
            logger.exception(f"Unexpected pipeline error for {url}: {e}")
            typer.echo(f"Error: An unexpected error occurred: {e}", err=True)
            if html_content and scraped_data is None:
                await self._save_failed_html(sid, html_content)
