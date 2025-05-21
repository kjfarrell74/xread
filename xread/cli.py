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
from xread.ai_models import AIModelFactory  # late import to avoid circulars

_interactive_mode_pipeline: Optional[ScraperPipeline] = None

# --- CLI Application ---
app = typer.Typer(name="xread", invoke_without_command=True, no_args_is_help=False)


@app.callback(invoke_without_command=True)
async def main_callback(ctx: typer.Context):
    global _interactive_mode_pipeline

    pipeline = ScraperPipeline()
    await pipeline.data_manager.initialize() # Initialize data_manager

    if ctx.invoked_subcommand is None:
        # No command was specified by the user. Prepare for interactive mode.
        _interactive_mode_pipeline = pipeline
    else:
        # A command is being run. Store pipeline in context for that command.
        ctx.obj = pipeline


async def run_interactive_mode_async(pipeline: ScraperPipeline) -> None:
    """Run interactive mode for URL input or commands."""
    current_model = settings.ai_model_type
    print("XReader CLI (AI-powered image & text analysis)")
    print(f"Current AI model: {current_model} (set AI_MODEL_TYPE env or use --model to change)")
    print("Enter URL to scrape, or command:")
    print("  help, model, list [limit], stats, delete <id>, reload_instructions, quit")

    commands = [
        'scrape', 'list', 'stats', 'delete', 'model', 'help', 'quit', 'exit', 'reload_instructions'
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
            elif cmd == "reload_instructions":
                pipeline.reload_instructions()
                print("Instructions reloaded.")
            elif cmd == "model":
                if args_str.strip():
                    new_model = args_str.strip().lower()
                    if new_model in AIModelFactory.supported():
                        settings.ai_model_type = new_model
                        print(f"AI model switched to: {new_model} (will apply on next scrape)")
                    else:
                        print(f"Unsupported model. Supported: {', '.join(AIModelFactory.supported())}")
                else:
                    print(f"Current AI model: {settings.ai_model_type}")
            elif cmd == "help":
                print("\nAvailable commands:")
                print("  <URL>                      Scrape URL (saves data + generates search terms).")
                print("  list [limit]               List saved post metadata.")
                print("  stats                      Show count of saved posts.")
                print("  delete <id>                Delete a saved post by status ID.")
                print("  reload_instructions        Reload instructions from instructions.yaml (if used).")
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
    ctx: typer.Context,
    url: str = typer.Argument(..., help="Tweet/Nitter URL to scrape"),
    model: Optional[str] = typer.Option(
        None, # Default to None, so we know if the user specified it
        "--model",
        "-m",
        help=f"AI model to use (e.g., {', '.join(AIModelFactory.supported())}). Overrides .env. Default: {settings.ai_model_type}",
    ),
) -> None:
    """Scrape URL, process images, generate search terms, and save combined data."""
    pipeline: ScraperPipeline = ctx.obj
    original_env_model_type = settings.ai_model_type
    user_specified_model = model is not None

    if user_specified_model:
        if model not in AIModelFactory.supported():
            typer.echo(f"Error: Unsupported model '{model}'. Supported models are: {', '.join(AIModelFactory.supported())}")
            raise typer.Exit(code=1)
        settings.ai_model_type = model
        if pipeline.ai_model and pipeline.ai_model.model_type_name != model:
            pipeline.ai_model = None # Force re-creation with the new model type

    logger.info(f"Scraping URL via command: {url} using model '{settings.ai_model_type}'")

    try:
        # Browser needs to be initialized for each scrape command run,
        # as it's not persistent outside interactive mode or a single command context.
        await pipeline.initialize_browser()
        await pipeline.run(url)
    finally:
        await pipeline.close_browser()
        if user_specified_model:
            settings.ai_model_type = original_env_model_type


# Implementation for listing posts
def _list_posts_impl(pipeline: ScraperPipeline, limit: Optional[int] = None) -> None:
    """Internal implementation for listing saved post metadata."""
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


@app.command(name="list")
def list_posts(ctx: typer.Context, limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Max posts to list.")) -> None:
    """List saved post metadata."""
    pipeline: ScraperPipeline = ctx.obj
    _list_posts_impl(pipeline, limit)


# Implementation for showing stats
def _show_stats_impl(pipeline: ScraperPipeline) -> None:
    """Internal implementation for showing count of saved posts."""
    count = pipeline.data_manager.count()
    print(f"Total saved posts: {count}")


@app.command(name="stats")
def show_stats(ctx: typer.Context) -> None:
    """Show count of saved posts."""
    pipeline: ScraperPipeline = ctx.obj
    _show_stats_impl(pipeline)


# Implementation for deleting a post
async def _delete_post_impl(pipeline: ScraperPipeline, status_id: str) -> None:
    """Internal implementation for deleting a saved post by status ID."""
    # await pipeline.data_manager.initialize() # Already initialized
    logger.info(f"Deleting post {status_id}")
    if await pipeline.data_manager.delete(status_id):
        print(f"Deleted post {status_id}.")
    else:
        print(f"Could not delete post {status_id} (not found or error).")


@app.command(name="delete")
async def delete_post(ctx: typer.Context, status_id: str = typer.Argument(..., help="Status ID to delete.")) -> None:
    """Delete a saved post by status ID."""
    pipeline: ScraperPipeline = ctx.obj
    await _delete_post_impl(pipeline, status_id)


async def async_main() -> None:
    """Main async entry point."""
    global _interactive_mode_pipeline
    try:
        # Typer's app() will call main_callback.
        # If a command is given, it runs. main_callback sets ctx.obj.
        # If no command, main_callback sets _interactive_mode_pipeline.
        app()

        # If _interactive_mode_pipeline is set, it means no command was run by Typer,
        # so we should start the interactive mode.
        if _interactive_mode_pipeline is not None:
            await run_interactive_mode_async(_interactive_mode_pipeline)
            _interactive_mode_pipeline = None # Clear it after use
    except SystemExit:
        # Allow SystemExit to propagate, often used by Typer for --help etc.
        raise
    except Exception as e:
        logger.exception("Fatal error in main execution:")
        typer.echo(f"Fatal Error: {e}", err=True)
        # Ensure we exit with a non-zero code for unhandled exceptions,
        # but not if it's a SystemExit (which might have code 0 for --help).
        if not isinstance(e, SystemExit): # Typer might raise SystemExit for valid reasons
            sys.exit(1)
