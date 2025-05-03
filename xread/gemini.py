"""Gemini API interaction functionality for image description and text analysis in xread."""

import asyncio
import hashlib
import mimetypes
import time
from pathlib import Path
from typing import Optional, List
import aiohttp
import google.generativeai as genai
from google.api_core import exceptions as google_api_exceptions
from urllib.parse import urlparse
import tempfile

from xread.settings import settings, logger
from xread.constants import MAX_IMAGE_SIZE, TimeoutConstants
from xread.models import Post
from xread.utils import with_retry

class GeminiApiError(Exception):
    """Custom exception for Gemini API errors."""
    pass

class RateLimiter:
    """Manages API rate limits to prevent throttling or bans."""
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.request_times: List[float] = []
        self._lock = asyncio.Lock()
        
    async def acquire(self) -> None:
        """Wait if necessary to comply with rate limits."""
        async with self._lock:
            now = time.time()
            # Remove timestamps older than 1 minute
            self.request_times = [t for t in self.request_times if now - t < 60]
            
            if len(self.request_times) >= self.requests_per_minute:
                oldest = min(self.request_times)
                sleep_time = max(0, 60 - (now - oldest))
                if sleep_time > 0:
                    logger.info(f"Rate limit: waiting {sleep_time:.2f}s")
                    await asyncio.sleep(sleep_time)
                    
            self.request_times.append(time.time())

