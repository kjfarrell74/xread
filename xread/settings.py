"""Application settings and configuration initialization for xread."""

import os
import sys
import configparser
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field, ValidationError, HttpUrl
from typing import List, Optional
import logging
from dotenv import load_dotenv
import typer

from xread.constants import DEFAULT_DATA_DIR, DEFAULT_NITTER_BASE_URL, DEFAULT_MAX_IMAGE_DOWNLOADS, DEFAULT_RETRY_ATTEMPTS, DEFAULT_RETRY_DELAY, FileFormats

# Configure logging first
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# Load configuration from config.ini if it exists
config = configparser.ConfigParser()
config_file = Path("config.ini")
if config_file.exists():
    config.read(config_file)
    logger.info(f"Loaded configuration from {config_file}")
else:
    logger.warning(f"Configuration file {config_file} not found, using defaults and environment variables")

class Settings(BaseSettings):
    """Application settings loaded from config.ini, environment variables, or defaults."""
    data_dir: Path = Field(Path(os.getenv("DATA_DIR", config.get("General", "data_dir", fallback=DEFAULT_DATA_DIR))), pre=True)
    nitter_base_url: HttpUrl = Field(
        os.getenv("NITTER_BASE_URL", config.get("Scraper", "nitter_instance", fallback=DEFAULT_NITTER_BASE_URL))
    )
    nitter_instances: List[HttpUrl] = Field(
        default_factory=lambda: [
            url.strip() for url in os.getenv(
                "NITTER_INSTANCES",
                config.get("Scraper", "nitter_instances", fallback="https://nitter.net,https://nitter.42l.fr,https://nitter.pussthecat.org,https://nitter.moomoo.me")
            ).split(",")
        ]
    )
    max_image_downloads: int = Field(
        int(os.getenv("MAX_IMAGE_DOWNLOADS_PER_RUN", config.getint("Pipeline", "max_images_per_post", fallback=DEFAULT_MAX_IMAGE_DOWNLOADS))),
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
    retry_attempts: int = Field(int(os.getenv("RETRY_ATTEMPTS", config.getint("Scraper", "retry_attempts", fallback=DEFAULT_RETRY_ATTEMPTS))), ge=1)
    retry_delay: int = Field(int(os.getenv("RETRY_DELAY", config.getint("Scraper", "retry_delay", fallback=DEFAULT_RETRY_DELAY))), ge=0)
    image_ignore_keywords: List[str] = Field(
        ['profile_images', 'avatar', 'user_media']
    )
    save_failed_html: bool = Field(bool(os.getenv("SAVE_FAILED_HTML", config.getboolean("Pipeline", "save_failed_html", fallback=True))))
    ai_model: str = Field(os.getenv("AI_MODEL", config.get("General", "ai_model", fallback="perplexity")))
    report_max_tokens: int = Field(int(os.getenv("REPORT_MAX_TOKENS", config.getint("Pipeline", "report_max_tokens", fallback=2000))), ge=100)
    report_temperature: float = Field(float(os.getenv("REPORT_TEMPERATURE", config.getfloat("Pipeline", "report_temperature", fallback=0.1))), ge=0.0, le=1.0)
    fetch_timeout: int = Field(int(os.getenv("FETCH_TIMEOUT", config.getint("Scraper", "fetch_timeout", fallback=30))), ge=5)
    
    # API Keys
    perplexity_api_key: Optional[str] = Field(os.getenv("PERPLEXITY_API_KEY", config.get("API Keys", "perplexity_api_key", fallback=None)))
    gemini_api_key: Optional[str] = Field(os.getenv("GEMINI_API_KEY", config.get("API Keys", "gemini_api_key", fallback=None)))
    openai_api_key: Optional[str] = Field(os.getenv("OPENAI_API_KEY", config.get("API Keys", "openai_api_key", fallback=None)))
    anthropic_api_key: Optional[str] = Field(os.getenv("ANTHROPIC_API_KEY", config.get("API Keys", "anthropic_api_key", fallback=None)))
    deepseek_api_key: Optional[str] = Field(os.getenv("DEEPSEEK_API_KEY", config.get("API Keys", "deepseek_api_key", fallback=None)))

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
    # Log the selected AI model
    logger.info(f"Selected AI model: {settings.ai_model}")
except ValidationError as e:
    logger.error(f"Configuration error: {e}")
    typer.echo(f"Configuration error: {e}", err=True)
    typer.echo("Check environment variables, config.ini, or .env file.", err=True)
    sys.exit(1)
