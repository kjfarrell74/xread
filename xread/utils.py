"""Utility functions and decorators for the xread application."""

import asyncio
import random
import yaml
from pathlib import Path
from typing import Callable, Any
import functools

import aiohttp
from google.api_core import exceptions as google_api_exceptions
from playwright.async_api import TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

from xread.settings import settings, logger

def with_retry(retries: int = None, delay: int = None):
    """Decorator to retry async functions with exponential backoff."""
    retries = retries if retries is not None else settings.retry_attempts
    delay = delay if delay is not None else settings.retry_delay

    def decorator(fn: Callable[..., Any]):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(retries):
                try:
                    if asyncio.iscoroutinefunction(fn):
                        return await fn(*args, **kwargs)
                    return await asyncio.to_thread(fn, *args, **kwargs)
                except (
                    PlaywrightTimeoutError,
                    PlaywrightError,
                    aiohttp.ClientError,
                    google_api_exceptions.GoogleAPIError,
                    google_api_exceptions.RetryError,
                    IOError,
                ) as e:
                    last_exception = e
                    is_non_retryable = isinstance(
                        e,
                        (
                            google_api_exceptions.PermissionDenied,
                            google_api_exceptions.InvalidArgument,
                            google_api_exceptions.Unauthenticated,
                        ),
                    )
                    logger.warning(
                        f"{fn.__name__} attempt {attempt+1}/{retries} failed: "
                        f"{type(e).__name__}: {e}"
                    )
                    if attempt < retries - 1 and not is_non_retryable:
                        sleep_time = delay * (2 ** attempt) + random.random()
                        logger.info(f"Retrying in {sleep_time:.2f}s...")
                        await asyncio.sleep(sleep_time)
                    else:
                        logger.error(f"{fn.__name__} failed after {retries} attempts.")
                        raise last_exception
            if last_exception:
                raise last_exception
            return None
        return wrapper
    return decorator


def load_instructions(filepath: Path = Path("instructions.yaml")) -> dict[str, Any]:
    """Load custom instructions from a YAML file if present."""
    if not filepath.exists():
        return {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            instructions = yaml.safe_load(f) or {}
        instructions.pop('report_style_guide', None)
        instructions.pop('report_format', None)
        instructions.pop('default_report_output_subdir', None)
        logger.info(f"Loaded instructions from {filepath}.")
        return instructions
    except yaml.YAMLError as e:
        logger.error(f"Error loading YAML file {filepath}: {e}")
    except IOError as e:
        logger.error(f"File reading error for {filepath}: {e}")
    return {}
