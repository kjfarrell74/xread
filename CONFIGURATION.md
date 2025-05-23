# XReader Configuration

XReader can be configured using environment variables, typically set in a `.env` file. This document outlines the available configuration options and how to set them up.

## Configuration Methods

XReader can be configured using a combination of a configuration file (`config.ini`), environment variables, and defaults. The precedence order is:
1. Environment variables (highest priority, overrides all other settings).
2. Settings from `config.ini` (if the file exists).
3. Default values (lowest priority).

### Configuration File (`config.ini`)

XReader supports a configuration file named `config.ini` in the project root directory. This file allows you to define persistent settings without relying on environment variables. Below is an overview of the sections and key settings available in `config.ini`:

- **[General] Section**:
  - `ai_model`: Specify the AI model to use for report generation (e.g., `perplexity` or `gemini`). Default: `perplexity`.
  - `log_level`: Set the logging level (e.g., `INFO`, `DEBUG`, `WARNING`). Default: `INFO`.

- **[API Keys] Section**:
  - **Note:** Storing API keys directly in `config.ini` is discouraged for security reasons. It's recommended to use environment variables.
  - `; perplexity_api_key`: Example of Perplexity API Key (commented out, set via `XREAD_PERPLEXITY_API_KEY` environment variable).
  - `; gemini_api_key`: Example of Gemini API Key (commented out, set via `XREAD_GEMINI_API_KEY` environment variable).

- **[Pipeline] Section**:
  - `save_failed_html`: Boolean to enable/disable saving failed HTML content for debugging. Default: `true`.
  - `max_images_per_post`: Limit the number of images processed per post for AI report generation. Default: `10`.
  - `report_max_tokens`: Set the maximum token limit for AI-generated reports. Default: `2000`.
  - `report_temperature`: Set the temperature for AI model output (lower values for more factual output). Default: `0.1`.

- **[Scraper] Section**:
  - `nitter_instance`: Specify the Nitter instance URL to use for scraping. Default: `nitter.net`.
  - `fetch_timeout`: Set a timeout for fetching HTML content (in seconds). Default: `30`.

To customize these settings, edit the `config.ini` file in the project root. If the file does not exist, you can create it based on the structure above or copy the default version provided with the project.

### Environment Variables

Environment variables can override settings from `config.ini` and are useful for temporary changes or sensitive information like API keys. You can set these variables in a `.env` file in the project root directory or directly in your shell environment.

### Creating a `.env` File

1. Copy the `.env.example` file to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Edit the `.env` file to set your specific values for API keys and other configurations.

### Key Environment Variables

**API Keys (Recommended Method):**
- **`XREAD_PERPLEXITY_API_KEY`**: Your API key for Perplexity AI. Required for using Perplexity for report generation.
  - Example: `XREAD_PERPLEXITY_API_KEY="pplx-your-api-key-here"`
- **`XREAD_GEMINI_API_KEY`**: Your API key for Google Gemini. Required for using Gemini for report generation.
  - Example: `XREAD_GEMINI_API_KEY="your-gemini-api-key-here"`

**Other Environment Variables:**
- **`DATA_DIR`**: Directory where scraped data and metadata will be stored. Defaults to `scraped_data`.
  - Example: `DATA_DIR=scraped_data`
- **DEBUG_DIR**: Directory for storing debug information like failed HTML parses. Defaults to `debug_output`.
  - Example: `DEBUG_DIR=debug_output`
- **NITTER_INSTANCE**: The Nitter instance URL to use for scraping Twitter/X data. Choose a reliable instance.
  - Example: `NITTER_INSTANCE=https://nitter.net`
- **SAVE_FAILED_HTML**: Whether to save HTML content when parsing fails, useful for debugging. Set to `true` or `false`. Defaults to `true`.
  - Example: `SAVE_FAILED_HTML=true`

### Loading Environment Variables

If you use a `.env` file, the `run.sh` script will automatically load these variables. Alternatively, you can set them directly in your shell before running the application:

```bash
export XREAD_PERPLEXITY_API_KEY="pplx-your-api-key-here"
export XREAD_GEMINI_API_KEY="your-gemini-api-key-here"
python xread.py
```
Alternatively, place them in a `.env` file in the project root, and they will be loaded automatically:
```
XREAD_PERPLEXITY_API_KEY="pplx-your-api-key-here"
XREAD_GEMINI_API_KEY="your-gemini-api-key-here"
```

## AI Model Configuration

XReader supports multiple AI models for report generation, including Perplexity and Gemini. The architecture is designed to be extensible for additional models in the future. You can select the AI model using the `ai_model` setting in `config.ini` or by setting the `AI_MODEL` environment variable (e.g., `perplexity` or `gemini`).

**API keys for these models should be set using environment variables (`XREAD_PERPLEXITY_API_KEY` and `XREAD_GEMINI_API_KEY`) as described above.** While `settings.py` might allow fallback to `config.ini` for these keys if environment variables are not set, this is primarily for local development convenience and is not the recommended approach for production or shared environments.

## Data Enhancement Configuration

XReader uses a centralized data enhancement module (`xread/data_enhancer.py`) to enrich scraped data with normalized dates, media flags, and image descriptions. No additional configuration is required for this module, but ensure that dependencies like `python-dateutil` and `Pillow` are installed via `requirements.txt`.

## Troubleshooting Configuration Issues

- **Missing API Key**: If you encounter errors related to authentication with an AI model, ensure that the corresponding API key (`XREAD_PERPLEXITY_API_KEY` or `XREAD_GEMINI_API_KEY`) is correctly set in your environment (e.g., via `.env` file or direct export). The application will log a warning if an API key is not found.
- **Invalid Nitter Instance**: If scraping fails, verify that the `nitter_instance` URL in `config.ini` or `NITTER_INSTANCE` environment variable is operational. You may need to switch to a different instance if the current one is down.
- **File Permission Issues**: Ensure that the directories specified in `DATA_DIR` (or `data_dir` in `config.ini`) and `DEBUG_DIR` have the necessary write permissions for storing data.
- **Configuration File Not Found**: If `config.ini` is not found, XReader will fall back to environment variables and defaults. Ensure the file is in the project root if you intend to use it.

For further assistance or to suggest additional configuration options, please refer to the [CONTRIBUTING.md](CONTRIBUTING.md) guide.
