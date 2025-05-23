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
from xread.data_manager import DataManager

# Define the Typer app
app = typer.Typer(help="CLI tool for xread to scrape and process web content.")

@app.command()
def scrape(
    url: str = typer.Argument(..., help="URL of the post to scrape"),
    output_format: str = typer.Option("json", "--format", "-f", help="Output format for the scraped data"),
    output_file: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path. If not provided, DataManager saves to a standard location."),
    ai_model: Optional[str] = typer.Option(None, "--model", "-m", help="AI model to use for processing"),
    enhance: bool = typer.Option(False, "--enhance", "-e", help="Enhance the scraped data using AI")
):
    """Scrape a post from the given URL, save it via DataManager, and optionally enhance it."""
    logger.info(f"Initiating scrape for URL: {url}")

    async def _scrape():
        async with DataManager() as data_manager:
            if ai_model:
                settings.selected_model = ai_model
                logger.info(f"Using AI model: {settings.selected_model}")
            
            async with ScraperPipeline(data_manager) as pipeline: # Use as async context manager
                scraped_data = await pipeline.run(url=url) # Pass URL to run method
            
            if not scraped_data:
                logger.error(f"Scraping failed for {url}, no data returned.")
                sys.exit(1)
            
            logger.info(f"Successfully scraped data for {url}. Main post ID: {scraped_data.main_post.status_id if scraped_data.main_post else 'N/A'}")

            if enhance:
                logger.info("AI enhancement process would start here if implemented.")
                # Placeholder: AI enhancement logic.
                # Example: enhanced_data = await ai_module.enhance(scraped_data, data_manager)
                # For now, assume enhancement might be part of pipeline or a separate step.
                # DataManager.save (called by pipeline) can store an ai_report.
            
            # DataManager.save is called within pipeline.run().
            # Handle custom output file / format if specified, beyond DataManager's default JSON.
            if output_file:
                if output_format.lower() == FileFormats.JSON.value:
                    try:
                        # Create a dictionary representation for JSON output
                        json_output_data = {
                            "main_post": scraped_data.main_post.__dict__ if scraped_data.main_post else None,
                            "replies": [reply.__dict__ for reply in scraped_data.replies],
                            "original_url": scraped_data.original_url,
                            "scrape_date": scraped_data.scrape_date, # Ensure these attributes exist on ScrapedData
                            "ai_report": getattr(scraped_data, 'ai_report', None), # Safely get ai_report
                            "factual_context": getattr(scraped_data, 'factual_context', None),
                            "source": getattr(scraped_data, 'source', None),
                        }
                        if scraped_data.main_post and scraped_data.main_post.images:
                            json_output_data["main_post"]["images"] = [img.__dict__ for img in scraped_data.main_post.images]
                        for i, r_dict in enumerate(json_output_data["replies"]):
                            if scraped_data.replies[i].images:
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
    except Exception as e:
        logger.error(f"Unhandled error during scrape command for {url}: {str(e)}")
        sys.exit(1)

@app.command()
def list_data(
    format: str = typer.Option("json", "--format", "-f", help="Format to list the data (json or basic text)")
):
    """List all scraped data using DataManager."""
    logger.info(f"Listing scraped data, requested format: {format}")

    async def _list_data():
        async with DataManager() as data_manager:
            # list_meta is a synchronous method, called fine in async block
            data_list = data_manager.list_meta()
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
    except Exception as e:
        logger.error(f"Error listing data: {str(e)}")
        sys.exit(1)

@app.command()
def add_note(
    username: str = typer.Argument(..., help="Username of the author to add a note for."), # Changed from post_id
    content: str = typer.Argument(..., help="Content of the author note.")
):
    """Add or update an author's note in the database via DataManager."""
    logger.info(f"Attempting to add/update note for author: {username}")

    async def _add_note():
        async with DataManager() as data_manager:
            note = AuthorNote(username=username, note_content=content) # Timestamp is not part of AuthorNote model
            success = await data_manager.save_author_note(note)
            if success:
                logger.info(f"Author note successfully saved for {username}.")
                print(f"Note saved for author {username}: \"{content}\"")
            else:
                logger.error(f"Failed to save note for author {username}. Check logs.")
                sys.exit(1) # Exit if save failed
    
    try:
        asyncio.run(_add_note())
    except Exception as e:
        logger.error(f"Operation to add note for {username} failed: {str(e)}")
        sys.exit(1)

@app.command()
def delete(
    post_id: str = typer.Argument(..., help="ID of the post to delete.")
):
    """Delete a specific post by its ID using DataManager."""
    logger.info(f"Attempting to delete post with ID: {post_id}")

    async def _delete():
        async with DataManager() as data_manager:
            success = await data_manager.delete(post_id)
            if success:
                logger.info(f"Successfully deleted post {post_id}.")
                print(f"Post {post_id} has been deleted.")
            else:
                logger.warning(f"Failed to delete post {post_id}. It might not exist or an error occurred.")
                print(f"Could not delete post {post_id}. Check logs for details.")
                # Optionally exit: sys.exit(1)
    
    try:
        asyncio.run(_delete())
    except Exception as e:
        logger.error(f"Error deleting post {post_id}: {str(e)}")
        sys.exit(1)

@app.command()
async def interactive(): # Made interactive() async itself
    """Start an interactive xread session."""
    logger.info("Initializing interactive xread session...")
    history = FileHistory(".xread_history")
    command_list = ["scrape", "list", "add-note", "delete", "help", "exit", "quit"]
    completer = WordCompleter(command_list, ignore_case=True)
    session = PromptSession(completer=completer, history=history)

    print("Welcome to xread interactive mode.")
    print("Available commands: " + ", ".join(command_list))

    while True:
        try:
            input_str = await session.prompt_async("xread> ") # Async prompt
            input_str = input_str.strip()

            if not input_str:
                continue
            
            command_parts = input_str.split()
            main_command = command_parts[0].lower()

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
                    # Basic option parsing for interactive mode (can be extended)
                    output_format_param = "json"
                    output_file_param = None
                    ai_model_param = None
                    enhance_param = False
                    if "--format" in command_parts:
                        try: output_format_param = command_parts[command_parts.index("--format") + 1]
                        except IndexError: print("Error: --format requires an argument"); continue
                    if "--output" in command_parts:
                        try: output_file_param = command_parts[command_parts.index("--output") + 1]
                        except IndexError: print("Error: --output requires an argument"); continue
                    if "--model" in command_parts:
                        try: ai_model_param = command_parts[command_parts.index("--model") + 1]
                        except IndexError: print("Error: --model requires an argument"); continue
                    if "--enhance" in command_parts: enhance_param = True
                    
                    scrape(url=url_param, output_format=output_format_param, output_file=output_file_param, ai_model=ai_model_param, enhance=enhance_param)

                elif main_command == "list":
                    format_param = "json" # Default
                    if "--format" in command_parts:
                        try: format_param = command_parts[command_parts.index("--format") + 1]
                        except IndexError: print("Error: --format requires an argument.")
                    list_data(format=format_param)

                elif main_command == "add-note":
                    if len(command_parts) < 3: print("Usage: add-note <username> <content>"); continue
                    username_param = command_parts[1]
                    # Recombine content that might have spaces
                    content_param = " ".join(command_parts[2:]) 
                    if content_param.startswith('"') and content_param.endswith('"'): # Allow quoted content
                        content_param = content_param[1:-1]
                    add_note(username=username_param, content=content_param)

                elif main_command == "delete":
                    if len(command_parts) < 2: print("Usage: delete <post_id>"); continue
                    post_id_param = command_parts[1]
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
