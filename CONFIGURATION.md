# XReader Configuration

XReader can be configured using environment variables, typically set in a `.env` file. This document outlines the available configuration options and how to set them up.

## Environment Variables

Environment variables are the primary method for configuring XReader. You can set these variables in a `.env` file in the project root directory or directly in your shell environment.

### Creating a `.env` File

1. Copy the `.env.example` file to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Edit the `.env` file to set your specific values for API keys and other configurations.

### Key Environment Variables

- **PERPLEXITY_API_KEY**: Your API key for accessing the Perplexity AI API. This is required for generating factual reports on scraped social media data.
  - Example: `PERPLEXITY_API_KEY=pplx-your-api-key-here`
- **DATA_DIR**: Directory where scraped data and metadata will be stored. Defaults to `scraped_data`.
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
export PERPLEXITY_API_KEY=pplx-your-api-key-here
python xread.py
```

## AI Model Configuration

XReader currently supports the Perplexity AI model for report generation. The architecture is designed to be extensible for additional AI models in the future. The API key for Perplexity AI must be set via the `PERPLEXITY_API_KEY` environment variable as described above.

## Data Enhancement Configuration

XReader uses a centralized data enhancement module (`xread/data_enhancer.py`) to enrich scraped data with normalized dates, media flags, and image descriptions. No additional configuration is required for this module, but ensure that dependencies like `python-dateutil` and `Pillow` are installed via `requirements.txt`.

## Troubleshooting Configuration Issues

- **Missing API Key**: If you encounter errors related to authentication with Perplexity AI, ensure that `PERPLEXITY_API_KEY` is correctly set in your `.env` file or environment.
- **Invalid Nitter Instance**: If scraping fails, verify that the `NITTER_INSTANCE` URL is operational. You may need to switch to a different instance if the current one is down.
- **File Permission Issues**: Ensure that the directories specified in `DATA_DIR` and `DEBUG_DIR` have the necessary write permissions for storing data.

For further assistance or to suggest additional configuration options, please refer to the [CONTRIBUTING.md](CONTRIBUTING.md) guide.
