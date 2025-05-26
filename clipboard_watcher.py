import asyncio
import pyperclip
from pyperclip import PyperclipException
import re
import sys
import time

import os
# Define sound notification function
def play_sound():
    print("Playing sound notification")
    success = False

    if sys.platform.startswith('win'):
        # Windows - use console bell
        os.system('echo \a')
        success = True
    else:
        # Linux - try multiple approaches
        # First try console bell
        os.system('printf "\\a"')

        # Then try to play the sound file if it exists
        if os.path.exists('sound.wav'):
            # Try multiple Linux audio players
            cmd = ('paplay sound.wav 2>/dev/null || '
                  'aplay sound.wav 2>/dev/null || '
                  'ffplay -nodisp -autoexit -loglevel quiet sound.wav 2>/dev/null || '
                  'mplayer -really-quiet sound.wav 2>/dev/null')
            exit_code = os.system(cmd)
            success = exit_code == 0

    if success:
        print("✓ Sound notification played")

SOUND_FUNC = play_sound

from xread.pipeline import ScraperPipeline
from xread.data_manager import AsyncDataManager

# Pattern for Twitter/X/Nitter post URLs
TWITTER_URL_RE = re.compile(
    r"(https?://)?(www\.)?(twitter\.com|x\.com|nitter\.[a-z0-9\-\.]+)/[^/]+/status/\d+",
    re.IGNORECASE
)

async def process_url(url):
    data_manager = AsyncDataManager()
    pipeline = ScraperPipeline(data_manager)
    await data_manager.initialize()
    await pipeline.initialize_browser()
    try:
        await pipeline.run(url)
        print("✅ Scraping completed successfully!")
    except Exception as e:
        print(f"❌ Error during scraping: {e}")
        raise
    finally:
        # Ensure browser is closed
        await pipeline.close_browser()
        # Close database connection
        await data_manager.close()
        print("🔔 Playing completion notification...")
        SOUND_FUNC()

def main():
    last_clipboard = ""
    print("Monitoring clipboard for Twitter/X/Nitter links...")
    # Play a sound to confirm script started and audio is working
    print("Testing sound notification...")
    SOUND_FUNC()
    
    # Initialize data manager
    data_manager = AsyncDataManager()
    asyncio.run(data_manager.initialize())
    
    try:
        while True:
            try:
                clipboard_content = pyperclip.paste()
                if clipboard_content is None:
                    clipboard_content = ""
                else:
                    clipboard_content = clipboard_content.strip()
            except PyperclipException:
                print("Error: No clipboard copy/paste mechanism found.")
                print("On Linux, install 'xclip' or 'xsel' (e.g., sudo apt-get install xclip).")
                print("See https://pyperclip.readthedocs.io/en/latest/index.html#not-implemented-error for details.")
                # Close database connection before exiting
                asyncio.run(data_manager.close())
                sys.exit(1)
            except Exception as e:
                print(f"Error pasting from clipboard: {e}")
                clipboard_content = ""
            if clipboard_content != last_clipboard:
                match = TWITTER_URL_RE.search(clipboard_content)
                if match:
                    url = match.group(0)
                    print(f"Detected URL: {url} – Starting scrape.")
                    asyncio.run(process_url(url))
                    print("Scrape complete. Ready for next link.")
                last_clipboard = clipboard_content
            time.sleep(1)  # Check every second
    except KeyboardInterrupt:
        print("Exiting clipboard watcher...")
        # Close database connection on keyboard interrupt
        asyncio.run(data_manager.close())
        print("Resources cleaned up. Exiting.")
    except Exception as e:
        print(f"Error in clipboard watcher: {e}")
        # Attempt to close database connection on error
        try:
            asyncio.run(data_manager.close())
        except Exception as close_error:
            print(f"Error closing database connection: {close_error}")
        sys.exit(1)

if __name__ == "__main__":
    main()
