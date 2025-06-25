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
from xread.models import AuthorNote
from xread.data_manager import AsyncDataManager

# Define the Typer app
app = typer.Typer(help="CLI tool for xread to scrape and process web content.")

@app.command()
def scrape(
    url: str = typer.Argument(..., help="URL of the post to scrape"),
    output_format: str = typer.Option("json", "--format", "-f", help="Output format for the scraped data"),
    output_file: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path. If not provided, output to stdout."),
    ai_model: Optional[str] = typer.Option(None, "--model", "-m", help="AI model to use for processing"),
    enhance: bool = typer.Option(False, "--enhance", "-e", help="Enhance the scraped data using AI")
):
    """Scrape a post from the given URL and optionally enhance it using AI."""
    logger.info(f"Starting scrape for URL: {url}")
    if ai_model:
        settings.ai_model = str(ai_model)
        logger.info(f"Selected AI model: {ai_model}")
    else:
        logger.info(f"Using default AI model: {settings.ai_model}")
    
    data_manager = AsyncDataManager()
    try:
        asyncio.run(data_manager.initialize())
        pipeline = ScraperPipeline(data_manager)
        result = asyncio.run(pipeline.run(url))
        
        if enhance:
            logger.info("Enhancing scraped data with AI...")
            # Ensure AI model is a string for enhancement
            ai_model_value = getattr(settings.ai_model, 'value', settings.ai_model)
            ai_model_str = str(ai_model_value)
            logger.info(f"Using AI model for enhancement: {ai_model_str}")
            # Placeholder for AI enhancement logic
            pass
        
        if output_format.lower() == "json" or output_format.lower() == FileFormats.JSON_EXTENSION:
            data_manager.save_as_json(result, output_file)
        elif output_format.lower() == "markdown":
            data_manager.save_as_markdown(result, output_file)
        else:
            logger.error(f"Unsupported output format: {output_format}")
            # Close database connection before exiting
            asyncio.run(data_manager.close())
            sys.exit(1)
            
        logger.info(f"Scraping completed for {url}")
    except Exception as e:
        logger.error(f"Error during scraping: {str(e)}")
        # Close database connection on error
        try:
            asyncio.run(data_manager.close())
        except Exception as close_error:
            logger.error(f"Error closing database connection: {str(close_error)}")
        sys.exit(1)
    finally:
        # Ensure database connection is closed
        try:
            asyncio.run(data_manager.close())
        except Exception as close_error:
            logger.error(f"Error closing database connection: {str(close_error)}")

@app.command()
def list_data(
    format: str = typer.Option("json", "--format", "-f", help="Format to list the data in (json or markdown)")
):
    """List all scraped data in the specified format."""
    logger.info(f"Listing scraped data in {format} format...")
    data_manager = AsyncDataManager()
    try:
        asyncio.run(data_manager.initialize())
        data_list = asyncio.run(data_manager.list_meta())
        if not data_list:
            print("No scraped data found.")
        else:
            for item in data_list:
                print(f"ID: {item['status_id']}, Author: {item['author']}, Scrape Date: {item['scrape_date']}")
    except Exception as e:
        logger.error(f"Error listing data: {str(e)}")
        # Close database connection on error
        try:
            asyncio.run(data_manager.close())
        except Exception as close_error:
            logger.error(f"Error closing database connection: {str(close_error)}")
        sys.exit(1)
    finally:
        # Ensure database connection is closed
        try:
            asyncio.run(data_manager.close())
        except Exception as close_error:
            logger.error(f"Error closing database connection: {str(close_error)}")

