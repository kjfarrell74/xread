# Refactoring TODO List

This document outlines refactoring opportunities in the xread project, prioritized by impact and complexity.

## Code Duplication

- [x] **Consolidate async_file modules**: There are identical implementations in `xread/core/async_file.py` and `xread/utils/async_file.py`. Keep only one implementation and update all imports.
  - Preferred location: `xread/core/async_file.py`
  - Update all imports to use the consolidated module

- [x] **Consolidate utility functions**: There's duplication between `xread/utils.py` and `xread/core/utils.py`, particularly the `with_retry` decorator and `play_ding` function.
  - Consolidate in `xread/core/utils.py`
  - Update path in `play_ding()` function to ensure correct relative path to `ding.mp3`

## Function Extraction (per .clinerules)

- [x] **Extract methods in ScraperPipeline class**: Break down large methods in `xread/pipeline.py` into smaller functions with clear responsibilities
  - [x] Extract image processing logic from `_generate_ai_report` into a separate method
  - [x] Extract URL normalization and status ID extraction from `run` into a dedicated method
  - [x] Extract error handling logic into separate methods

- [x] **Extract methods in NitterScraper class**: Refactor the large `fetch_html` method in `xread/scraper.py`:
  - [x] Extract URL normalization logic
  - [x] Extract error handling logic
  - [x] Extract content validation logic

- [x] **Extract methods in PerplexityModel class**: Break down the large `generate_report` method in `xread/ai_models.py`:
  - [x] Extract multimodal API call logic
  - [x] Extract text-only API call logic
  - [x] Extract error handling logic

- [x] **Extract methods in AsyncDataManager class**: Refactor methods in `xread/data_manager.py`:
  - [x] Extract database initialization logic from `_initialize_db`
  - [x] Extract JSON serialization logic from `save`

## Arrow Functions (per .clinerules)

- [x] **Convert to arrow functions in frontend code**: Update functions in `frontend/src/components/Dashboard.tsx` to use arrow functions

## Plugin System Improvements

- [x] **Complete MastodonPlugin implementation**: The `xread/plugins/plugin_mastodon.py` has placeholder implementation
  - [x] Implement `scrape` method with proper Mastodon API integration

- [x] **Enhance PluginManager**: Update `xread/plugins/manager.py` to:
  - [x] Add proper registration for AIModelPlugin classes
  - [x] Add plugin configuration capabilities
  - [x] Add plugin discovery from external directories

## Error Handling

- [x] **Improve error handling in pipeline.py**: Add more specific exception handling:
  - [x] Handle network errors separately from parsing errors
  - [x] Add retry logic for transient errors
  - [x] Improve error messages for better debugging

- [x] **Enhance error handling in AI model classes**: Improve error handling in `xread/ai_models.py`:
  - [x] Add more specific exception types
  - [x] Implement fallback strategies when API calls fail
  - [x] Add better logging for API errors

## Code Organization

- [x] **Reorganize imports**: Standardize import order across all files:
  - [x] xread/ai_models.py
  - [x] xread/pipeline.py
  - [x] Standard library imports first
  - [x] Third-party library imports second
  - [x] Local application imports last

- [x] **Standardize docstrings**: Ensure all functions and classes have consistent docstring format:
  - [x] Add missing parameter descriptions
  - [x] Add return value descriptions
  - [x] Add exception descriptions

## Performance Improvements

- [x] **Add caching to data_enhancer.py**: Implement caching for expensive operations:
  - [x] Cache image descriptions
  - [x] Cache date parsing results

- [x] **Optimize image processing**: Improve image handling in `xread/ai_models.py`:
  - [x] Add image size validation before processing
  - [x] Implement image compression for large images
  - [x] Add parallel processing for multiple images

## Testing

- [x] **Add tests for plugins**: Create unit tests for plugin system:
  - [x] Test plugin discovery and registration
  - [x] Test plugin selection logic
  - [x] Test individual plugins

- [x] **Add tests for AI models**: Create unit tests for AI model integration:
  - [x] Mock API responses for testing
  - [x] Test error handling
  - [x] Test fallback strategies

## Security

- [x] **Enhance input validation**: Improve validation in `xread/scraper.py`:
  - [x] Add URL validation
  - [x] Add content validation
  - [x] Add sanitization for user inputs

- [x] **Implement rate limiting**: Add rate limiting for API calls:
  - [x] Add configurable rate limits
  - [x] Add backoff strategies
  - [x] Add monitoring for rate limit errors
