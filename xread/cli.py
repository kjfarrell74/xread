"""Command-line interface and interactive mode for xread."""

from __future__ import annotations # For forward references

import asyncio
import sys
from datetime import datetime
from typing import Optional, List, Dict, Any # Added List, Dict, Any
from urllib.parse import urlparse

import typer
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory

from xread.settings import settings, logger
from xread.constants import FileFormats
from xread.pipeline import ScraperPipeline
from xread.models import AuthorNote, ScrapedData # Added ScrapedData for type hint
from xread.data_manager import DataManager
from xread.exceptions import (
    XReadError,
    DatabaseError,
    ScrapingError,
    AIModelError,
    ConfigurationError,
    FileOperationError
)

# Define the Typer app
app: typer.Typer = typer.Typer(help="CLI tool for xread to scrape and process web content.")

@app.command()
def scrape(
    url: str = typer.Argument(..., help="URL of the post to scrape"),
    output_format: str = typer.Option("json", "--format", "-f", help="Output format for the scraped data"),
    output_file: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path. If not provided, DataManager saves to a standard location."),
    ai_model: Optional[str] = typer.Option(None, "--model", "-m", help="AI model to use for processing"),
    enhance: bool = typer.Option(False, "--enhance", "-e", help="Enhance the scraped data using AI")
) -> None:
    """Scrape a post from the given URL, save it via DataManager, and optionally enhance it."""
    logger.info(f"Initiating scrape for URL: {url}")

    async def _scrape() -> None:
        async with DataManager() as data_manager: # data_manager is DataManager
            if ai_model:
                settings.selected_model = ai_model
                logger.info(f"Using AI model: {settings.selected_model}")
            
            async with ScraperPipeline(data_manager) as pipeline: # pipeline is ScraperPipeline
                # pipeline.run returns Optional[ScrapedData]
                scraped_data: Optional[ScrapedData] = await pipeline.run(url=url) 
            
            if not scraped_data:
                # This case is handled by pipeline.run raising an error or returning None.
                # If it returns None (e.g. skipped), we might not want to sys.exit(1) always.
                # However, current pipeline.run raises on true failure, returns None on skip.
                # For now, assuming if scraped_data is None after pipeline.run, it's a situation to exit.
                logger.warning(f"Scraping for {url} did not return data (either skipped or failed before raising an exception).")
                # typer.echo("Scraping did not produce data or was skipped.", err=True) # User feedback handled by pipeline/specific error
                # sys.exit(1) # Let specific errors caught below handle exit. If skipped, it's not an error.
                # If pipeline.run returns None for "skipped", this is not an error state.
                # The try/except block below will catch actual errors from pipeline.run()
                return # If skipped, just return from _scrape

            logger.info(f"Successfully scraped data for {url}. Main post ID: {scraped_data.main_post.status_id if scraped_data.main_post else 'N/A'}")

            if enhance:
                logger.info("AI enhancement process would start here if implemented.")
            
            if output_file:
                if output_format.lower() == FileFormats.JSON.value:
                    try:
                        json_output_data: Dict[str, Any] = {
                            "main_post": scraped_data.main_post.__dict__ if scraped_data.main_post else None,
                            "replies": [reply.__dict__ for reply in scraped_data.replies],
                            "original_url": getattr(scraped_data, 'original_url', None), # Use getattr for safety
                            "scrape_date": getattr(scraped_data, 'scrape_date', None),
                            "ai_report": getattr(scraped_data, 'ai_report', None),
                            "factual_context": getattr(scraped_data, 'factual_context', None),
                            "source": getattr(scraped_data, 'source', None),
                        }
                        # Ensure main_post and its images are handled correctly
                        if scraped_data.main_post and hasattr(scraped_data.main_post, 'images') and scraped_data.main_post.images:
                             if json_output_data["main_post"] is not None: # mypy check
                                json_output_data["main_post"]["images"] = [img.__dict__ for img in scraped_data.main_post.images]
                        
                        # Ensure replies and their images are handled
                        for i, r_dict in enumerate(json_output_data.get("replies", [])):
                            if i < len(scraped_data.replies) and hasattr(scraped_data.replies[i], 'images') and scraped_data.replies[i].images:
                                r_dict["images"] = [img.__dict__ for img in scraped_data.replies[i].images]
                                
                        with open(output_file, 'w', encoding='utf-8') as f:
                            import json # ensure import
                            json.dump(json_output_data, f, indent=2, ensure_ascii=False)
                        logger.info(f"Scraped data also saved to JSON file: {output_file}")
                    except Exception as e:
                        logger.error(f"Failed to save custom JSON to {output_file}: {e}")
                elif output_format.lower() == FileFormats.MARKDOWN.value:
                    logger.warning(f"Markdown output format to {output_file} is selected but not implemented.")
                    # Example: md_content = convert_to_markdown(scraped_data)
                    # with open(output_file, 'w', encoding='utf-8') as f: f.write(md_content)
                else:
                    logger.error(f"Unsupported output format for custom file: {output_format}")
            
            logger.info(f"Scraping and processing for {url} completed.")

    try:
        asyncio.run(_scrape())
    except ScrapingError as e:
        logger.error(f"Scraping failed for {url}: {e}", exc_info=True)
        typer.echo(f"Error: Could not scrape content. {e}", err=True)
        sys.exit(1)
    except AIModelError as e:
        logger.error(f"AI model operation failed for {url}: {e}", exc_info=True)
        typer.echo(f"Error: AI model operation failed. {e}", err=True)
        sys.exit(1)
    except DatabaseError as e:
        logger.error(f"Database operation failed for {url}: {e}", exc_info=True)
        typer.echo(f"Error: A database problem occurred. {e}", err=True)
        sys.exit(1)
    except FileOperationError as e:
        logger.error(f"File operation failed for {url}: {e}", exc_info=True)
        typer.echo(f"Error: A file operation problem occurred. {e}", err=True)
        sys.exit(1)
    except ConfigurationError as e:
        logger.error(f"Configuration error during scrape for {url}: {e}", exc_info=True)
        typer.echo(f"Error: Configuration problem. {e}", err=True)
        sys.exit(1)
    except XReadError as e: # Catch other specific app errors
        logger.error(f"An application error occurred during scrape for {url}: {e}", exc_info=True)
        typer.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e: # Generic fallback
        logger.critical(f"An unexpected error occurred during scrape for {url}: {e}", exc_info=True)
        typer.echo("An unexpected critical error occurred. Please check logs for details.", err=True)
        sys.exit(1)

