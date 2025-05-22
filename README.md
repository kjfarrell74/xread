# XReader

XReader is an asynchronous CLI tool designed to scrape tweet data from a Nitter instance, generate detailed factual reports using AI models like Perplexity AI, and save the combined data for further analysis. This tool is ideal for researchers, fact-checkers, and anyone interested in analyzing social media content with enhanced metadata.

## Features

- **Scraping**: Extracts tweet data including main posts and replies from a specified Nitter instance using Playwright and BeautifulSoup.
- **Report Generation**: Generates detailed, factual reports about social media posts using AI models, with support for Perplexity AI API and potential for additional models.
- **Post Enhancement**: Enriches scraped data with normalized dates, media flags, and image descriptions using a centralized data enhancement module.
- **Data Normalization**: Standardizes data formats with ISO 8601 timestamps and consistent metadata structure.
- **Data Management**: Saves scraped data, image descriptions, and generated metadata in a structured JSON format for easy access and reference.

## Installation

### Prerequisites

- Python 3.8 or higher
- pip (Python package installer)

### Steps

1. **Clone the Repository** (if applicable):
   ```bash
   git clone <repository-url>
   cd xreader
   ```

2. **Install Dependencies**:
   Ensure you are in the project directory and run:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set Up Environment Variables**:
   Copy the `.env` template to `.env` and update it with your Perplexity API key:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` to replace placeholder values with your actual API keys for Perplexity and other configurations.

4. **Run the Tool**:
   You can now run XReader using:
   ```bash
   python xread.py
   ```
   Or use the provided shell script for convenience:
   ```bash
   bash run.sh
   ```

## Usage

XReader can be used in both interactive and command-line modes to scrape and analyze social media data.

### Interactive Mode

Run the tool without arguments to enter interactive mode:
```bash
python xread.py
```
In interactive mode, you can input URLs directly or use commands like `list`, `stats`, `delete`, and `reload_instructions`.

### Command-Line Mode

Scrape a specific URL directly:
```bash
python xread.py scrape <URL>
```
List saved posts:
```bash
python xread.py list
```
Show statistics:
```bash
python xread.py stats
```
Delete a saved post:
```bash
python xread.py delete <status_id>
```

For detailed usage examples, refer to [USAGE.md](USAGE.md).

## Configuration

XReader can be configured via the `.env` file.

- **`.env`**: Contains API keys for Perplexity, data directory paths, Nitter instance URL, and other configurations.

For a full list of configuration options, see [CONFIGURATION.md](CONFIGURATION.md).

## Data Storage

Scraped data is stored in the `scraped_data` directory with the following structure:
- `index.json`: An index of all scraped posts.
- `post_[STATUSID].json`: Individual post data including main post, replies, and AI-generated report.

Debug information, such as failed HTML parses, is saved in the `debug_output` directory.

## Troubleshooting

- **API Key Issues**: Ensure your Perplexity API key is correctly set in the `.env` file. If you encounter authentication errors, verify the key's validity.
- **Rate Limiting**: If you hit rate limits with the Perplexity API or Nitter instance, consider adjusting request frequency or adding delays between requests.
- **Parsing Errors**: If posts fail to parse, check `debug_output` for saved HTML files to diagnose the issue. Ensure the Nitter instance is operational.
- **Installation Problems**: Verify that all dependencies are installed correctly using `pip install -r requirements.txt`. Check for Python version compatibility.

## Contributing

If you'd like to contribute to XReader, please read our [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to submit pull requests, report issues, and suggest improvements.

## Changelog

For a history of changes and updates to XReader, refer to [CHANGELOG.md](CHANGELOG.md).

## License

This project is licensed under the MIT License - see the LICENSE file for details.
