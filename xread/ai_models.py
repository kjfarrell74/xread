"""Unified AI model interfaces for xread.

This module provides abstractions for integrating various AI providers.
It defines a base class for AI models and specific implementations like PerplexityModel
to support generating reports and analyses from scraped data.
"""

import os
import asyncio
import base64
import hashlib
import mimetypes
from typing import Optional, List, Dict, Any
from abc import ABC, abstractmethod
from datetime import timedelta

import aiohttp

from xread.settings import settings, logger
from xread.constants import PERPLEXITY_REPORT_PROMPT, GEMINI_REPORT_PROMPT
from xread.models import ScrapedData, Post


class BaseAIModel(ABC):
    """Abstract base class for AI model integrations."""
    
    @abstractmethod
    async def generate_report(self, scraped_data: ScrapedData, sid: str) -> Optional[str]:
        """Generate a report based on scraped data.
        
        Args:
            scraped_data (ScrapedData): The scraped data to analyze.
            sid (str): The status ID of the post for logging purposes.
            
        Returns:
            Optional[str]: The generated report or None if generation fails.
        """
        pass


class PerplexityModel(BaseAIModel):
    """Implementation of the Perplexity AI model for report generation."""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize the Perplexity model with an API key.
        
        Args:
            api_key (Optional[str]): The API key for Perplexity AI. If not provided, it will be fetched from environment variables.
        """
        self.api_key = api_key or os.getenv("PERPLEXITY_API_KEY") or settings.perplexity_api_key
        if not self.api_key:
            logger.error("Perplexity API key not found in environment variables or initialization.")
            raise ValueError("Perplexity API key is required.")
    
    async def generate_report(self, scraped_data: ScrapedData, sid: str) -> Optional[str]:
        """Generate a factual report using Perplexity AI API based on the scraped text content and images, with robust error handling and retry logic."""
        from xread.core.utils import with_retry
        import aiohttp

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
            "Authorization": f"Bearer {self.api_key}",
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
            try:
                async def multimodal_call():
                    return await self._generate_multimodal_report(
                        prompt_text, image_content, user_message, payload, headers, sid
                    )
                multimodal_result = await with_retry(retries=2, delay=2)(multimodal_call)()
                if multimodal_result is not None:
                    return multimodal_result
            except (aiohttp.ClientError, asyncio.TimeoutError) as net_exc:
                logger.error(f"Network error in multimodal Perplexity API call for post {sid}: {net_exc}")
            except Exception as e:
                logger.error(f"Unhandled error in multimodal Perplexity API call for post {sid}: {e}")

        # Fallback: Text-only call if no images or if multimodal call failed
        logger.info(f"Attempting text-only Perplexity API call for post {sid}")
        messages = [system_message, user_message]  # System message + user message for text-only call
        payload["messages"] = messages

        try:
            async def text_only_call():
                return await self._generate_text_only_report(headers, payload, sid)
            return await with_retry(retries=2, delay=2)(text_only_call)()
        except (aiohttp.ClientError, asyncio.TimeoutError) as net_exc:
            logger.error(f"Network error in text-only Perplexity API call for post {sid}: {net_exc}")
            return f"Error: Network error in text-only Perplexity API call: {net_exc}"
        except Exception as e:
            return await self._handle_perplexity_error(e, sid)
    
    async def _generate_multimodal_report(
        self,
        prompt_text: str,
        image_content: list,
        user_message: dict,
        payload: dict,
        headers: dict,
        sid: str
    ) -> Optional[str]:
        """
        Handle the multimodal Perplexity API call logic as a separate method.
        Returns the report string if successful, or None if fallback is needed.
        """
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
            return None

    async def _handle_perplexity_error(self, e: Exception, sid: str) -> Optional[str]:
        logger.exception(f"Error in Perplexity API call for post {sid}: {e}")
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Traceback: {error_traceback}")
        return f"Error: Failed to generate Perplexity report. Exception: {e}. Check logs for details."

    async def _generate_text_only_report(self, headers: Dict, payload: Dict, sid: str) -> Optional[str]:
        logger.info(f"Sending text-only request to Perplexity API for post {sid}")
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.perplexity.ai/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                if response.status != 200:
                    error_body = await response.text()
                    logger.error(f"Text-only API call failed: {error_body}")
                    return f"Error: Text-only API call failed with status {response.status}"
                data = await response.json()
                return data["choices"][0]["message"]["content"]

    async def _process_images_perplexity(self, scraped_data: ScrapedData, sid: str) -> List[Dict[str, Any]]:
        """Process images for use with Perplexity AI API.
        
        Args:
            scraped_data (ScrapedData): The scraped data containing images.
            sid (str): The status ID of the post for logging purposes.
            
        Returns:
            List[Dict[str, Any]]: List of processed image data dictionaries.
        """
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
        """Download images and encode them for use with Perplexity API.
        
        Args:
            post (Post): The post containing images to process.
            session (aiohttp.ClientSession): The HTTP session for downloading images.
            
        Returns:
            List[Dict[str, Any]]: List of dictionaries containing encoded image data.
        """
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

class CachedPerplexityModel(PerplexityModel):
    def __init__(self, cache, api_key: Optional[str] = None):
        super().__init__(api_key)
        self.cache = cache
    
    async def generate_report(self, scraped_data: ScrapedData, sid: str) -> Optional[str]:
        # Create cache key from text content hash
        content_hash = hashlib.md5(scraped_data.get_full_text().encode()).hexdigest()
        cache_key = self.cache.cache_key("perplexity_report", content_hash)
        
        # Try cache first
        cached_report = await self.cache.get(cache_key)
        if cached_report:
            logger.info(f"Using cached report for post {sid}")
            return cached_report
        
        # Generate new report
        report = await super().generate_report(scraped_data, sid)
        if report:
            # Cache for 24 hours
            await self.cache.set(cache_key, report, ttl=timedelta(hours=24))
        
        return report

    async def _process_images_perplexity(self, scraped_data: ScrapedData, sid: str) -> List[Dict[str, Any]]:
        """Process images for use with Perplexity AI API.
        
        Args:
            scraped_data (ScrapedData): The scraped data containing images.
            sid (str): The status ID of the post for logging purposes.
            
        Returns:
            List[Dict[str, Any]]: List of processed image data dictionaries.
        """
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
        """Download images and encode them for use with Perplexity API.
        
        Args:
            post (Post): The post containing images to process.
            session (aiohttp.ClientSession): The HTTP session for downloading images.
            
        Returns:
            List[Dict[str, Any]]: List of dictionaries containing encoded image data.
        """
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


class GeminiModel(BaseAIModel):
    """Implementation of the Gemini AI model for report generation with search capabilities."""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize the Gemini model with an API key.
        
        Args:
            api_key (Optional[str]): The API key for Gemini AI. If not provided, it will be fetched from environment variables.
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or settings.gemini_api_key
        if not self.api_key:
            logger.error("Gemini API key not found in environment variables or initialization.")
            raise ValueError("Gemini API key is required.")
    
    async def generate_report(self, scraped_data: ScrapedData, sid: str) -> Optional[str]:
        """Generate a factual report using Gemini AI API based on the scraped text content and images.
        
        Args:
            scraped_data (ScrapedData): The scraped data containing text and images.
            sid (str): The status ID of the post for logging purposes.
            
        Returns:
            Optional[str]: The generated report or an error message if generation fails.
        """
        full_text = scraped_data.get_full_text()
        if not full_text.strip():
            logger.warning(f"Post {sid} has no text content for report generation.")
            return "Info: No text content provided for analysis."
            
        # Process images to include in the prompt if supported by Gemini API
        image_content = await self._process_images_gemini(scraped_data, sid)
        
        # Generate prompt text using the Gemini-specific prompt structure
        prompt_text = GEMINI_REPORT_PROMPT.format(scraped_text=full_text)
        
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json"
        }

        payload = {
            "contents": [],
            "generationConfig": {
                "maxOutputTokens": 2000,
                "temperature": 0.1
            }
        }

        # Prepare contents for Gemini API
        system_content = {
            "role": "model",  # Gemini often uses 'model' for system-like instructions
            "parts": [
                {
                    "text": "You are an expert analyst who provides comprehensive, detailed, and 100% factually accurate reports. Maintain complete objectivity and neutrality. Avoid any political, social, or ideological bias. Thoroughly describe any images in the content. Provide in-depth analysis with relevant context. Structure your response clearly with organized sections."
                }
            ]
        }
        user_content = {
            "role": "user",
            "parts": []
        }

        # Check if images are available and supported by Gemini API
        if image_content:
            logger.info(f"Attempting multimodal Gemini API call for post {sid}")
            user_content["parts"].append({
                "text": prompt_text
            })
            for img in image_content:
                if 'source' in img and 'media_type' in img['source'] and 'data' in img['source']:
                    user_content["parts"].append({
                        "inlineData": {
                            "mimeType": img['source']['media_type'],
                            "data": img['source']['data']
                        }
                    })
                    logger.info(f"Added inline image data for Gemini API")
                else:
                    logger.warning(f"Skipping image without proper source data")
            
            payload["contents"] = [user_content] if not system_content else [system_content, user_content]
            
            try:
                logger.info(f"Sending multimodal request to Gemini API for post {sid}")
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",  # Updated endpoint for Gemini API with a specific model
                        headers=headers,
                        json=payload
                    ) as response:
                        if response.status != 200:
                            logger.error(f"Multimodal Gemini API call returned status code {response.status} for post {sid}")
                            error_body = await response.text()
                            logger.error(f"Error response: {error_body}")
                            raise Exception(f"Multimodal API call failed with status {response.status}. Details: {error_body}")
                        data = await response.json()
                        logger.info(f"Multimodal Gemini API request successful for post {sid}")
                        return data["candidates"][0]["content"]["parts"][0]["text"]
            except Exception as e:
                logger.exception(f"Error in multimodal Gemini API call for post {sid}: {e}")
                logger.info(f"Falling back to text-only Gemini API call for post {sid}")

        # Fallback: Text-only call if no images or if multimodal call failed
        logger.info(f"Attempting text-only Gemini API call for post {sid}")
        user_content["parts"] = [{"text": prompt_text}]
        payload["contents"] = [user_content] if not system_content else [system_content, user_content]

        try:
            logger.info(f"Sending text-only request to Gemini API for post {sid}")
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",  # Updated endpoint for Gemini API with a specific model
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status != 200:
                        logger.error(f"Text-only Gemini API call returned status code {response.status} for post {sid}")
                        error_body = await response.text()
                        logger.error(f"Error response: {error_body}")
                        return f"Error: Text-only Gemini API call failed with status {response.status}. Details: {error_body}"
                    data = await response.json()
                    logger.info(f"Text-only Gemini API request successful for post {sid}")
                    return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            logger.exception(f"Error in text-only Gemini API call for post {sid}: {e}")
            import traceback
            error_traceback = traceback.format_exc()
            logger.error(f"Traceback: {error_traceback}")
            return f"Error: Failed to generate Gemini report (both multimodal and text-only attempts failed). Exception: {e}. Check logs for details."

    async def _process_images_gemini(self, scraped_data: ScrapedData, sid: str) -> List[Dict[str, Any]]:
        """Process images for use with Gemini AI API.
        
        Args:
            scraped_data (ScrapedData): The scraped data containing images.
            sid (str): The status ID of the post for logging purposes.
            
        Returns:
            List[Dict[str, Any]]: List of processed image data dictionaries.
        """
        # Reuse the Perplexity image processing logic as a placeholder
        # This may need adjustment based on Gemini API requirements for image handling
        processed_images = []
        
        logger.info(f"Processing images for post {sid} to include in Gemini prompt...")
        
        try:
            async with aiohttp.ClientSession() as session:
                main_post_images = await self._download_and_encode_images_gemini(scraped_data.main_post, session)
                processed_images.extend(main_post_images)
                
                for reply in scraped_data.replies:
                    reply_images = await self._download_and_encode_images_gemini(reply, session)
                    processed_images.extend(reply_images)
                    if len(processed_images) >= 10:
                        logger.info(f"Reached maximum number of images for Gemini (10). Skipping remaining images.")
                        break
            
            logger.info(f"Processed {len(processed_images)} images for Gemini API")
        except Exception as e:
            logger.error(f"Error processing images for Gemini: {e}")
            logger.info("Proceeding with text content only for Gemini report generation.")
            processed_images = []
            
        return processed_images

    async def _download_and_encode_images_gemini(self, post: Post, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        """Download images and encode them for use with Gemini API.
        
        Args:
            post (Post): The post containing images to process.
            session (aiohttp.ClientSession): The HTTP session for downloading images.
            
        Returns:
            List[Dict[str, Any]]: List of dictionaries containing encoded image data.
        """
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
                    # Nitter URLs to direct Twitter URLs that Gemini might be able to access
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


class OpenAIModel(BaseAIModel):
    """Implementation of OpenAI GPT model for report generation."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or settings.openai_api_key
        if not self.api_key:
            logger.error("OpenAI API key not found in environment variables or initialization.")
            raise ValueError("OpenAI API key is required.")
        import openai
        openai.api_key = self.api_key

    async def generate_report(self, scraped_data: ScrapedData, sid: str) -> Optional[str]:
        import openai
        full_text = scraped_data.get_full_text()
        if not full_text.strip():
            logger.warning(f"Post {sid} has no text content for report generation.")
            return "Info: No text content provided for analysis."

        prompt_text = PERPLEXITY_REPORT_PROMPT.format(scraped_text=full_text)
        try:
            response = await openai.ChatCompletion.acreate(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an expert analyst."},
                    {"role": "user", "content": prompt_text},
                ],
                max_tokens=settings.report_max_tokens,
                temperature=settings.report_temperature,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI API error for post {sid}: {e}")
            return f"Error: Failed to generate OpenAI report. Exception: {e}"