@app.command()
def list_data(
    format: str = typer.Option("json", "--format", "-f", help="Format to list the data (json or basic text)")
) -> None:
    """List all scraped data using DataManager."""
    logger.info(f"Listing scraped data, requested format: {format}")

    async def _list_data() -> None:
        async with DataManager() as data_manager: # data_manager is DataManager
            data_list: List[Dict[str, Any]] = await data_manager.list_meta()
            if not data_list:
                print("No scraped data found.")
                return

            if format.lower() == "json":
                import json # ensure import
                print(json.dumps(data_list, indent=2))
            else: # Default to basic text
                for item in data_list:
                    print(f"ID: {item['status_id']}, Author: {item['author']}, Scrape Date: {item['scrape_date']}")
    
    try:
        asyncio.run(_list_data())
    except DatabaseError as e:
        logger.error(f"Database operation failed while listing data: {e}", exc_info=True)
        typer.echo(f"Error: A database problem occurred while listing data. {e}", err=True)
        sys.exit(1)
    except XReadError as e:
        logger.error(f"An application error occurred while listing data: {e}", exc_info=True)
        typer.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        logger.critical(f"An unexpected error occurred while listing data: {e}", exc_info=True)
        typer.echo("An unexpected critical error occurred. Please check logs for details.", err=True)
        sys.exit(1)

