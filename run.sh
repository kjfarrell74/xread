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
