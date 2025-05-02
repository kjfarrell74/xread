#!/usr/bin/env python3
"""Entry point for the xread application."""

import asyncio

from xread.cli import async_main

if __name__ == "__main__":
    asyncio.run(async_main())