@app.command()
def add_note(
    username: str = typer.Argument(..., help="Username of the author to add a note for."),
    content: str = typer.Argument(..., help="Content of the author note.")
) -> None:
    """Add or update an author's note in the database via DataManager."""
    logger.info(f"Attempting to add/update note for author: {username}")

    async def _add_note() -> None:
        async with DataManager() as data_manager: # data_manager is DataManager
            note: AuthorNote = AuthorNote(username=username, note_content=content)
            success: bool = await data_manager.save_author_note(note)
            if success:
                logger.info(f"Author note successfully saved for {username}.")
                print(f"Note saved for author {username}: \"{content}\"")
            else:
                # This path should ideally be handled by save_author_note raising an exception
                logger.error(f"Failed to save note for author {username} (save_author_note returned False).")
                typer.echo(f"Error: Could not save note for author {username}.", err=True)
                sys.exit(1)
    
    try:
        asyncio.run(_add_note())
    except DatabaseError as e:
        logger.error(f"Database operation failed while adding note for {username}: {e}", exc_info=True)
        typer.echo(f"Error: A database problem occurred while adding note. {e}", err=True)
        sys.exit(1)
    except XReadError as e:
        logger.error(f"An application error occurred while adding note for {username}: {e}", exc_info=True)
        typer.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        logger.critical(f"An unexpected error occurred while adding note for {username}: {e}", exc_info=True)
        typer.echo("An unexpected critical error occurred. Please check logs for details.", err=True)
        sys.exit(1)

@app.command()
def delete(
    post_id: str = typer.Argument(..., help="ID of the post to delete.")
) -> None:
    """Delete a specific post by its ID using DataManager."""
    logger.info(f"Attempting to delete post with ID: {post_id}")

    async def _delete() -> None:
        async with DataManager() as data_manager: # data_manager is DataManager
            success: bool = await data_manager.delete(post_id)
            if success:
                logger.info(f"Successfully deleted post {post_id}.")
                print(f"Post {post_id} has been deleted.")
            else:
                # This path might be hit if delete returns False without raising an error
                # (e.g., post not found, which isn't strictly an exception)
                logger.warning(f"Post {post_id} could not be deleted (it may not exist or delete operation returned False).")
                typer.echo(f"Info: Post {post_id} could not be deleted (it may not exist).", err=True)
                # sys.exit(1) # Not necessarily an error to exit(1) if post simply not found
    
    try:
        asyncio.run(_delete())
    except DatabaseError as e:
        logger.error(f"Database operation failed while deleting post {post_id}: {e}", exc_info=True)
        typer.echo(f"Error: A database problem occurred while deleting post. {e}", err=True)
        sys.exit(1)
    except XReadError as e:
        logger.error(f"An application error occurred while deleting post {post_id}: {e}", exc_info=True)
        typer.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        logger.critical(f"An unexpected error occurred while deleting post {post_id}: {e}", exc_info=True)
        typer.echo("An unexpected critical error occurred. Please check logs for details.", err=True)
        sys.exit(1)

