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

- [ ] **Extract methods in NitterScraper class**: Refactor the large `fetch_html` method in `xread/scraper.py`:
  - [ ] Extract URL normalization logic
  - [ ] Extract error handling logic
  - [ ] Extract content validation logic

- [ ] **Extract methods in PerplexityModel class**: Break down the large `generate_report` method in `xread/ai_models.py`:
  - [ ] Extract multimodal API call logic
  - [ ] Extract text-only API call logic
  - [ ] Extract error handling logic

- [ ] **Extract methods in AsyncDataManager class**: Refactor methods in `xread/data_manager.py`:
  - [ ] Extract database initialization logic from `_initialize_db`
  - [ ] Extract JSON serialization logic from `save`

## Arrow Functions (per .clinerules)

- [ ] **Convert to arrow functions in frontend code**: Update functions in `frontend/src/components/Dashboard.tsx` to use arrow functions

## Plugin System Improvements

- [ ] **Complete MastodonPlugin implementation**: The `xread/plugins/plugin_mastodon.py` has placeholder implementation
  - [ ] Implement `scrape` method with proper Mastodon API integration

- [ ] **Enhance PluginManager**: Update `xread/plugins/manager.py` to:
  - [ ] Add proper registration for AIModelPlugin classes
  - [ ] Add plugin configuration capabilities
  - [ ] Add plugin discovery from external directories

## Error Handling

- [ ] **Improve error handling in pipeline.py**: Add more specific exception handling:
  - [ ] Handle network errors separately from parsing errors
  - [ ] Add retry logic for transient errors
  - [ ] Improve error messages for better debugging

- [ ] **Enhance error handling in AI model classes**: Improve error handling in `xread/ai_models.py`:
  - [ ] Add more specific exception types
  - [ ] Implement fallback strategies when API calls fail
  - [ ] Add better logging for API errors

## Code Organization

- [ ] **Reorganize imports**: Standardize import order across all files:
  - [ ] Standard library imports first
  - [ ] Third-party library imports second
  - [ ] Local application imports last

- [ ] **Standardize docstrings**: Ensure all functions and classes have consistent docstring format:
  - [ ] Add missing parameter descriptions
  - [ ] Add return value descriptions
  - [ ] Add exception descriptions

## Performance Improvements

- [ ] **Add caching to data_enhancer.py**: Implement caching for expensive operations:
  - [ ] Cache image descriptions
  - [ ] Cache date parsing results

- [ ] **Optimize image processing**: Improve image handling in `xread/ai_models.py`:
  - [ ] Add image size validation before processing
  - [ ] Implement image compression for large images
  - [ ] Add parallel processing for multiple images

## Testing

- [ ] **Add tests for plugins**: Create unit tests for plugin system:
  - [ ] Test plugin discovery and registration
  - [ ] Test plugin selection logic
  - [ ] Test individual plugins

- [ ] **Add tests for AI models**: Create unit tests for AI model integration:
  - [ ] Mock API responses for testing
  - [ ] Test error handling
  - [ ] Test fallback strategies

## Security

- [ ] **Enhance input validation**: Improve validation in `xread/scraper.py`:
  - [ ] Add URL validation
  - [ ] Add content validation
  - [ ] Add sanitization for user inputs

- [ ] **Implement rate limiting**: Add rate limiting for API calls:
  - [ ] Add configurable rate limits
  - [ ] Add backoff strategies
  - [ ] Add monitoring for rate limit errors
