# XReader Configuration Guide

This document details the configuration options for XReader, an asynchronous CLI tool for scraping tweet data from a Nitter instance, generating image descriptions and search terms using the Google Gemini API, and saving the combined data. Configuration is managed through two primary files: `.env` for environment variables and basic settings, and `instructions.yaml` for customizing prompts and generation parameters.

## Table of Contents

- [Overview](#overview)
- [Environment Variables (`.env`)](#environment-variables-env)
  - [API Keys](#api-keys)
  - [General Configuration](#general-configuration)
  - [Model Selection](#model-selection)
- [Custom Instructions (`instructions.yaml`)](#custom-instructions-instructionsyaml)
  - [Image Description Settings](#image-description-settings)
  - [Search Term Generation Customization](#search-term-generation-customization)
  - [Research Question Generation Customization](#research-question-generation-customization)
- [Applying Configuration Changes](#applying-configuration-changes)

## Overview

XReader's behavior can be tailored to meet specific needs through its configuration files. The `.env` file handles essential settings like API keys, data storage paths, and operational limits, while `instructions.yaml` allows for fine-tuning of AI prompts and generation logic. Understanding and adjusting these settings can optimize XReader for tasks such as fact-checking, contextual analysis, or data collection.

## Environment Variables (`.env`)

The `.env` file is used to set environment variables that control XReader's core functionality. It is loaded at startup and defines API access, data storage locations, and operational constraints. Below are the available settings, grouped by category.

### API Keys

- **`GEMINI_API_KEY`**
  - **Description**: Your Google Gemini API key, required for image description and text analysis features.
  - **Default**: `your_gemini_api_key_here` (placeholder, must be replaced with a valid key)
  - **Example**: `GEMINI_API_KEY=AIzaSy...yourkey...`
  - **Notes**: If not set or invalid, Gemini-related features (image descriptions, search term generation) will be disabled. Ensure this key has access to the models specified below.

### General Configuration

- **`DATA_DIR`**
  - **Description**: Directory path where scraped data, post JSON files, and caches are stored.
  - **Default**: `scraped_data`
  - **Example**: `DATA_DIR=my_custom_data_folder`
  - **Notes**: This directory will be created if it doesn't exist. Ensure write permissions are available.

- **`NITTER_BASE_URL`**
  - **Description**: The base URL of the Nitter instance to use for scraping tweets.
  - **Default**: `https://nitter.net`
  - **Example**: `NITTER_BASE_URL=https://nitter.example.com`
  - **Notes**: Choose a reliable Nitter instance to avoid rate limiting or downtime. URLs from Twitter or X.com are normalized to this instance.

- **`MAX_IMAGE_DOWNLOADS_PER_RUN`**
  - **Description**: Maximum number of images to download and describe per scraping run.
  - **Default**: `5`
  - **Example**: `MAX_IMAGE_DOWNLOADS_PER_RUN=10`
  - **Notes**: Set to `0` to disable image processing. Higher values may increase API usage and risk rate limiting.

- **`SAVE_FAILED_HTML`**
  - **Description**: Whether to save HTML content to `debug_output` when parsing fails, useful for troubleshooting.
  - **Default**: `true`
  - **Example**: `SAVE_FAILED_HTML=false`
  - **Notes**: Enable this to diagnose scraping issues. Files are saved with a timestamp and status ID if available.

### Model Selection

- **`IMAGE_DESCRIPTION_MODEL`**
  - **Description**: The Gemini model to use for generating image descriptions.
  - **Default**: `gemini-1.5-flash`
  - **Example**: `IMAGE_DESCRIPTION_MODEL=gemini-1.5-pro`
  - **Notes**: Ensure your API key has access to the specified model. Some models may have different costs or capabilities.

- **`TEXT_ANALYSIS_MODEL`**
  - **Description**: The Gemini model to use for text analysis tasks like search term and research question generation.
  - **Default**: `gemini-1.5-flash`
  - **Example**: `TEXT_ANALYSIS_MODEL=gemini-1.5-pro`
  - **Notes**: Similar to `IMAGE_DESCRIPTION_MODEL`, ensure compatibility with your API key. Set to an empty string to disable text analysis features if image processing is the only desired functionality.

## Custom Instructions (`instructions.yaml`)

The `instructions.yaml` file allows for deeper customization of XReader's AI interactions, specifically the prompts and parameters used for image description and content analysis. Changes to this file can be reloaded during runtime in interactive mode using the `reload_instructions` command. Below are the configurable sections.

### Image Description Settings

- **`image_description_prompt`**
  - **Description**: The prompt text used to instruct the Gemini model when describing images.
  - **Default**: 
    ```
    Describe this image objectively. Focus on visible elements, text, and context.
    If the image shows charts, graphs, or data, describe those details.
    Avoid speculating about intent or making judgments not supported by the image.
    ```
  - **Example**:
    ```
    image_description_prompt: >
      Provide a detailed, factual description of this image. Include any text, numbers, or data visualizations present.
      Do not infer emotions or motivations beyond what is visually evident.
    ```
  - **Notes**: Keep the prompt focused and objective to ensure useful descriptions. Use YAML's `>` syntax for multi-line strings.

### Search Term Generation Customization

- **`search_term_prompt_options`**
  - **Subfields**:
    - **`prioritize_fact_checking`**
      - **Description**: If true, search terms are biased towards fact-checking queries.
      - **Default**: `true`
      - **Example**: `prioritize_fact_checking: false`
    - **`include_source_credibility`**
      - **Description**: If true, includes terms to assess the credibility of sources mentioned in the content.
      - **Default**: `true`
      - **Example**: `include_source_credibility: false`
    - **`min_terms`**
      - **Description**: Minimum number of search terms to generate per post analysis.
      - **Default**: `8`
      - **Example**: `min_terms: 5`
    - **`max_terms`**
      - **Description**: Maximum number of search terms to generate per post analysis.
      - **Default**: `12`
      - **Example**: `max_terms: 15`
  - **Notes**: These settings indirectly influence the internal prompt for search term generation. Adjust them to balance between breadth and focus of generated terms.

### Research Question Generation Customization

- **`research_question_options`**
  - **Subfields**:
    - **`question_count`**
      - **Description**: Number of research questions to generate for each post analysis.
      - **Default**: `5`
      - **Example**: `question_count: 3`
    - **`include_methodology`**
      - **Description**: If true, includes questions about research methods or approaches related to the content.
      - **Default**: `true`
      - **Example**: `include_methodology: false`
    - **`prioritize_context`**
      - **Description**: If true, prioritizes questions that explore historical or contextual aspects of the content.
      - **Default**: `true`
      - **Example**: `prioritize_context: false`
  - **Notes**: These options shape the research questions generated, allowing customization for specific investigative goals.

## Applying Configuration Changes

- **`.env` Changes**: Modifications to `.env` require restarting XReader as these variables are loaded only at startup. After editing, relaunch the tool to apply changes:
  ```bash
  python xread.py
  ```

- **`instructions.yaml` Changes**: Updates to this file can be applied without restarting if you're in interactive mode. Use the following command to reload the instructions:
  ```
  > reload_instructions
  ```
  This feature allows for rapid iteration on prompts and settings during a session. Note that in command-line mode, a restart is still required.

By carefully configuring these settings, XReader can be adapted to various use cases, from casual data collection to rigorous academic research or journalistic fact-checking. For general usage instructions, refer to [USAGE.md](USAGE.md), and for project overview or troubleshooting, see [README.md](README.md).