class AnthropicModel(BaseAIModel):
    """Implementation of Anthropic Claude model for report generation."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY") or settings.anthropic_api_key
        if not self.api_key:
            logger.error("Anthropic API key not found in environment variables or initialization.")
            raise ValueError("Anthropic API key is required.")
        import anthropic
        self.client = anthropic.AsyncAnthropic(api_key=self.api_key)

    async def generate_report(self, scraped_data: ScrapedData, sid: str) -> Optional[str]:
        import anthropic
        full_text = scraped_data.get_full_text()
        if not full_text.strip():
            logger.warning(f"Post {sid} has no text content for report generation.")
            return "Info: No text content provided for analysis."

        prompt_text = PERPLEXITY_REPORT_PROMPT.format(scraped_text=full_text)
        try:
            response = await self.client.messages.create(
                model="claude-3-sonnet-20240229",
                max_tokens=settings.report_max_tokens,
                temperature=settings.report_temperature,
                messages=[{"role": "user", "content": prompt_text}],
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Anthropic API error for post {sid}: {e}")
            return f"Error: Failed to generate Anthropic report. Exception: {e}"


class DeepSeekModel(BaseAIModel):
    """Implementation of DeepSeek model for report generation."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY") or settings.deepseek_api_key
        if not self.api_key:
            logger.error("DeepSeek API key not found in environment variables or initialization.")
            raise ValueError("DeepSeek API key is required.")

    async def generate_report(self, scraped_data: ScrapedData, sid: str) -> Optional[str]:
        full_text = scraped_data.get_full_text()
        if not full_text.strip():
            logger.warning(f"Post {sid} has no text content for report generation.")
            return "Info: No text content provided for analysis."

        prompt_text = PERPLEXITY_REPORT_PROMPT.format(scraped_text=full_text)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt_text}],
            "max_tokens": settings.report_max_tokens,
            "temperature": settings.report_temperature,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.deepseek.com/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status != 200:
                        error_body = await response.text()
                        logger.error(f"DeepSeek API call failed: {error_body}")
                        return f"Error: DeepSeek API call failed with status {response.status}"
                    data = await response.json()
                    return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"DeepSeek API error for post {sid}: {e}")
            return f"Error: Failed to generate DeepSeek report. Exception: {e}"
