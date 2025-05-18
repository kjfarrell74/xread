"""Application settings and configuration initialization for xread."""

import os
import sys
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field, ValidationError, HttpUrl
from typing import List
import logging
from dotenv import load_dotenv
import typer

from xread.constants import DEFAULT_DATA_DIR, DEFAULT_NITTER_BASE_URL, DEFAULT_MAX_IMAGE_DOWNLOADS, DEFAULT_RETRY_ATTEMPTS, DEFAULT_RETRY_DELAY, FileFormats

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""
    data_dir: Path = Field(Path(os.getenv("DATA_DIR", DEFAULT_DATA_DIR)), pre=True)
    nitter_base_url: HttpUrl = Field(
        os.getenv("NITTER_BASE_URL", DEFAULT_NITTER_BASE_URL)
    )
    max_image_downloads: int = Field(
        int(os.getenv("MAX_IMAGE_DOWNLOADS_PER_RUN", DEFAULT_MAX_IMAGE_DOWNLOADS)),
        ge=0,
    )
    status_id_regex: str = r"status/(\d+)"
    full_url_regex: str = (
        r"(?:https?://)?(?:www\.)?(?:twitter\.com|x\.com|nitter\.(?:net|[a-z0-9-]+))/"
        r"([^/]+)/status/(\d+)"
    )
    tweet_selectors: List[str] = Field(
        default_factory=lambda: [
            ".main-thread .timeline-item",
            ".conversation .tweet-body",
            ".tweet-body",
            ".timeline-item",
        ]
    )
    retry_attempts: int = Field(DEFAULT_RETRY_ATTEMPTS, ge=1)
    retry_delay: int = Field(DEFAULT_RETRY_DELAY, ge=0)
    image_ignore_keywords: List[str] = Field(
        ['profile_images', 'avatar', 'user_media']
    )
    save_failed_html: bool = Field(bool(os.getenv("SAVE_FAILED_HTML", True)))

    # No AI model-specific settings are needed as Perplexity is directly integrated.

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'
        extra = 'ignore'
        populate_by_name = True

# Initialize settings with error handling
try:
    settings = Settings()
    # Create debug directory if needed
    if settings.save_failed_html:
        Path(FileFormats.DEBUG_DIR).mkdir(parents=True, exist_ok=True)
    # No AI model type checking needed as Perplexity is directly used.
except ValidationError as e:
    logger.error(f"Configuration error: {e}")
    typer.echo(f"Configuration error: {e}", err=True)
    typer.echo("Check environment variables or .env file.", err=True)
    sys.exit(1)
