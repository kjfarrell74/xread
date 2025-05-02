"""Data management functionality for saving and loading scraped data in xread."""

import json
from pathlib import Path
from typing import Optional, Dict, List, Set, Any
import aiofiles
from datetime import datetime, timezone

from xread.settings import settings, logger
from xread.models import ScrapedData, Post, Image

class DataManager:
    """Handles saving and loading scraped data to/from JSON files."""
    def __init__(self):
        self.data_dir = settings.data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.data_dir / 'index.json'
        self.cache_dir = self.data_dir / 'cache'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / 'image_descriptions.json'
        self.image_cache: Dict[str, str] = {}
        self.index: Dict[str, Any] = {'posts': {}, 'latest_scrape': None}
        self.seen: Set[str] = set()

    async def initialize(self) -> None:
        """Initialize the data manager by loading index and cache."""
        await self._load_index()
        await self._load_cache()

    async def _load_index(self) -> None:
        if self.index_file.exists():
            try:
                async with aiofiles.open(self.index_file, mode='r', encoding='utf-8') as f:
                    self.index = json.loads(await f.read())
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading index.json: {e}. Resetting index.")
                self.index = {'posts': {}, 'latest_scrape': None}
        self.seen = set(self.index.get('posts', {}).keys())

    async def _load_cache(self) -> None:
        if self.cache_file.exists():
            try:
                async with aiofiles.open(self.cache_file, mode='r', encoding='utf-8') as f:
                    self.image_cache = json.loads(await f.read())
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading image cache: {e}. Starting empty.")
                self.image_cache = {}

    async def _save_index(self) -> None:
        try:
            async with aiofiles.open(self.index_file, mode='w', encoding='utf-8') as f:
                await f.write(json.dumps(self.index, indent=2))
        except IOError as e:
            logger.error(f"Error saving index.json: {e}")

    async def _save_cache(self) -> None:
        try:
            async with aiofiles.open(self.cache_file, mode='w', encoding='utf-8') as f:
                await f.write(json.dumps(self.image_cache, indent=2, ensure_ascii=False))
        except IOError as e:
            logger.error(f"Error saving image cache: {e}")

    async def save(
        self,
        data: ScrapedData,
        original_url: str,
        search_terms: Optional[str] = None,
        research_questions: Optional[str] = None,
    ) -> Optional[str]:
        """Save scraped data, search terms, and research questions to a JSON file."""
        sid = data.main_post.status_id
        if not sid:
            first_reply_sid = next((r.status_id for r in data.replies if r.status_id), None)
            if first_reply_sid:
                sid = first_reply_sid
                logger.warning(f"Main post missing ID, using first reply ID: {sid}")
            else:
                logger.error("No status ID found in main post or replies. Skipping save.")
                return None

        if sid in self.seen:
            logger.info(f"Post {sid} already saved. Skipping.")
            return None

        meta = {
            'original_url': original_url,
            'author': data.main_post.username,
            'scrape_date': datetime.now(timezone.utc).isoformat(),
            'replies_count': len(data.replies)
        }
        self.index['posts'][sid] = meta
        self.index['latest_scrape'] = meta['scrape_date']
        await self._save_index()

        post_file = self.data_dir / f'post_{sid}.json'
        final_output = {
            'main_post': data.main_post.to_dict(),
            'replies': [r.to_dict() for r in data.replies],
            'suggested_search_terms': search_terms,
            'research_questions': research_questions
        }
        try:
            post_json = json.dumps(final_output, indent=2, ensure_ascii=False)
            async with aiofiles.open(post_file, mode='w', encoding='utf-8') as f:
                await f.write(post_json)
            self.seen.add(sid)
            logger.info(f"Saved post {sid} to {post_file}")
            return sid
        except (IOError, TypeError) as e:
            logger.error(f"Error saving post {post_file}: {e}")
            if sid in self.index['posts']:
                del self.index['posts'][sid]
                await self._save_index()
            return None

    async def load_post_data(self, status_id: str) -> Optional[ScrapedData]:
        """Load the scraped data (main_post, replies) from a saved JSON post file."""
        post_file = self.data_dir / f'post_{status_id}.json'
        if not post_file.exists():
            logger.warning(f"Post file not found for ID: {status_id}")
            return None
        try:
            async with aiofiles.open(post_file, mode='r', encoding='utf-8') as f:
                full_content = json.loads(await f.read())
            main_post_dict = full_content.get('main_post')
            replies_list_dict = full_content.get('replies', [])
            if not main_post_dict:
                logger.error(f"Main post data missing in file {post_file}")
                return None
            main_post = Post(**main_post_dict)
            main_post.images = [
                Image(**img_dict) for img_dict in main_post_dict.get('images', []) if isinstance(img_dict, dict)
            ]
            replies: List[Post] = []
            for reply_dict in replies_list_dict:
                if isinstance(reply_dict, dict):
                    reply = Post(**reply_dict)
                    reply.images = [
                        Image(**img_dict) for img_dict in reply_dict.get('images', []) if isinstance(img_dict, dict)
                    ]
                    replies.append(reply)
                else:
                    logger.warning(f"Skipping malformed reply data in file {post_file}")
            logger.info(f"Loaded scraped data for ID: {status_id}")
            return ScrapedData(main_post=main_post, replies=replies)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading/decoding {post_file}: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error reconstructing data for {post_file}: {e}")
            return None

    def list_meta(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """List saved post metadata, sorted by scrape date (descending)."""
        posts = [{'status_id': sid, **meta} for sid, meta in self.index.get('posts', {}).items()]
        posts.sort(key=lambda x: x.get('scrape_date', ''), reverse=True)
        return posts[:limit] if limit else posts

    def count(self) -> int:
        """Return total number of saved posts."""
        return len(self.index.get('posts', {}))

    async def delete(self, status_id: str) -> bool:
        """Delete a saved post by status ID."""
        if status_id not in self.index.get('posts', {}):
            logger.warning(f"Post {status_id} not found.")
            return False
        post_file = self.data_dir / f"post_{status_id}.json"
        if post_file.exists():
            try:
                post_file.unlink()
                logger.info(f"Deleted file {post_file}")
            except IOError as e:
                logger.error(f"Error deleting file {post_file}: {e}")
        self.index['posts'].pop(status_id, None)
        self.seen.discard(status_id)
        await self._save_index()
        logger.info(f"Removed post {status_id} from index.")
        return True