@app.command()
def add_note(
    username: str = typer.Argument(..., help="Username/author to add a note for"),
    content: str = typer.Argument(..., help="Content of the author note")
):
    """Add an author note for a specific username that will be included in future scrapes."""
    logger.info(f"Adding author note for username {username}")
    data_manager = AsyncDataManager()
    try:
        asyncio.run(data_manager.initialize())
        note = AuthorNote(username=username, note_content=content)
        success = asyncio.run(data_manager.save_author_note(note))
        if not success:
            print(f"Failed to add note for username {username}.")
            return
        logger.info(f"Author note added for username {username}")
        print(f"Note added for @{username}: {content}")
    except Exception as e:
        logger.error(f"Error adding author note: {str(e)}")
        # Close database connection on error
        try:
            asyncio.run(data_manager.close())
        except Exception as close_error:
            logger.error(f"Error closing database connection: {str(close_error)}")
        sys.exit(1)
    finally:
        # Ensure database connection is closed
        try:
            asyncio.run(data_manager.close())
        except Exception as close_error:
            logger.error(f"Error closing database connection: {str(close_error)}")

@app.command()
def delete(
    post_id: str = typer.Argument(..., help="ID of the post to delete")
):
    """Delete a post from the database by its ID."""
    logger.info(f"Deleting post {post_id}")
    data_manager = AsyncDataManager()
    try:
        asyncio.run(data_manager.initialize())
        success = asyncio.run(data_manager.delete(post_id))
        if success:
            print(f"Post {post_id} deleted successfully.")
            logger.info(f"Post {post_id} deleted successfully.")
        else:
            print(f"Failed to delete post {post_id}. It may not exist.")
            logger.warning(f"Failed to delete post {post_id}.")
    except Exception as e:
        logger.error(f"Error deleting post: {str(e)}")
        # Close database connection on error
        try:
            asyncio.run(data_manager.close())
        except Exception as close_error:
            logger.error(f"Error closing database connection: {str(close_error)}")
        sys.exit(1)
    finally:
        # Ensure database connection is closed
        try:
            asyncio.run(data_manager.close())
        except Exception as close_error:
            logger.error(f"Error closing database connection: {str(close_error)}")

@app.command()
def interactive():
    """Start an interactive mode for xread."""
    logger.info("Starting interactive mode...")
    history = FileHistory(".xread_history")
    commands = ["scrape", "list", "add-note", "delete", "help", "exit", "quit"]
    completer = WordCompleter(commands, ignore_case=True)
    session = PromptSession(completer=completer, history=history)
    
    # Initialize data manager
    data_manager = AsyncDataManager()
    asyncio.run(data_manager.initialize())
    
    while True:
        try:
            command = session.prompt("xread> ").strip()
            if not command:
                continue
            elif command.lower() in ["exit", "quit"]:
                logger.info("Exiting interactive mode.")
                # Close database connection before exiting
                asyncio.run(data_manager.close())
                break
            elif command.lower() == "help":
                print("Available commands: scrape, list, add-note, delete, help, exit, quit")
            elif command.lower().startswith("scrape"):
                parts = command.split()
                if len(parts) < 2:
                    print("Usage: scrape <URL> [--format <format>] [--output <file>] [--model <model>] [--enhance]")
                    continue
                url = parts[1]
                args = parts[2:] if len(parts) > 2 else []
                scrape(url, *args)
            elif command.lower().startswith("list"):
                parts = command.split()
                format_arg = "json"
                if len(parts) > 1 and "--format" in parts:
                    idx = parts.index("--format")
                    if idx + 1 < len(parts):
                        format_arg = parts[idx + 1]
                list_data(format_arg)
            elif command.lower().startswith("add-note"):
                parts = command.split()
                if len(parts) < 3:
                    print("Usage: add-note <post_id> <content>")
                    continue
                post_id = parts[1]
                content = " ".join(parts[2:])
                add_note(post_id, content)
            elif command.lower().startswith("delete"):
                parts = command.split()
                if len(parts) < 2:
                    print("Usage: delete <post_id>")
                    continue
                post_id = parts[1]
                delete(post_id)
            else:
                print(f"Unknown command: {command}")
        except KeyboardInterrupt:
            logger.info("Interactive mode interrupted by user.")
            # Close database connection on keyboard interrupt
            asyncio.run(data_manager.close())
            break
        except Exception as e:
            logger.error(f"Error in interactive mode: {str(e)}")
            # Attempt to close database connection on error
            try:
                asyncio.run(data_manager.close())
            except Exception as close_error:
                logger.error(f"Error closing database connection: {str(close_error)}")

if __name__ == "__main__":
    app()
