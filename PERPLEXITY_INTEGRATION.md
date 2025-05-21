# Perplexity AI Integration

This document explains the changes made to integrate Perplexity AI API for generating factual reports in the xread application.

## Overview of Changes

The xread application has been updated to replace the previous Gemini-based image processing and research question generation with a factual report generation feature using the Perplexity AI API. The new implementation now sends both text and images to Perplexity for a more comprehensive analysis. Here's a summary of the key changes:

### 1. Replaced Components

- Replaced the Gemini-based `_process_media` method with new Perplexity-compatible image processing methods.
- Added new methods: `_process_images_perplexity` and `_download_and_encode_images` to prepare images for Perplexity.
- Removed the `_generate_search_terms` and `_generate_research_questions` methods.
- Updated the pipeline flow to use the new image processing and report generation.

### 2. Added Perplexity AI Integration

- Added a new `_generate_perplexity_report` method in the `ScraperPipeline` class.
- Implemented multimodal message formatting for Perplexity API to handle both text and images.
- Updated the pipeline flow to process images and include them in the Perplexity report generation.
- Set up proper error handling and logging for the Perplexity API integration.
- Limited image processing to a maximum of 4 images per post to avoid exceeding API limits.

### 3. Updated Data Storage

- Modified the database schema to handle the Perplexity report storage.
- Added migration code to handle existing databases.
- Updated the JSON file storage to include the Perplexity report.

### 4. Configuration Updates

- Updated the `CONFIGURATION.md` file to document the Perplexity API integration.
- Added information about the required environment variable `PERPLEXITY_API_KEY`.
- Marked deprecated settings related to Gemini API integration.

### 5. Constants and Messaging

- Added new constants for the Perplexity report prompt.
- Updated error messages to reflect the new integration.
- Added a test script for verifying the Perplexity integration.

## How to Use

1. Set up the Perplexity API key as an environment variable:
   ```bash
   export PERPLEXITY_API_KEY=your_api_key_here
   ```

2. Run the application as usual:
   ```bash
   python xread.py scrape URL_TO_TWITTER_POST
   ```

3. The application will:
   - Scrape the Twitter/X post text and images
   - Process and encode up to 4 images from the post
   - Send both text and images to the Perplexity API for analysis
   - Generate a comprehensive factual report
   - Save the report with the post data

4. View the report in the saved data in the JSON file located in `scraped_data/scraped_data/post_[STATUS_ID].json`.

## Testing

Several test scripts have been provided to verify the Perplexity integration:

### Basic Test
```bash
./test_perplexity.sh
```

This script will:
- Check if the Perplexity API key is set
- Run the application with a sample Twitter URL
- Show the results of the integration

### Direct API Test
```bash
python test_perplexity_direct.py
```

This script:
- Tests the Perplexity API directly with a sample text
- Shows the raw API response
- Saves the results to a debug file

### Test with Images
```bash
python test_perplexity_with_images.py
```

This script:
- Tests the full pipeline with a Twitter post containing images
- Processes and includes the images in the Perplexity API request
- Demonstrates the multimodal capabilities of the integration

## Troubleshooting

If you encounter issues with the Perplexity API integration, check the following:

1. Verify that the `PERPLEXITY_API_KEY` environment variable is set correctly.
2. Check the application logs for any error messages from the Perplexity API.
3. Ensure that your Perplexity API key has the necessary permissions and quota.

## Future Improvements

Potential improvements to the Perplexity integration:

1. Add support for customizing the Perplexity model through configuration.
2. Implement rate limiting and retry logic for API failures.
3. Add more detailed reporting options through configuration.