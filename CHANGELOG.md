# Changelog

All notable changes to XReader will be documented in this file. This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) where possible, though as a CLI tool, versioning may be informal in early stages.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and entries are grouped by version or date for unreleased changes.

## [Unreleased]

### Added
- Initial project structure and core functionality for scraping tweet data from Nitter instances.
- Integration with Perplexity AI API for generating comprehensive factual reports on social media content.
- Post enhancer module for normalizing and enriching social media data with standardized dates and metadata.
- Comprehensive documentation including README, USAGE, CONFIGURATION, and CONTRIBUTING guides.
- Configuration files `.env` and `instructions.yaml` for customizable settings.
- Directory structure for data storage (`scraped_data`) and debugging (`debug_output`).
- Clipboard watcher for automatically detecting Twitter/X/Nitter URLs.
- ISO 8601 timestamp normalization with UTC timezone for all date fields.
- Heuristic-based image description generation from URL patterns.
- Media type flagging (has_images, has_video, has_links) for enhanced content awareness.

### Changed
- Replaced Google Gemini API integration with Perplexity AI for better report generation.
- Updated documentation to reflect the shift to Perplexity-based factual reporting.
- Enhanced Perplexity API prompt template for more detailed, unbiased reports.
- Improved image handling with automatic Nitter to Twitter media URL conversion.

### Fixed
- Twitter/X/Nitter URL detection regex pattern in clipboard watcher.
- Image URL formatting for compatibility with Perplexity API.
- Database schema handling for storing Perplexity reports.

### Removed
- Image description and research question generation using Gemini API (replaced with Perplexity).

## [0.1.0] - 2025-05-03

### Added
- Initial commit of XReader with basic scraping functionality using Playwright and BeautifulSoup.
- Support for interactive and command-line modes with commands like `scrape`, `list`, `stats`, and `delete`.
- Data management for saving and loading scraped posts in JSON format.
- Basic error handling and retry logic for network and API operations.

### Notes
- This version represents the starting point of the project as found in the initial codebase. Future changes will be logged above under "Unreleased" until a new version is defined.

## About Versioning

XReader is currently in an early development phase. Version numbers may not strictly follow Semantic Versioning until a stable release is reached. Each significant update or bundle of features/fixes will increment the version, with notes on breaking changes if any.

For the latest updates or to contribute, refer to the project's [README.md](README.md) and [CONTRIBUTING.md](CONTRIBUTING.md).
