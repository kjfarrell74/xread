"""Data management functionality for saving and loading scraped data in xread."""

import json
import sqlite3  # Added for database operations
from pathlib import Path
from typing import Optional, Dict, List, Set, Any
import aiofiles
from datetime import datetime, timezone

from xread.settings import settings, logger
from xread.models import ScrapedData, Post, Image

class DataManager:
    """Handles saving and loading scraped data to/from the database."""
    def __init__(self):
        self.data_dir = settings.data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / 'xread_data.db'  # Define DB path
        self.conn: Optional[sqlite3.Connection] = None
        self.image_cache: Dict[str, str] = {}  # Keep for in-memory, but DB is source
        self.seen: Set[str] = set()

    async def initialize(self) -> None:
        """Initialize the data manager by connecting to DB and creating tables."""
        self.conn = self._connect_db()
        self._initialize_db()
        await self._load_seen_ids()
        await self._load_cache()  # Load cache from DB into memory

    def _connect_db(self) -> sqlite3.Connection:
        """Establish SQLite connection."""
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)  # check_same_thread=False needed for async usage
            conn.row_factory = sqlite3.Row  # Access columns by name
            logger.info(f"Connected to SQLite database: {self.db_path}")
            return conn
        except sqlite3.Error as e:
            logger.error(f"Error connecting to SQLite database: {e}")
            raise  # Propagate error

    def _initialize_db(self) -> None:
        """Create database tables if they don't exist."""
        if not self.conn:
            raise ConnectionError("Database not connected.")
        cursor = self.conn.cursor()
        try:
            # Main posts table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS posts (
                    status_id TEXT PRIMARY KEY,
                    author TEXT,
                    username TEXT,
                    text TEXT,
                    date TEXT,
                    permalink TEXT UNIQUE,
                    images_json TEXT,
                    original_url TEXT,
                    scrape_date TEXT,
                    suggested_search_terms TEXT,
                    research_questions TEXT
                )
            ''')

            # Replies table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS replies (
                    reply_db_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_status_id TEXT NOT NULL,
                    status_id TEXT UNIQUE,
                    user TEXT,
                    username TEXT,
                    text TEXT,
                    date TEXT,
                    permalink TEXT UNIQUE,
                    images_json TEXT,
                    FOREIGN KEY (post_status_id) REFERENCES posts (status_id) ON DELETE CASCADE
                )
            ''')

            # Image cache table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS image_cache (
                    url_hash TEXT PRIMARY KEY,
                    description TEXT,
                    cached_at TEXT
                )
            ''')
            self.conn.commit()
            logger.info("Database tables ensured.")
        except sqlite3.Error as e:
            logger.error(f"Error initializing database tables: {e}")
            self.conn.rollback()
        finally:
            cursor.close()

    async def _load_index(self) -> None:
        if self.index_file.exists():
            try:
                async with aiofiles.open(self.index_file, mode='r', encoding='utf-8') as f:
                    self.index = json.loads(await f.read())
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading index.json: {e}. Resetting index.")
                self.index = {'posts': {}, 'latest_scrape': None}
        self.seen = set(self.index.get('posts', {}).keys())

    async def _load_seen_ids(self) -> None:
        """Load already processed post IDs from the database."""
        if not self.conn: return
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT status_id FROM posts")
            rows = cursor.fetchall()
            self.seen = {row['status_id'] for row in rows}
            logger.info(f"Loaded {len(self.seen)} seen post IDs from database.")
        except sqlite3.Error as e:
            logger.error(f"Error loading seen IDs from database: {e}")
        finally:
            cursor.close()

    async def _load_cache(self) -> None:
        """Load image description cache from the database."""
        if not self.conn: return
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT url_hash, description FROM image_cache")
            rows = cursor.fetchall()
            self.image_cache = {row['url_hash']: row['description'] for row in rows}
            logger.info(f"Loaded {len(self.image_cache)} items into image cache from database.")
        except sqlite3.Error as e:
            logger.error(f"Error loading image cache from database: {e}")
        finally:
            cursor.close()

    # Removed _save_index as it's no longer needed with DB storage

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
        """Save scraped data to the database."""
        if not self.conn:
            logger.error("Database not connected. Cannot save.")
            return None

        sid = data.main_post.status_id
        if not sid:
            first_reply_sid = next((r.status_id for r in data.replies if r.status_id), None)
            if first_reply_sid:
                sid = first_reply_sid
                logger.warning(f"Main post missing ID, using first reply ID: {sid}")
            else:
                logger.error("No status ID found. Skipping save.")
                return None

        if sid in self.seen:
            logger.info(f"Post {sid} already saved. Skipping.")
            return None

        cursor = self.conn.cursor()
        try:
            scrape_date = datetime.now(timezone.utc).isoformat()
            images_json = json.dumps([img.__dict__ for img in data.main_post.images])
            cursor.execute(
                "INSERT INTO posts (status_id, author, username, text, date, permalink, images_json, original_url, scrape_date, suggested_search_terms, research_questions) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (sid, data.main_post.user, data.main_post.username, data.main_post.text, data.main_post.date,
                 data.main_post.permalink, images_json, original_url, scrape_date, search_terms, research_questions)
            )

            for reply in data.replies:
                reply_images_json = json.dumps([img.__dict__ for img in reply.images])
                cursor.execute(
                    "INSERT INTO replies (post_status_id, status_id, user, username, text, date, permalink, images_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (sid, reply.status_id, reply.user, reply.username, reply.text, reply.date,
                     reply.permalink, reply_images_json)
                )

            self.conn.commit()
            self.seen.add(sid)
            logger.info(f"Saved post {sid} to database.")
            return sid
        except sqlite3.IntegrityError as e:
            logger.warning(f"Integrity error saving post {sid}: {e}")
            self.conn.rollback()
            return None
        except sqlite3.Error as e:
            logger.error(f"Error saving post {sid} to database: {e}")
            self.conn.rollback()
            return None

    async def load_post_data(self, status_id: str) -> Optional[ScrapedData]:
        """Load scraped data from the database for a given status_id."""
        if not self.conn:
            logger.error("Database not connected. Cannot load data.")
            return None
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT * FROM posts WHERE status_id = ?", (status_id,))
            main_post_row = cursor.fetchone()
            if not main_post_row:
                logger.warning(f"Post not found in database for ID: {status_id}")
                return None

            main_post_images = [Image(**img_dict) for img_dict in json.loads(main_post_row['images_json'] or '[]')]
            main_post = Post(
                status_id=main_post_row['status_id'],
                user=main_post_row['user'],
                username=main_post_row['username'],
                text=main_post_row['text'],
                date=main_post_row['date'],
                permalink=main_post_row['permalink'],
                images=main_post_images
            )

            cursor.execute("SELECT * FROM replies WHERE post_status_id = ?", (status_id,))
            reply_rows = cursor.fetchall()
            replies: List[Post] = []
            for reply_row in reply_rows:
                reply_images = [Image(**img_dict) for img_dict in json.loads(reply_row['images_json'] or '[]')]
                reply = Post(
                    status_id=reply_row['status_id'],
                    user=reply_row['user'],
                    username=reply_row['username'],
                    text=reply_row['text'],
                    date=reply_row['date'],
                    permalink=reply_row['permalink'],
                    images=reply_images
                )
                replies.append(reply)

            logger.info(f"Loaded scraped data from DB for ID: {status_id}")
            return ScrapedData(main_post=main_post, replies=replies)
        except sqlite3.Error as e:
            logger.error(f"Error loading post {status_id} from database: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON for post {status_id} from database: {e}")
            return None
        finally:
            cursor.close()

    def list_meta(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """List saved post metadata, sorted by scrape date (descending)."""
        if not self.conn:
            logger.warning("Database connection not available. Attempting to reconnect.")
            self.conn = self._connect_db()
            if not self.conn:
                logger.error("Failed to reconnect to database. Cannot list metadata.")
                return []
        cursor = self.conn.cursor()
        try:
            query = "SELECT status_id, author, username, text, date, permalink, scrape_date FROM posts ORDER BY scrape_date DESC"
            if limit is not None:
                query += f" LIMIT {limit}"
            cursor.execute(query)
            rows = cursor.fetchall()
            posts = [
                {
                    'status_id': row['status_id'],
                    'author': row['author'],
                    'username': row['username'],
                    'text': row['text'],
                    'date': row['date'],
                    'permalink': row['permalink'],
                    'scrape_date': row['scrape_date']
                }
                for row in rows
            ]
            logger.info(f"Listed {len(posts)} posts from database.")
            return posts
        except sqlite3.Error as e:
            logger.error(f"Error listing posts from database: {e}")
            return []
        finally:
            cursor.close()

    def count(self) -> int:
        """Return total number of saved posts."""
        if not self.conn:
            logger.warning("Database connection not available. Attempting to reconnect.")
            self.conn = self._connect_db()
            if not self.conn:
                logger.error("Failed to reconnect to database. Cannot count posts.")
                return 0
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) as count FROM posts")
            row = cursor.fetchone()
            count = row['count'] if row else 0
            logger.info(f"Counted {count} posts in database.")
            return count
        except sqlite3.Error as e:
            logger.error(f"Error counting posts in database: {e}")
            return 0
        finally:
            cursor.close()

    async def delete(self, status_id: str) -> bool:
        """Delete a saved post by status ID."""
        if not self.conn:
            logger.warning("Database connection not available. Attempting to reconnect.")
            self.conn = self._connect_db()
            if not self.conn:
                logger.error("Failed to reconnect to database. Cannot delete post.")
                return False
        if status_id not in self.seen:
            logger.warning(f"Post {status_id} not found.")
            return False
        cursor = self.conn.cursor()
        try:
            cursor.execute("DELETE FROM posts WHERE status_id = ?", (status_id,))
            self.conn.commit()
            self.seen.discard(status_id)
            logger.info(f"Deleted post {status_id} from database.")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error deleting post {status_id} from database: {e}")
            self.conn.rollback()
            return False
        finally:
            cursor.close()
