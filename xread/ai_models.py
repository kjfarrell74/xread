"""Unified AI model interfaces and factory for xread.

This module introduces a strategy-pattern abstraction so xread can work with
multiple AI providers (e.g. Google Gemini, Anthropic Claude) through a common
interface. Only the subset of functionality required by the existing pipeline
is implemented (image description and text generation).
"""

from __future__ import annotations

import base64
import mimetypes
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from xread.settings import settings, logger
from xread.data_manager import DataManager
from xread.models import Post
from xread.utils import with_retry

# ----------------------------------------------------------------------------
# Generic interface / exceptions
# ----------------------------------------------------------------------------


class AIModelError(Exception):
    """Raised when an AI model adapter encounters an unrecoverable error."""


class BaseAIModel(ABC):
    """Abstract interface every AI model adapter must implement."""

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialise the model and return *True* on success."""

    @abstractmethod
    async def is_valid(self) -> bool:
        """Return *True* if the model is ready for use (API key valid etc.)."""

    # --- operations used by `ScraperPipeline` ---
    @abstractmethod
    async def process_images(
        self,
        item: Post,
        session: aiohttp.ClientSession,
        item_type: str = "post",
    ) -> None:
        """Generate image descriptions in *item* (in-place)."""

    @abstractmethod
    async def generate_text_native(
        self, prompt: str, task_description: str
    ) -> Optional[str]:
        """Generate text for *prompt* (search terms / research questions)."""

    # The pipeline currently relies on these *optional* attributes.  Adapters
    # should expose them for compatibility but they are not required for
    # functionality when alternative models are used.

    downloaded_count: int = 0  # number of images processed this run


# ----------------------------------------------------------------------------
# Gemini wrapper – uses existing `GeminiProcessor`
# ----------------------------------------------------------------------------


from xread.gemini import GeminiProcessor, GeminiApiError  # noqa: E402  (late import)


class GeminiModel(BaseAIModel):
    """Thin wrapper that delegates calls to the existing *GeminiProcessor*."""

    def __init__(self, data_manager: DataManager, cfg: Dict[str, Any]):
        self._processor: Optional[GeminiProcessor] = None
        self._data_manager = data_manager
        self.cfg = cfg

    # ---------------- BaseAIModel interface ---------------- #

    async def initialize(self) -> bool:
        # `GeminiProcessor` performs its own SDK configuration in __init__.
        self._processor = GeminiProcessor(self._data_manager)
        return self._processor.api_key_valid

    async def is_valid(self) -> bool:
        return bool(self._processor and self._processor.api_key_valid)

    async def process_images(
        self, item: Post, session: aiohttp.ClientSession, item_type: str = "post"
    ) -> None:
        if not await self.is_valid():
            return
        await self._processor.process_images(item, session, item_type)

    async def generate_text_native(
        self, prompt: str, task_description: str
    ) -> Optional[str]:
        if not await self.is_valid():
            return None
        try:
            return await self._processor.generate_text_native(prompt, task_description)
        except GeminiApiError as e:
            logger.warning(f"Gemini error ({task_description}): {e}")
            return f"Error: {e}"

    # ---------------- compatibility passthroughs ---------------- #

    @property
    def downloaded_count(self) -> int:  # type: ignore[override]
        return self._processor.downloaded_count if self._processor else 0

    @downloaded_count.setter
    def downloaded_count(self, value: int) -> None:  # type: ignore[override]
        if self._processor:
            self._processor.downloaded_count = value

    # Expose internal models for code that checks them (optional)
    @property
    def image_model(self):  # noqa: D401: we just mimic attribute
        return self._processor.image_model if self._processor else None

    @property
    def text_model(self):
        return self._processor.text_model if self._processor else None


# ----------------------------------------------------------------------------
# Claude adapter – via *anthropic* SDK
# ----------------------------------------------------------------------------


try:
    from anthropic import AsyncAnthropic
except ImportError:  # The dependency is optional until user installs it.
    AsyncAnthropic = None  # type: ignore


class ClaudeProcessor(BaseAIModel):
    """Anthropic Claude integration (image + text)."""

    def __init__(self, data_manager: DataManager, cfg: Dict[str, Any]):
        if AsyncAnthropic is None:
            raise AIModelError(
                "anthropic package not installed – run `pip install anthropic`."
            )
        self._client = AsyncAnthropic(api_key=cfg.get("api_key"))
        self.model_name = cfg.get("model", "claude-3-5-sonnet")
        self.max_downloads = cfg.get("max_image_downloads", 5)
        self.downloaded_count = 0
        self._data_manager = data_manager
        self.api_key_valid = False

    # ---------------- BaseAIModel interface ---------------- #

    async def initialize(self) -> bool:
        try:
            # sanity ping to check key
            await self._client.messages.create(
                model=self.model_name,
                max_tokens=5,
                messages=[{"role": "user", "content": "ping"}],
            )
            self.api_key_valid = True
        except Exception as e:
            logger.error(f"Claude init failed: {e}")
            self.api_key_valid = False
        return self.api_key_valid

    async def is_valid(self) -> bool:
        return self.api_key_valid

    # ---- helpers --------------------------------------------------------- #

    @with_retry()
    async def _describe_image(self, content: bytes, image_path: Path) -> str:
        mime_type, _ = mimetypes.guess_type(str(image_path))
        mime_type = mime_type if mime_type and mime_type.startswith("image/") else "image/jpeg"
        image_b64 = base64.b64encode(content).decode()
        resp = await self._client.messages.create(
            model=self.model_name,
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this image objectively."},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": image_b64,
                            },
                        },
                    ],
                }
            ],
        )
        if resp.content:
            return resp.content[0].text.strip()
        raise AIModelError("Claude response empty")

    # ---- operations ------------------------------------------------------ #

    async def process_images(
        self, item: Post, session: aiohttp.ClientSession, item_type: str = "post"
    ) -> None:
        if not await self.is_valid() or not item.images:
            return
        for img in item.images:
            if self.downloaded_count >= self.max_downloads:
                img.description = "Skipped (limit reached)"
                continue
            try:
                async with session.get(img.url) as resp:
                    resp.raise_for_status()
                    content = await resp.read()
                img.description = await self._describe_image(content, Path(img.url))
                self.downloaded_count += 1
            except Exception as e:
                logger.warning(f"Claude image error for {img.url}: {e}")
                img.description = f"Error: {e}"

    async def generate_text_native(
        self, prompt: str, task_description: str
    ) -> Optional[str]:
        if not await self.is_valid():
            return None
        try:
            resp = await self._client.messages.create(
                model=self.model_name,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )
            if resp.content:
                return resp.content[0].text.strip()
            return "Error: empty Claude response"
        except Exception as e:
            logger.error(f"Claude text generation failed ({task_description}): {e}")
            return f"Error: {e}"


# ----------------------------------------------------------------------------
# Factory helper
# ----------------------------------------------------------------------------


class AIModelFactory:
    """Create and initialise AI model adapters by name."""

    _REGISTRY = {
        "gemini": GeminiModel,
        "claude": ClaudeProcessor,
    }

    @classmethod
    async def create(
        cls, model_type: str, data_manager: DataManager, cfg: Dict[str, Any]
    ) -> BaseAIModel:
        key = model_type.lower()
        model_cls = cls._REGISTRY.get(key)
        if not model_cls:
            supported = ", ".join(cls._REGISTRY)
            raise ValueError(f"Unsupported model '{model_type}'. Supported: {supported}")
        model = model_cls(data_manager, cfg)
        if not await model.initialize():
            raise AIModelError(f"Failed to initialise {model_type} model")
        return model

    @classmethod
    def supported(cls) -> List[str]:
        return list(cls._REGISTRY) 