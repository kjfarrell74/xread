"""Command-line interface and interactive mode for xread."""

import asyncio
import sys
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import typer
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory

from xread.settings import settings, logger
from xread.constants import FileFormats
from xread.pipeline import ScraperPipeline
# No AI model factory

# --- CLI Application ---
app = typer.Typer(name="xread", invoke_without_command=True, no_args_is_help=False)


async def run_interactive_mode_async(pipeline: ScraperPipeline) -> None:
    """Run interactive mode for URL input or commands."""
    print("XReader CLI (Perplexity Reports)")
    print("Enter URL to scrape, or command:")
    print("  help, list [limit], stats, delete <id>, quit")

    commands = [
        'scrape', 'list', 'stats', 'delete', 'help', 'quit', 'exit'
    ]
    command_completer = WordCompleter(commands, ignore_case=True)
    history = FileHistory(str(settings.data_dir / FileFormats.HISTORY_FILE))
    session = PromptSession(
        history=history,
        completer=command_completer,
        enable_history_search=True
    )

    await pipeline.initialize_browser()
    try:
        while True:
            try:
                user_input = await session.prompt_async('> ')
            except (EOFError, KeyboardInterrupt):
                print("\nExiting.")
                break
            if not user_input:
                continue

            parts = user_input.split(maxsplit=1)
            cmd = parts[0].lower()
            args_str = parts[1] if len(parts) > 1 else ""

            if cmd in ("quit", "exit"):
                print("Goodbye.")
                break
            elif cmd == "help":
                print("\nAvailable commands:")
                print("  <URL>                      Scrape URL (saves data + generates Perplexity report).")
                print("  list [limit]               List saved post metadata.")
                print("  stats                      Show count of saved posts.")
                print("  delete <id>                Delete a saved post by status ID.")
                print("  help                       Show this help message.")
                print("  quit / exit                Exit the application.\n")
            elif cmd == "list":
                try:
                    limit = int(args_str.split(maxsplit=1)[0]) if args_str and args_str.split(maxsplit=1)[0].isdigit() else None
                except ValueError:
                    print("Invalid limit.")
                    continue
                list_posts(limit)
            elif cmd == "stats":
                show_stats()
            elif cmd == "delete":
                delete_id = args_str.strip()
                if delete_id:
                    await delete_post(delete_id)
                else:
                    print("Usage: delete <status_id>")
            elif cmd == "scrape":
                url_to_scrape = args_str.strip()
                if url_to_scrape:
                    await pipeline.run(url_to_scrape)
                else:
                    print("Usage: scrape <url>")
            elif urlparse(user_input).scheme in ['http', 'https']:
                await pipeline.run(user_input)
            else:
                print(f"Unknown command/URL: {user_input}. Type 'help'.")
    finally:
        logger.info("Closing browser after interactive session...")
        await pipeline.close_browser()
        logger.info("Browser closed.")


@app.command(name="scrape")
async def scrape_command(
    url: str = typer.Argument(..., help="Tweet/Nitter URL to scrape")
) -> None:
    """Scrape URL, process images, generate search terms, and save combined data."""
    pipeline = ScraperPipeline()
    await pipeline.data_manager.initialize()
    logger.info(f"Scraping URL via command: {url}")
    await pipeline.run(url)


@app.command(name="list")
def list_posts(limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Max posts to list.")) -> None:
    """List saved post metadata."""
    pipeline = ScraperPipeline()
    logger.info(f"Listing posts with limit: {limit}")
    posts = pipeline.data_manager.list_meta(limit)
    if not posts:
        print("No saved posts found.")
        return
    print("\n--- Saved Posts ---")
    for meta in posts:
        sid = meta.get('status_id', 'N/A')
        author = meta.get('author', 'Unk')
        date_str = meta.get('scrape_date', 'Unk')
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            fmt_date = dt.strftime('%Y-%m-%d %H:%M')
        except Exception:
            fmt_date = date_str
        print(f"ID: {sid:<20} Author: @{author:<18} Scraped: {fmt_date}")
    print("-------------------\n")


@app.command(name="stats")
def show_stats() -> None:
    """Show count of saved posts."""
    pipeline = ScraperPipeline()
    count = pipeline.data_manager.count()
    print(f"Total saved posts: {count}")


@app.command(name="delete")
async def delete_post(status_id: str = typer.Argument(..., help="Status ID to delete.")) -> None:
    """Delete a saved post by status ID."""
    pipeline = ScraperPipeline()
    await pipeline.data_manager.initialize()
    logger.info(f"Deleting post {status_id}")
    if await pipeline.data_manager.delete(status_id):
        print(f"Deleted post {status_id}.")
    else:
        print(f"Could not delete post {status_id} (not found or error).")


async def async_main() -> None:
    """Main async entry point."""
    pipeline = ScraperPipeline()
    is_interactive = len(sys.argv) <= 1 or sys.argv[1] not in app.registered_commands
    try:
        await pipeline.data_manager.initialize()
        if is_interactive:
            await run_interactive_mode_async(pipeline)
        else:
            browser_needed = any(cmd_name in sys.argv for cmd_name in ['scrape'])
            if browser_needed:
                await pipeline.initialize_browser()
            try:
                app()
            finally:
                if browser_needed:
                    await pipeline.close_browser()
    except Exception as e:
        logger.exception("Fatal error in main execution:")
        typer.echo(f"Fatal Error: {e}", err=True)
        sys.exit(1)