class GeminiProcessor:
    """Manages Gemini API interactions for image description and text analysis."""
    def __init__(self, data_manager):
        self.image_model: Optional[genai.GenerativeModel] = None
        self.text_model: Optional[genai.GenerativeModel] = None
        self.api_key_valid = False
        self.rate_limiter = RateLimiter(requests_per_minute=60)
        if settings.gemini_api_key:
            try:
                genai.configure(api_key=settings.gemini_api_key)
                model_loaded = False
                if settings.max_image_downloads > 0 and settings.image_description_model:
                    try:
                        self.image_model = genai.GenerativeModel(settings.image_description_model)
                        logger.info(f"Initialized image model '{settings.image_description_model}'")
                        model_loaded = True
                    except Exception as e:
                        logger.error(f"Failed to load image model '{settings.image_description_model}': {e}")
                if settings.text_analysis_model:
                    try:
                        self.text_model = genai.GenerativeModel(settings.text_analysis_model)
                        logger.info(f"Initialized text model '{settings.text_analysis_model}'")
                        model_loaded = True
                    except Exception as e:
                        logger.error(f"Failed to load text model '{settings.text_analysis_model}': {e}")
                self.api_key_valid = model_loaded
                if not self.api_key_valid:
                    logger.warning("API key provided, but no Gemini models could be loaded.")
            except Exception as e:
                logger.error(f"Failed to configure Gemini SDK: {e}")
        else:
            logger.warning("GEMINI_API_KEY not found. Gemini features disabled.")
        self.max_downloads = settings.max_image_downloads
        self.downloaded_count = 0
        self.data_manager = data_manager

    async def process_images(self, item: Post, session: aiohttp.ClientSession, item_type: str = "post") -> None:
        """Process images in a post or reply to generate descriptions.
        
        Args:
            item: The Post object containing images to process.
            session: The aiohttp ClientSession for downloading images.
            item_type: String indicating if this is a 'post' or 'reply' (default: 'post').
        """
        if not self.api_key_valid or not self.image_model or settings.max_image_downloads <= 0:
            return
        if not item.images:
            return
        remaining = self.max_downloads - self.downloaded_count
        logger.info(f"Processing up to {remaining} images for {item_type} {item.status_id or 'N/A'}...")
        tasks = []
        for img in item.images:
            if self.downloaded_count >= self.max_downloads:
                break
            tasks.append(asyncio.create_task(self._process_single_image(session, img)))
        for img in item.images[len(tasks):]:
            img.description = "Skipped (limit reached)"
        if tasks:
            await asyncio.gather(*tasks)

    @with_retry()
    async def _process_single_image(self, session: aiohttp.ClientSession, image) -> None:
        """Download an image and generate its description via the Gemini API."""
        temp_file_path = None
        cache_key = hashlib.sha256(image.url.encode()).hexdigest()
        try:
            if cache_key in self.data_manager.image_cache:
                image.description = self.data_manager.image_cache[cache_key]
                logger.info(f"Used cached description for {image.url}")
                self.downloaded_count += 1
                logger.info(f"Image count: {self.downloaded_count}/{self.max_downloads}")
                return

            logger.info(f"Downloading image: {image.url}")
            async with asyncio.timeout(TimeoutConstants.IMAGE_DOWNLOAD_SECONDS):
                async with session.get(image.url) as resp:
                    resp.raise_for_status()
                    content = await resp.read()
            if not content:
                logger.warning(f"Empty download {image.url}")
                image.description = "Error: Empty download"
                return
            if len(content) > MAX_IMAGE_SIZE:
                logger.warning(f"Image {image.url} too large")
                image.description = "Error: Image too large"
                return
            temp_dir = Path(tempfile.gettempdir())
            temp_dir.mkdir(exist_ok=True)
            temp_suff = Path(urlparse(image.url).path).suffix or ".tmp"
            with tempfile.NamedTemporaryFile(delete=False, suffix=temp_suff, dir=temp_dir) as tmpf:
                tmpf.write(content)
                temp_file_path = Path(tmpf.name)
            await self.rate_limiter.acquire()
            image.description = await self._describe_image_native(temp_file_path, content)
            self.downloaded_count += 1
            logger.info(f"Described {image.url}. Image count: {self.downloaded_count}/{self.max_downloads}")
            if image.description and not image.description.startswith("Error:"):
                self.data_manager.image_cache[cache_key] = image.description
                await self.data_manager._save_cache()
        except Exception as e:
            err_msg = f"Error processing image: {e.__class__.__name__}"
            logger.warning(f"{err_msg} for {image.url}")
            image.description = image.description or err_msg
        finally:
            if temp_file_path and temp_file_path.exists():
                try:
                    temp_file_path.unlink()
                except IOError as e:
                    logger.warning(f"Failed to delete temp file {temp_file_path}: {e}")

    @with_retry()
    async def _describe_image_native(self, path: Path, image_bytes: bytes) -> str:
        """Use Gemini API to describe an image."""
        if not self.api_key_valid or not self.image_model:
            raise GeminiApiError("Image model not available.")
        try:
            if not image_bytes:
                logger.warning(f"{path} empty.")
                raise GeminiApiError("Image file empty.")
            logger.info(f"Describing {path} ({len(image_bytes)} bytes) via Gemini...")
            mime_type, _ = mimetypes.guess_type(str(path))
            mime_type = mime_type if mime_type and mime_type.startswith('image/') else "image/jpeg"
            image_part = {"mime_type": mime_type, "data": image_bytes}
            prompt_parts = ["describe the image in a concise but detailed manner", image_part]
            response = await self.image_model.generate_content_async(prompt_parts)
            if not response.candidates:
                if response.prompt_feedback and response.prompt_feedback.block_reason:
                    raise GeminiApiError(f"Blocked ({response.prompt_feedback.block_reason.name})")
                raise GeminiApiError("No candidates")
            if response.text:
                desc = response.text.strip()
                if "cannot fulfill" in desc.lower() or "unable to process" in desc.lower():
                    raise GeminiApiError("API refused.")
                return desc
            raise GeminiApiError("No text in response.")
        except google_api_exceptions.InvalidArgument as e:
            if "API key not valid" in str(e):
                self.api_key_valid = False
            raise GeminiApiError(f"Invalid Argument ({e})")
        except google_api_exceptions.PermissionDenied as e:
            self.api_key_valid = False
            raise GeminiApiError(f"Permission Denied ({e})")
        except google_api_exceptions.ResourceExhausted as e:
            raise GeminiApiError(f"Rate limit ({e})")
        except google_api_exceptions.GoogleAPIError as e:
            raise GeminiApiError(f"API Error ({e.__class__.__name__})")
        except Exception as e:
            logger.exception(f"Unexpected desc error {path}: {e}")
            raise GeminiApiError(f"Unexpected ({e.__class__.__name__})")

    async def generate_text_native(self, prompt: str, task_description: str) -> Optional[str]:
        """Generate text using the Gemini API for the given prompt."""
        if not self.api_key_valid or not self.text_model:
            reason = "API client/key invalid" if not self.api_key_valid else "Text model init failed"
            logger.error(f"Cannot perform '{task_description}': {reason}.")
            raise GeminiApiError(f"Cannot perform '{task_description}'. Reason: {reason}.")
        logger.info(f"Sending prompt to Gemini API for '{task_description}'...")
        try:
            response = await self.text_model.generate_content_async([prompt])
            if not response.candidates:
                block_reason = (
                    response.prompt_feedback.block_reason.name
                    if response.prompt_feedback and response.prompt_feedback.block_reason
                    else "Unknown"
                )
                logger.warning(f"Gemini blocked for '{task_description}'. Reason: {block_reason}.")
                raise GeminiApiError(f"Blocked by API ({block_reason}) for '{task_description}'.")
            if not response.text:
                logger.warning(f"Gemini response empty for '{task_description}'.")
                raise GeminiApiError(f"API response empty for '{task_description}'.")
            text_content = response.text.strip()
            if "cannot fulfill" in text_content.lower() or "unable to process" in text_content.lower():
                logger.warning(f"Generated content for '{task_description}' contains refusal.")
                return f"Warning: Refusal\n{text_content}"
            logger.info(f"Successfully generated content for '{task_description}'.")
            return text_content
        except google_api_exceptions.InvalidArgument as e:
            if "API key not valid" in str(e):
                self.api_key_valid = False
            logger.error(f"Invalid Argument for '{task_description}': {e}")
            raise GeminiApiError(f"Invalid Argument ({e})")
        except google_api_exceptions.PermissionDenied as e:
            self.api_key_valid = False
            logger.error(f"Permission Denied for '{task_description}': {e}")
            raise GeminiApiError(f"Permission Denied ({e})")
        except google_api_exceptions.ResourceExhausted as e:
            logger.error(f"Rate limit for '{task_description}': {e}")
            raise GeminiApiError(f"Rate limit ({e})")
        except google_api_exceptions.GoogleAPIError as e:
            logger.error(f"API Error for '{task_description}': {e}")
            raise GeminiApiError(f"API Error ({e.__class__.__name__})")
        except Exception as e:
            logger.exception(f"Unexpected error during '{task_description}': {e}")
            raise GeminiApiError(f"Unexpected ({e.__class__.__name__})")
