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

# Play notification sound when the script completes, if a ding.mp3 file is present
if [ -f "ding.mp3" ]; then
  # Try common audio players
  if command -v mpg123 >/dev/null 2>&1; then
    mpg123 -q ding.mp3
  elif command -v afplay >/dev/null 2>&1; then
    afplay ding.mp3
  elif command -v mpv >/dev/null 2>&1; then
    mpv --no-terminal --quiet ding.mp3
  elif command -v cvlc >/dev/null 2>&1; then
    cvlc --play-and-exit --quiet ding.mp3
  else
    echo "Notification sound found but no suitable player installed (mpg123, afplay, mpv, cvlc)."
  fi
fi

