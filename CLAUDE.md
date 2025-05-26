# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Environment Setup

This project uses a virtual environment for dependency management. Always activate the virtual environment:

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (required for scraping)
python -m playwright install firefox
```

The `run.sh` script automates this setup and can be used instead:

```bash
./run.sh  # Interactive mode or clipboard watcher
./run.sh scrape <URL>  # CLI mode with arguments
```

## Common Commands

### Running the Application
```bash
# Interactive mode (clipboard watcher)
python xread.py interactive
# OR use the convenience script
./run.sh

# CLI mode - scrape specific URL
python xread.py scrape <URL>

# List all scraped data
python xread.py list-data

# Add author note to a post
python xread.py add-note <post_id> "note content"

# Delete a post
python xread.py delete <post_id>
```

### Testing
Tests are organized in the `tests/` directory with unit, integration, and security test suites. However, pytest is not currently in requirements.txt, so tests need to be run manually:

```bash
# Install pytest first
pip install pytest

# Run all tests
python -m pytest tests/

# Run specific test suite
python -m pytest tests/unit/
python -m pytest tests/integration/
python -m pytest tests/security/

# Run single test file
python -m pytest tests/unit/test_data_manager.py
```

### Database Operations
The application uses SQLite with aiosqlite for async operations. Database files are stored in `scraped_data/xread_data.db`. The schema is automatically created and migrated on startup.

## Architecture Overview

### Core Pipeline Flow
1. **URL Input** → `cli.py` receives URLs via CLI or interactive mode
2. **Scraping** → `pipeline.py` orchestrates the process using `scraper.py` + Playwright
3. **AI Enhancement** → `ai_models.py` generates reports via Perplexity/Gemini APIs  
4. **Data Storage** → `data_manager.py` saves to SQLite + JSON files
5. **Optional Processing** → `post_enhancer.py` adds metadata and image descriptions

### Key Components

**ScraperPipeline** (`pipeline.py`): Central orchestrator that manages browser instances, coordinates scraping, AI processing, and data storage.

**AsyncDataManager** (`data_manager.py`): Handles all database operations and JSON file storage. Uses SQLite with automatic schema migrations for adding new columns.

**NitterScraper** (`scraper.py`): Extracts tweet data from Nitter instances using BeautifulSoup + Playwright. Supports multiple Nitter instance fallbacks.

**AI Models** (`ai_models.py`): Abstracted AI interface supporting Perplexity and Gemini APIs. Uses BaseAIModel ABC for extensibility.

**Settings System** (`settings.py`): Multi-layered configuration supporting config.ini, environment variables, and defaults with precedence order.

### Data Models
- **Post**: Individual tweet/post with metadata (likes, retweets, images)
- **ScrapedData**: Container for main post + replies 
- **Image**: Image URL with optional AI-generated descriptions
- **AuthorNote**: User-specific notes stored per username
- **UserProfile**: Extended user metadata

### Browser Management
Uses Playwright with Firefox for JavaScript-heavy Nitter pages. Browser instances are managed through `BrowserManager` with proper async context handling.

### Configuration Precedence
1. Environment variables (highest)
2. config.ini file settings  
3. Default values (lowest)

Essential environment variables: `PERPLEXITY_API_KEY`, `GEMINI_API_KEY`, `DATA_DIR`, `NITTER_INSTANCE`

### Security Features
- Input validation via `security_patches.py` 
- Secure file permissions (0o640 for data files)
- SQL injection protection through parameterized queries
- Rate limiting and retry logic with exponential backoff

### Plugin System
Extensible plugin architecture in `plugins/` supporting custom data sources (Mastodon, etc.) via base plugin interface.

## Database Schema

The SQLite database auto-migrates and contains:
- `posts`: Main posts with AI reports, topic tags, engagement metrics
- `replies`: Threaded replies linked to posts
- `author_notes`: User-specific notes
- `user_profiles`: Extended user metadata
- `image_cache`: Cached image descriptions

New columns are automatically added via `AsyncDataManager._create_tables_and_migrate()`.

## AI Integration

Two AI providers supported:
- **Perplexity**: Fact-checking and analysis (default)
- **Gemini**: Alternative AI model

Models implement `BaseAIModel` interface. Selection via `ai_model` setting in config.ini or `AI_MODEL` environment variable.

## Error Handling

- Failed HTML content saved to `debug_output/` for debugging
- Comprehensive logging with configurable levels
- Retry logic with exponential backoff for network operations
- Graceful degradation when AI APIs are unavailable