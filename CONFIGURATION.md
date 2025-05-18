# XReader Configuration Guide

This document details the configuration options for XReader, an asynchronous CLI tool for scraping tweet data from a Nitter instance, generating factual reports using the Perplexity AI API, and saving the combined data. Configuration is managed through the `.env` file for environment variables and basic settings.

## Table of Contents

- [Overview](#overview)
- [Environment Variables (`.env`)](#environment-variables-env)
  - [API Keys](#api-keys)
  - [General Configuration](#general-configuration)
  - [Model Selection](#model-selection)
- [Applying Configuration Changes](#applying-configuration-changes)

## Overview

XReader's behavior can be tailored to meet specific needs through its configuration file. The `.env` file handles essential settings like API keys, data storage paths, and operational limits. The Perplexity AI API is used to generate factual reports from the content of Twitter/X posts. Understanding and adjusting these settings can optimize XReader for tasks such as fact-checking, contextual analysis, or data collection.

## Environment Variables (`.env`)

The `.env` file is used to set environment variables that control XReader's core functionality. It is loaded at startup and defines API access, data storage locations, and operational constraints. Below are the available settings, grouped by category.

### API Keys

- **`PERPLEXITY_API_KEY`**
  - **Description**: Your Perplexity AI API key, required for generating factual reports from post content.
  - **Default**: `your_perplexity_api_key_here` (placeholder, must be replaced with a valid key)
  - **Example**: `PERPLEXITY_API_KEY=pplx-...yourkey...`
  - **Notes**: If not set or invalid, report generation will be disabled. You can obtain a key from the Perplexity AI dashboard.


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

- **`PERPLEXITY_MODEL`**
  - **Description**: The Perplexity AI model to use for generating factual reports.
  - **Default**: `sonar-pro`
  - **Example**: `PERPLEXITY_MODEL=sonar-pro`
  - **Notes**: Currently hardcoded to `sonar-pro` in the application code. Future updates may allow customizing this model through the configuration.


## Applying Configuration Changes

- **`.env` Changes**: Modifications to `.env` require restarting XReader as these variables are loaded only at startup. After editing, relaunch the tool to apply changes:
  ```bash
  python xread.py
  ```

By carefully configuring these settings, XReader can be adapted to various use cases, from casual data collection to rigorous academic research or journalistic fact-checking. For general usage instructions, refer to [USAGE.md](USAGE.md), and for project overview or troubleshooting, see [README.md](README.md).