@app.command()
async def interactive() -> None:
    """Start an interactive xread session."""
    logger.info("Initializing interactive xread session...")
    history: FileHistory = FileHistory(".xread_history")
    command_list: List[str] = ["scrape", "list", "add-note", "delete", "help", "exit", "quit"]
    completer: WordCompleter = WordCompleter(command_list, ignore_case=True)
    session: PromptSession = PromptSession(completer=completer, history=history)

    print("Welcome to xread interactive mode.")
    print("Available commands: " + ", ".join(command_list))

    while True:
        try:
            input_str: str = await session.prompt_async("xread> ")
            input_str = input_str.strip()

            if not input_str:
                continue
            
            command_parts: List[str] = input_str.split()
            main_command: str = command_parts[0].lower()

            if main_command in ["exit", "quit"]:
                logger.info("Exiting interactive mode as per user command.")
                print("Exiting...")
                break
            elif main_command == "help":
                print("\nAvailable commands: " + ", ".join(command_list))
                print("Use commands as you would on the CLI, e.g.:")
                print("  scrape <URL> [--format json/md] [--output <filepath>] [--model <modelname>] [--enhance]")
                print("  list [--format json/text]")
                print("  add-note <username> \"<note content>\"")
                print("  delete <post_id>")
                print("  exit / quit\n")
                continue

            # Typer commands are now structured with an inner async def _command_logic()
            # and asyncio.run(_command_logic()) within the command function.
            # So, we can call the command functions (scrape, list_data, etc.) directly.
            # Typer itself will manage the execution.
            # This is simpler than trying to re-parse all args manually here.
            # We effectively simulate a CLI call by rebuilding the arg list.
            # For this to work perfectly, the main app entry point `app()` would be called
            # with these args. Or, use Typer's `Context.invoke` if running within a Typer context.
            # For now, direct calls to the command functions. They manage their own asyncio.run.
            
            # Need to be careful: Typer commands are not designed to be called like regular functions
            # from Python code if you expect full CLI behavior (like automatic --help).
            # However, calling them will execute their logic.

            # For simplicity and since each command now handles its own asyncio.run(),
            # we can call them directly.
            # Parsing arguments from command_parts is still needed for parameters.
            # This is a simplified parser for interactive mode.
            try:
                if main_command == "scrape":
                    if len(command_parts) < 2: print("Usage: scrape <URL> [options...]"); continue
                    url_param = command_parts[1]
                    # Basic option parsing for interactive mode
                    url_param: str = command_parts[1]
                    output_format_param: str = "json"
                    output_file_param: Optional[str] = None
                    ai_model_param: Optional[str] = None
                    enhance_param: bool = False
                    # Simplified parsing for interactive mode; not as robust as Typer's full parsing
                    idx = 0
                    while idx < len(command_parts):
                        part = command_parts[idx]
                        if part == "--format" and idx + 1 < len(command_parts):
                            output_format_param = command_parts[idx+1]
                            idx += 1
                        elif part == "--output" and idx + 1 < len(command_parts):
                            output_file_param = command_parts[idx+1]
                            idx += 1
                        elif part == "--model" and idx + 1 < len(command_parts):
                            ai_model_param = command_parts[idx+1]
                            idx += 1
                        elif part == "--enhance":
                            enhance_param = True
                        idx += 1
                    
                    scrape(url=url_param, output_format=output_format_param, output_file=output_file_param, ai_model=ai_model_param, enhance=enhance_param)

                elif main_command == "list":
                    format_param: str = "json" # Default
                    if "--format" in command_parts:
                        try: 
                            format_idx = command_parts.index("--format")
                            if format_idx + 1 < len(command_parts):
                                format_param = command_parts[format_idx + 1]
                            else: raise IndexError # To be caught below
                        except (ValueError, IndexError): print("Error: --format requires an argument.")
                    list_data(format=format_param)

                elif main_command == "add-note":
                    if len(command_parts) < 3: print("Usage: add-note <username> <content>"); continue
                    username_param: str = command_parts[1]
                    content_param: str = " ".join(command_parts[2:])
                    if content_param.startswith('"') and content_param.endswith('"'):
                        content_param = content_param[1:-1]
                    add_note(username=username_param, content=content_param)

                elif main_command == "delete":
                    if len(command_parts) < 2: print("Usage: delete <post_id>"); continue
                    post_id_param: str = command_parts[1]
                    delete(post_id=post_id_param)
                else:
                    print(f"Unknown command: '{main_command}'. Type 'help' for available commands.")
            
            except SystemExit:
                # sys.exit() might be called by Typer commands on error.
                # Catch it to keep the interactive session alive.
                logger.info(f"Command '{main_command}' triggered SystemExit.")
            except Exception as cmd_exc:
                print(f"Error executing command '{main_command}': {cmd_exc}")
                logger.error(f"Error during interactive command '{main_command}': {cmd_exc}")

        except KeyboardInterrupt: # Ctrl+C
            logger.info("Interactive session interrupted by user (Ctrl+C).")
            print("\nInterrupted. Type 'exit' or 'quit' to leave.")
        except EOFError: # Ctrl+D
            logger.info("EOF signal received, exiting interactive mode.")
            print("\nExiting...")
            break # Exit loop
        except Exception as e:
            logger.error(f"An unexpected error occurred in interactive mode's main loop: {str(e)}")
            print(f"An critical error occurred: {str(e)}. Exiting interactive mode.")
            break # Exit loop for safety

if __name__ == "__main__":
    # Typer will handle running the `async def interactive()` command correctly
    app()
