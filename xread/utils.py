"""Utility functions and decorators for the xread application."""

from __future__ import annotations # For forward references if needed, and cleaner syntax

import asyncio
import random
from pathlib import Path
from typing import Callable, Any, Coroutine, Optional, TypeVar, ParamSpec, List as TypingList, Awaitable
import functools

import aiohttp
from playwright.async_api import TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

import os
import subprocess

from xread.settings import settings, logger

# Define TypeVar and ParamSpec for generic decorator
R = TypeVar('R')
P = ParamSpec('P')

def with_retry(retries: Optional[int] = None, delay: Optional[int] = None) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorator to retry async functions with exponential backoff."""
    actual_retries: int = retries if retries is not None else settings.retry_attempts
    actual_delay: int = delay if delay is not None else settings.retry_delay

    def decorator(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_exception: Optional[Exception] = None
            for attempt in range(actual_retries):
                try:
                    # The decorator is designed for async functions, so direct await is appropriate
                    return await fn(*args, **kwargs)
                except (
                    PlaywrightTimeoutError, # Specific Playwright Timeout
                    PlaywrightError,      # General Playwright Error
                    aiohttp.ClientError,
                    IOError,
                ) as e:
                    last_exception = e
                    logger.warning(
                        f"{fn.__name__} attempt {attempt+1}/{retries} failed: "
                        f"{type(e).__name__}: {e}"
                    )
                    if attempt < retries - 1:
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

def play_ding():
    """
    Play the notification sound (ding.mp3) using an available audio player.
    Tries mpg123, mpv, cvlc, or afplay.
    """
    ding_path = os.path.join(os.path.dirname(__file__), "..", "ding.mp3")
    ding_path = os.path.abspath(ding_path)
    if not os.path.isfile(ding_path):
        logger.info("ding.mp3 not found, skipping notification sound.")
        return
    players = [
        ["mpg123", "-q", ding_path],
        ["mpv", "--no-terminal", "--quiet", ding_path],
        ["cvlc", "--play-and-exit", "--quiet", ding_path],
        ["afplay", ding_path],  # macOS
    ]
    for player in players:
        try:
            subprocess.run([player[0], "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.Popen(player)
            logger.info(f"Played notification sound using {player[0]}")
            break
        except Exception:
            continue
