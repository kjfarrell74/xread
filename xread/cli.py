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
        settings.selected_model = ai_model
        logger.info(f"Selected AI model: {ai_model}")
    
    try:
        pipeline = ScraperPipeline(url)
        result = asyncio.run(pipeline.run())
        
        if enhance:
            logger.info("Enhancing scraped data with AI...")
            # Placeholder for AI enhancement logic
            pass
        
        data_manager = AsyncDataManager()
        if output_format.lower() == FileFormats.JSON.value:
            data_manager.save_as_json(result, output_file)
        elif output_format.lower() == FileFormats.MARKDOWN.value:
            data_manager.save_as_markdown(result, output_file)
        else:
            logger.error(f"Unsupported output format: {output_format}")
            sys.exit(1)
            
        logger.info(f"Scraping completed for {url}")
    except Exception as e:
        logger.error(f"Error during scraping: {str(e)}")
        sys.exit(1)

@app.command()
def list_data(
    format: str = typer.Option("json", "--format", "-f", help="Format to list the data in (json or markdown)")
):
    """List all scraped data in the specified format."""
    logger.info(f"Listing scraped data in {format} format...")
    data_manager = AsyncDataManager()
    asyncio.run(data_manager.initialize())
    data_list = data_manager.list_meta()
    if not data_list:
        print("No scraped data found.")
    else:
        for item in data_list:
            print(f"ID: {item['status_id']}, Author: {item['author']}, Scrape Date: {item['scrape_date']}")

@app.command()
def add_note(
    post_id: str = typer.Argument(..., help="ID of the post to add a note to"),
    content: str = typer.Argument(..., help="Content of the author note")
):
    """Add an author note to a specific post."""
    logger.info(f"Adding author note to post {post_id}")
    data_manager = AsyncDataManager()
    asyncio.run(data_manager.initialize())
    note = AuthorNote(content=content, timestamp=datetime.now())
    try:
        data_manager.add_author_note(post_id, note)
        logger.info(f"Author note added to post {post_id}")
        print(f"Note added to post {post_id}: {content}")
    except Exception as e:
        logger.error(f"Error adding author note: {str(e)}")
        sys.exit(1)

@app.command()
def delete(
    post_id: str = typer.Argument(..., help="ID of the post to delete")
):
    """Delete a post from the database by its ID."""
    logger.info(f"Deleting post {post_id}")
    data_manager = AsyncDataManager()
    asyncio.run(data_manager.initialize())
    success = asyncio.run(data_manager.delete(post_id))
    if success:
        print(f"Post {post_id} deleted successfully.")
        logger.info(f"Post {post_id} deleted successfully.")
    else:
        print(f"Failed to delete post {post_id}. It may not exist.")
        logger.warning(f"Failed to delete post {post_id}.")

@app.command()
def interactive():
    """Start an interactive mode for xread."""
    logger.info("Starting interactive mode...")
    history = FileHistory(".xread_history")
    commands = ["scrape", "list", "add-note", "delete", "help", "exit", "quit"]
    completer = WordCompleter(commands, ignore_case=True)
    session = PromptSession(completer=completer, history=history)
    
    while True:
        try:
            command = session.prompt("xread> ").strip()
            if not command:
                continue
            elif command.lower() in ["exit", "quit"]:
                logger.info("Exiting interactive mode.")
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
            break
        except Exception as e:
            logger.error(f"Error in interactive mode: {str(e)}")

if __name__ == "__main__":
    app()
