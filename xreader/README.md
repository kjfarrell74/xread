# XReader

XReader is an asynchronous CLI tool designed to scrape tweet data from a Nitter instance, generate image descriptions and search terms using the Google Gemini API, and save the combined data for further analysis. This tool is ideal for researchers, fact-checkers, and anyone interested in analyzing social media content with enhanced metadata.

## Features

- **Scraping**: Extracts tweet data including main posts and replies from a specified Nitter instance using Playwright and BeautifulSoup.
- **Image Processing**: Downloads images from posts and generates objective descriptions using the Gemini API.
- **Text Analysis**: Generates search terms and research questions based on post content to aid in fact-checking and deeper investigation.
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
   Copy the `.env` template to `.env` and update it with your Gemini API key:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` to replace `your_gemini_api_key_here` with your actual API key.

4. **Run the Tool**:
   You can now run XReader using:
   ```bash
   python xread.py
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

XReader can be configured via the `.env` file and `instructions.yaml` for custom prompts and settings.

- **`.env`**: Contains API keys, data directory paths, Nitter instance URL, and model selections for image and text analysis.
- **`instructions.yaml`**: Customizes prompts for image descriptions, search term generation, and research question options.

For a full list of configuration options, see [CONFIGURATION.md](CONFIGURATION.md).

## Data Storage

Scraped data is stored in the `scraped_data` directory with the following structure:
- `index.json`: An index of all scraped posts.
- `post_[STATUSID].json`: Individual post data including main post, replies, image descriptions, search terms, and research questions.
- `cache/image_descriptions.json`: Cached descriptions for images to avoid redundant API calls.

Debug information, such as failed HTML parses, is saved in the `debug_output` directory.

## Troubleshooting

- **API Key Issues**: Ensure your Gemini API key is correctly set in the `.env` file. If you encounter authentication errors, verify the key's validity.
- **Rate Limiting**: If you hit rate limits with the Gemini API or Nitter instance, consider adjusting the `MAX_IMAGE_DOWNLOADS_PER_RUN` in `.env` or adding delays between requests.
- **Parsing Errors**: If posts fail to parse, check `debug_output` for saved HTML files to diagnose the issue. Ensure the Nitter instance is operational.
- **Installation Problems**: Verify that all dependencies are installed correctly using `pip install -r requirements.txt`. Check for Python version compatibility.

## Contributing

If you'd like to contribute to XReader, please read our [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to submit pull requests, report issues, and suggest improvements.

## Changelog

For a history of changes and updates to XReader, refer to [CHANGELOG.md](CHANGELOG.md).

## License

This project is licensed under the MIT License - see the LICENSE file for details.
