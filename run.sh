#!/bin/bash

# Exit on error
set -e

# Set working directory to script location
cd "$(dirname "$0")"

# Create virtual environment if missing
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip and install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Check and install Playwright browsers if needed
echo "Checking Playwright browser installation..."
if ! python -c "from playwright.sync_api import sync_playwright; sync_playwright().start().firefox.launch(headless=True).close()" 2>/dev/null; then
  echo "Playwright browsers not installed or outdated. Installing..."
  python -m playwright install firefox
  # Install system dependencies if on Linux
  if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "Installing system dependencies for Playwright..."
    python -m playwright install-deps firefox
  fi
  echo "Playwright Firefox browser installed successfully."
else
  echo "Playwright Firefox browser is already installed and working."
fi

# Load environment variables safely
if [ -f ".env" ]; then
  echo "Loading environment variables from .env"
  set -a
  . .env
  set +a
else
  echo "Warning: .env file not found, skipping environment variable load"
fi

# Run the appropriate script based on arguments:
# If any arguments are provided, run the xread CLI; otherwise, start the clipboard watcher.
if [ "$#" -gt 0 ]; then
  echo "Running xread CLI with args: $@"
  python xread.py "$@"
else
  echo "Monitoring clipboard for Twitter/X/Nitter links..."
  python clipboard_watcher.py
fi

# Notification sound is now handled in Python, not in the shell script
