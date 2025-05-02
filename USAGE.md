# XReader Usage Guide

This document provides detailed examples and instructions on how to use XReader, an asynchronous CLI tool for scraping tweet data from a Nitter instance, generating image descriptions and search terms using the Google Gemini API, and saving the combined data.

## Table of Contents

- [Overview](#overview)
- [Running XReader](#running-xreader)
  - [Interactive Mode](#interactive-mode)
  - [Command-Line Mode](#command-line-mode)
- [Command Examples](#command-examples)
  - [Scrape a URL](#scrape-a-url)
  - [List Saved Posts](#list-saved-posts)
  - [Show Statistics](#show-statistics)
  - [Delete a Saved Post](#delete-a-saved-post)
- [Interactive Commands](#interactive-commands)
- [Customizing Behavior](#customizing-behavior)

## Overview

XReader allows users to scrape social media posts from Nitter, a privacy-focused alternative to Twitter, and enhances the data with AI-generated image descriptions and search terms for fact-checking or research purposes. The tool can be operated in two primary modes: interactive mode for a user-friendly interface and command-line mode for quick, scripted operations.

## Running XReader

### Interactive Mode

To start XReader in interactive mode, simply run the script without any arguments:

```bash
python xread.py
```

In this mode, you'll be presented with a prompt where you can enter URLs to scrape or use specific commands to manage saved data. Interactive mode supports command history and auto-completion for ease of use.

### Command-Line Mode

For direct operations or integration into scripts, use command-line mode by specifying a command and its arguments:

```bash
python xread.py <command> [arguments]
```

Available commands include `scrape`, `list`, `stats`, and `delete`. Each command is detailed below with examples.

## Command Examples

### Scrape a URL

To scrape a specific tweet or thread from a Nitter, Twitter, or X.com URL, use the `scrape` command:

```bash
python xread.py scrape https://nitter.net/user/status/1234567890123456789
```

Or directly in interactive mode by typing the URL:

```
> https://twitter.com/user/status/1234567890123456789
```

XReader will normalize the URL to the configured Nitter instance, fetch the content, process any images (up to the limit set in `.env`), generate search terms and research questions if configured, and save the data to the `scraped_data` directory.

### List Saved Posts

To view metadata of previously saved posts, sorted by scrape date (most recent first):

```bash
python xread.py list
```

Limit the number of posts displayed:

```bash
python xread.py list --limit 5
```

In interactive mode:

```
> list 5
```

This displays the status ID, author, and scrape date for each post, helping you keep track of your saved data.

### Show Statistics

To get a quick count of how many posts have been saved:

```bash
python xread.py stats
```

In interactive mode:

```
> stats
```

This is useful for monitoring the growth of your dataset over time.

### Delete a Saved Post

To remove a saved post by its status ID:

```bash
python xread.py delete 1234567890123456789
```

In interactive mode:

```
> delete 1234567890123456789
```

This deletes the associated JSON file from `scraped_data` and updates the index, freeing up space and maintaining data relevance.

## Interactive Commands

When in interactive mode, XReader supports the following commands in addition to direct URL input:

- **`help`**: Displays a list of available commands and their descriptions.
- **`list [limit]`**: Lists saved post metadata, optionally limited to a specified number.
- **`stats`**: Shows the total count of saved posts.
- **`delete <id>`**: Deletes a saved post by its status ID.
- **`reload_instructions`**: Reloads custom instructions from `instructions.yaml` without restarting the application. Useful for tweaking prompts or settings on the fly.
- **`quit` or `exit`**: Exits the interactive mode.

Example session:

```
XReader CLI (Gemini Image Desc + Search Terms)
Enter URL to scrape, or command:
  help, list [limit], stats, delete <id>, reload_instructions, quit
> list 3
--- Saved Posts ---
ID: 1234567890123456789    Author: @user1            Scraped: 2025-05-03 04:30
ID: 1234567890123456788    Author: @user2            Scraped: 2025-05-02 15:22
ID: 1234567890123456787    Author: @user3            Scraped: 2025-05-01 09:10
-------------------
> https://x.com/user4/status/1234567890123456790
[Processing URL...]
Success: Saved post 1234567890123456790.
> quit
Goodbye.
```

## Customizing Behavior

XReader's behavior can be customized through configuration files:

- **`.env`**: Adjust settings like the data directory (`DATA_DIR`), Nitter instance URL (`NITTER_BASE_URL`), maximum image downloads per run (`MAX_IMAGE_DOWNLOADS_PER_RUN`), and Gemini model selections. See [CONFIGURATION.md](CONFIGURATION.md) for details.
- **`instructions.yaml`**: Modify prompts for image descriptions or parameters for search term and research question generation. Use the `reload_instructions` command in interactive mode to apply changes without restarting.

By tailoring these configurations, you can adapt XReader to specific research needs, such as focusing on fact-checking or contextual analysis.

For further assistance or to report issues, refer to the troubleshooting section in [README.md](README.md) or check the project's contribution guidelines in [CONTRIBUTING.md](CONTRIBUTING.md).
