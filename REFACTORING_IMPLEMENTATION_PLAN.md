# Refactoring Implementation Plan

This document provides detailed implementation steps for the highest priority refactoring tasks identified in the REFACTORING_TODO.md file.

## Priority 1: Consolidate Duplicate Code

### Task 1.1: Consolidate async_file modules

**Current Issue:**
Identical implementations exist in `xread/core/async_file.py` and `xread/utils/async_file.py`, causing code duplication and maintenance challenges.

**Implementation Steps:**
1. Keep `xread/core/async_file.py` as the canonical implementation
2. Update all imports across the codebase to use `xread/core/async_file.py`
3. Remove `xread/utils/async_file.py`
4. Add a deprecation warning in `xread/utils/__init__.py` to handle any potential external imports:
   ```python
   import warnings
   from xread.core.async_file import write_json_async, read_json_async, ensure_directory_async

   warnings.warn(
       "Importing from xread.utils.async_file is deprecated. "
       "Please import from xread.core.async_file instead.",
       DeprecationWarning,
       stacklevel=2
   )
   ```
5. Update tests to import from the correct module

**Files to Modify:**
- `xread/pipeline.py`
- `xread/data_manager.py`
- Any other files importing from either async_file module
- `tests/unit/test_async_file.py` (already uses the core module)

### Task 1.2: Consolidate utility functions

**Current Issue:**
Duplication between `xread/utils.py` and `xread/core/utils.py`, particularly the `with_retry` decorator and `play_ding` function.

**Implementation Steps:**
1. Move all unique functions from `xread/utils.py` to `xread/core/utils.py`
2. Fix the path in the `play_ding()` function to ensure correct relative path to `ding.mp3`
3. Update imports across the codebase
4. Add re-exports in `xread/utils.py` to maintain backward compatibility:
   ```python
   import warnings
   from xread.core.utils import with_retry, play_ding

   warnings.warn(
       "Importing from xread.utils is deprecated. "
       "Please import from xread.core.utils instead.",
       DeprecationWarning,
       stacklevel=2
   )
   ```

**Files to Modify:**
- `xread/utils.py`
- `xread/core/utils.py`
- Any files importing from either utils module

## Priority 2: Function Extraction (per .clinerules)

### Task 2.1: Extract methods in ScraperPipeline class

**Current Issue:**
The `ScraperPipeline` class in `xread/pipeline.py` contains several large methods that handle multiple responsibilities, making the code harder to maintain and test.

**Implementation Steps:**

1. Extract image processing logic from `_generate_ai_report`:
   ```python
   async def _process_images_for_ai(self, scraped_data: ScrapedData, sid: str) -> List[Dict[str, Any]]:
       """Process images from scraped data for AI model consumption."""
       # Move image processing logic here from _generate_ai_report
       # ...
   ```

2. Extract URL normalization and status ID extraction from `run`:
   ```python
   async def _normalize_and_extract_id(self, url: str) -> Tuple[str, str, Optional[str]]:
       """Normalize URL and extract status IDs.
       
       Returns:
           Tuple containing (normalized_url, main_status_id, url_status_id)
       """
       # Move URL normalization and ID extraction logic here
       # ...
   ```

3. Extract error handling logic into separate methods:
   ```python
   async def _handle_fetch_error(self, url: str, error: Exception, sid: Optional[str] = None, html_content: Optional[str] = None) -> None:
       """Handle errors during fetch and parse operations."""
       # Move error handling logic here
       # ...
   ```

**Files to Modify:**
- `xread/pipeline.py`

### Task 2.2: Extract methods in PerplexityModel class

**Current Issue:**
The `generate_report` method in `xread/ai_models.py` is very large and handles multiple responsibilities.

**Implementation Steps:**

1. Extract multimodal API call logic:
   ```python
   async def _make_multimodal_api_call(self, prompt_text: str, image_content: List[Dict[str, Any]], sid: str) -> Optional[str]:
       """Make a multimodal API call to Perplexity with text and images."""
       # Move multimodal API call logic here
       # ...
   ```

2. Extract text-only API call logic:
   ```python
   async def _make_text_only_api_call(self, prompt_text: str, sid: str) -> Optional[str]:
       """Make a text-only API call to Perplexity."""
       # Move text-only API call logic here
       # ...
   ```

3. Extract error handling logic:
   ```python
   async def _handle_api_error(self, error: Exception, api_type: str, sid: str) -> str:
       """Handle API call errors and generate appropriate error messages."""
       # Move error handling logic here
       # ...
   ```

**Files to Modify:**
- `xread/ai_models.py`

## Priority 3: Plugin System Improvements

### Task 3.1: Complete MastodonPlugin implementation

**Current Issue:**
The `MastodonPlugin` in `xread/plugins/plugin_mastodon.py` has only a placeholder implementation.

**Implementation Steps:**

1. Research Mastodon API requirements
2. Implement the `scrape` method with proper Mastodon API integration:
   ```python
   async def scrape(self, url: str) -> ScrapedData:
       """Scrape data from a Mastodon post URL."""
       # Parse the URL to extract instance and post ID
       instance, post_id = self._parse_mastodon_url(url)
       
       # Fetch the post data using Mastodon API
       post_data = await self._fetch_mastodon_post(instance, post_id)
       
       # Convert to ScrapedData format
       return self._convert_to_scraped_data(post_data, url)
   ```

3. Add helper methods for URL parsing, API interaction, and data conversion

**Files to Modify:**
- `xread/plugins/plugin_mastodon.py`
- Add new files for Mastodon API client if needed

### Task 3.2: Enhance PluginManager

**Current Issue:**
The `PluginManager` in `xread/plugins/manager.py` lacks proper registration for `AIModelPlugin` classes and has limited plugin discovery capabilities.

**Implementation Steps:**

1. Add proper registration for AIModelPlugin classes:
   ```python
   def load_plugins(self):
       """Dynamically load all plugins from plugins directory"""
       for finder, name, ispkg in pkgutil.iter_modules(['xread/plugins']):
           if name.startswith('plugin_'):
               module = importlib.import_module(f'xread.plugins.{name}')
               # Auto-register plugins based on base class
               for attr_name in dir(module):
                   attr = getattr(module, attr_name)
                   if isinstance(attr, type):
                       if issubclass(attr, ScraperPlugin) and attr != ScraperPlugin:
                           self.scraper_plugins.append(attr())
                       elif issubclass(attr, AIModelPlugin) and attr != AIModelPlugin:
                           self.ai_plugins.append(attr())
   ```

2. Add plugin configuration capabilities:
   ```python
   def __init__(self, config: Optional[Dict[str, Any]] = None):
       self.scraper_plugins: List[ScraperPlugin] = []
       self.ai_plugins: List[AIModelPlugin] = []
       self.config = config or {}
       self.load_plugins()
   ```

3. Add plugin discovery from external directories:
   ```python
   def load_plugins_from_directory(self, directory: str) -> None:
       """Load plugins from an external directory."""
       if not os.path.exists(directory):
           logger.warning(f"Plugin directory {directory} does not exist")
           return
           
       sys.path.insert(0, directory)
       for finder, name, ispkg in pkgutil.iter_modules([directory]):
           if name.startswith('plugin_'):
               try:
                   module = importlib.import_module(name)
                   # Auto-register plugins based on base class
                   for attr_name in dir(module):
                       attr = getattr(module, attr_name)
                       if isinstance(attr, type):
                           if issubclass(attr, ScraperPlugin) and attr != ScraperPlugin:
                               self.scraper_plugins.append(attr())
                           elif issubclass(attr, AIModelPlugin) and attr != AIModelPlugin:
                               self.ai_plugins.append(attr())
               except Exception as e:
                   logger.error(f"Error loading plugin {name}: {e}")
       sys.path.pop(0)
   ```

**Files to Modify:**
- `xread/plugins/manager.py`

## Next Steps

After implementing these high-priority refactoring tasks, proceed to the remaining items in the REFACTORING_TODO.md file, focusing on:

1. Extracting methods in the remaining classes
2. Improving error handling
3. Standardizing code organization
4. Adding performance improvements
5. Enhancing testing coverage
6. Implementing security improvements
