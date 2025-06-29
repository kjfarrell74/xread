"""Data management functionality for saving and loading scraped data in xread."""

import json
import os
from pathlib import Path
from typing import Optional, Dict, List, Set, Any
from datetime import datetime, timezone

import aiosqlite  # Using async SQLite for database operations
import aiofiles

from xread.core.async_file import write_json_async
from xread.settings import settings, logger
from xread.models import ScrapedData, Post, Image, AuthorNote, UserProfile
from xread.security_patches import SecurityValidator, SecureDataManager as SecureBaseDataManager
from xread.exceptions import DatabaseError, ValidationError, InvalidStatusIDError

class AsyncDataManager(SecureBaseDataManager):
    """Handles saving and loading scraped data to/from the database asynchronously with security features."""
    def __init__(self):
        super().__init__(data_dir=settings.data_dir)
        self.data_dir = settings.data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o750)  # Secure permissions
        self.db_path = self.data_dir / 'xread_data.db'
        self.conn: Optional[aiosqlite.Connection] = None
        self.image_cache: Dict[str, str] = {}
        self.seen: Set[str] = set()
        self._closed = False

    async def initialize(self) -> None:
        """Initialize the data manager by connecting to DB and creating tables with secure settings."""
        if self._closed:
            logger.warning("Attempting to initialize a closed data manager. Reopening connection.")
            self._closed = False
        self.conn = await self._connect_db()
        await self._initialize_db()
        await self._load_seen_ids()
        await self._load_cache()
        self._ensure_secure_db()

    async def _connect_db(self) -> aiosqlite.Connection:
        """Establish async SQLite connection with security settings."""
        try:
            conn = await aiosqlite.connect(self.db_path)
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA foreign_keys = ON")
            await conn.execute("PRAGMA journal_mode = WAL")
            await conn.execute("PRAGMA synchronous = NORMAL")
            logger.info(f"Connected to SQLite database: {self.db_path}")
            return conn
        except aiosqlite.Error as e:
            logger.error(f"Error connecting to SQLite database: {e}")
            raise

    async def _initialize_db(self) -> None:
        """Create database tables if they don't exist and perform migrations with secure permissions."""
        if not self.conn:
            raise ConnectionError("Database not connected.")
        await self._create_tables_and_migrate()
        os.chmod(self.db_path, 0o640)  # rw-r-----

    async def _create_tables_and_migrate(self) -> None:
        """Extracted: Create all tables and perform schema migrations."""
        cursor = await self.conn.cursor()
        try:
            # Main posts table
            await cursor.execute('''
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
                    research_questions TEXT,
                    perplexity_report TEXT
                )
            ''')

            # Check and add new columns to posts table if they don't exist
            await cursor.execute("PRAGMA table_info(posts)")
            columns = [column[1] for column in await cursor.fetchall()]

            new_columns = {
                'likes': 'INTEGER DEFAULT 0',
                'retweets': 'INTEGER DEFAULT 0',
                'replies_count': 'INTEGER DEFAULT 0',
                'topic_tags': 'TEXT', # Stored as JSON string
                'factual_context': 'TEXT',
                'source': 'TEXT',
                'ai_report': 'TEXT',
                'author_note': 'TEXT'
            }

            for col_name, col_type in new_columns.items():
                if col_name not in columns:
                    try:
                        await cursor.execute(f"ALTER TABLE posts ADD COLUMN {col_name} {col_type}")
                        logger.info(f"Added column '{col_name}' to 'posts' table.")
                    except aiosqlite.Error as e:
                        logger.error(f"Error adding column '{col_name}' to 'posts' table: {e}")

            # Replies table
            await cursor.execute('''
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

            # Check and add new columns to replies table if they don't exist
            await cursor.execute("PRAGMA table_info(replies)")
            reply_columns = [column[1] for column in await cursor.fetchall()]

            if 'text' not in reply_columns:
                try:
                    await cursor.execute("ALTER TABLE replies ADD COLUMN text TEXT")
                    logger.info("Added column 'text' to 'replies' table.")
                except aiosqlite.Error as e:
                    logger.error(f"Error adding column 'text' to 'replies' table: {e}")

            # Image cache table
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS image_cache (
                    url_hash TEXT PRIMARY KEY,
                    description TEXT,
                    cached_at TEXT
                )
            ''')

            # User profiles table
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_profiles (
                    username TEXT PRIMARY KEY,
                    display_name TEXT,
                    bio TEXT,
                    location TEXT,
                    website TEXT,
                    profile_image_url TEXT,
                    followers_count INTEGER,
                    following_count INTEGER,
                    join_date TEXT
                )
            ''')

            # Author notes table
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS author_notes (
                    username TEXT PRIMARY KEY,
                    note_content TEXT
                )
            ''')

            await self.conn.commit()
            logger.info("Database tables and schema migrations ensured.")
        except aiosqlite.Error as e:
            logger.error(f"Error initializing database tables or performing migrations: {e}")
            await self.conn.rollback()
        finally:
            await cursor.close()

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
        cursor = await self.conn.cursor()
        try:
            await cursor.execute("SELECT status_id FROM posts")
            rows = await cursor.fetchall()
            self.seen = {row['status_id'] for row in rows}
            logger.info(f"Loaded {len(self.seen)} seen post IDs from database.")
        except aiosqlite.Error as e:
            logger.error(f"Error loading seen IDs from database: {e}")
        finally:
            await cursor.close()

    async def _load_cache(self) -> None:
        """Load image description cache from the database."""
        if not self.conn: return
        cursor = await self.conn.cursor()
        try:
            await cursor.execute("SELECT url_hash, description FROM image_cache")
            rows = await cursor.fetchall()
            self.image_cache = {row['url_hash']: row['description'] for row in rows}
            logger.info(f"Loaded {len(self.image_cache)} items into image cache from database.")
        except aiosqlite.Error as e:
            logger.error(f"Error loading image cache from database: {e}")
        finally:
            await cursor.close()

    # Removed _save_index as it's no longer needed with DB storage

    async def get_user_profile(self, username: str) -> Optional['UserProfile']:
        """Fetch a user profile from the database by username."""
        if not self.conn:
            logger.error("Database not connected. Cannot fetch user profile.")
            return None
        cursor = await self.conn.cursor()
        try:
            await cursor.execute(
                "SELECT * FROM user_profiles WHERE username = ?",
                (username,)
            )
            row = await cursor.fetchone()
            if row:
                from xread.models import UserProfile  # Local import to avoid circular import
                return UserProfile(
                    username=row["username"],
                    display_name=row["display_name"],
                    bio=row["bio"],
                    location=row["location"],
                    website=row["website"],
                    profile_image_url=row["profile_image_url"],
                    followers_count=row["followers_count"],
                    following_count=row["following_count"],
                    join_date=row["join_date"]
                )
            else:
                return None
        except Exception as e:
            logger.error(f"Error fetching user profile for {username}: {e}")
            return None
        finally:
            await cursor.close()

    def _ensure_scalar(self, value):
        if isinstance(value, (list, dict)):
            return json.dumps(value)
        return value

    async def save(
        self,
        data: ScrapedData,
        original_url: str,
        ai_report: Optional[str] = None,
        author_profile: Optional['UserProfile'] = None,
        author_note: Optional['AuthorNote'] = None
    ) -> Optional[str]:
        """Save scraped data to the database and as JSON files with security validations."""
        if not self.conn:
            raise DatabaseError("Database not connected. Cannot save data.")

        sid = self._extract_and_validate_sid(data)
        if not sid:
            return None
            
        if sid in self.seen:
            logger.info(f"Post {sid} already saved. Skipping.")
            return None

        clean_sid = SecurityValidator.sanitize_filename(sid)
        cursor = await self.conn.cursor()
        try:
            scrape_date = datetime.now(timezone.utc).isoformat()
            images_json = json.dumps([img.__dict__ for img in data.main_post.images])

            topic_tags_serialized = self._serialize_topic_tags(data.main_post.topic_tags, sid)

            logger.debug(f"Saving post {sid} with topic_tags type: {type(data.main_post.topic_tags)} and value: {data.main_post.topic_tags}")

            await self._insert_main_post(
                cursor, clean_sid, data, original_url, scrape_date, 
                ai_report, images_json, topic_tags_serialized
            )

            await self._insert_replies(cursor, clean_sid, data.replies)

            await self.conn.commit()
            self.seen.add(sid)
            logger.info(f"Saved post {sid} to database.")
            
            # Also save to JSON file with secure permissions
            json_data = self._serialize_to_json(
                data, original_url, scrape_date, ai_report, author_profile, author_note
            )
            logger.info(f"save: json_data = {json.dumps(json_data, indent=2, ensure_ascii=False)}")
            json_file_path = self.data_dir / 'scraped_data' / f'post_{clean_sid}.json'
            json_file_path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
            await write_json_async(json_file_path, json_data)
            os.chmod(json_file_path, 0o640)  # rw-r-----
            logger.info(f"Saved post {sid} to JSON file at {json_file_path}.")
            
            return sid
        except aiosqlite.IntegrityError as e:
            logger.warning(f"Integrity error saving post {sid}: {e}")
            await self.conn.rollback()
            raise DatabaseError(f"Integrity constraint violation for post {sid}: {e}")
        except aiosqlite.Error as e:
            logger.error(f"Database error saving post {sid}: {e}")
            await self.conn.rollback()
            raise DatabaseError(f"Database operation failed for post {sid}: {e}")
        except IOError as e:
            logger.error(f"File I/O error saving post {sid}: {e}")
            # Return sid since database save was successful, only JSON file failed
            return sid

    def _extract_and_validate_sid(self, data: ScrapedData) -> Optional[str]:
        """Extract and validate status ID from scraped data."""
        sid = data.main_post.status_id
        if not sid:
            first_reply_sid = next((r.status_id for r in data.replies if r.status_id), None)
            if first_reply_sid:
                sid = first_reply_sid
                logger.warning(f"Main post missing ID, using first reply ID: {sid}")
            else:
                raise ValidationError("No status ID found in scraped data")

        # Validate status ID
        if not SecurityValidator.validate_status_id(sid):
            raise InvalidStatusIDError(f"Invalid status ID format: {sid}")
            
        return sid
    
    def _serialize_topic_tags(self, topic_tags_value: Any, sid: str) -> str:
        """Serialize topic tags with defensive handling."""
        try:
            if isinstance(topic_tags_value, str):
                try:
                    loaded = json.loads(topic_tags_value)
                    return json.dumps(loaded)
                except Exception:
                    return json.dumps([topic_tags_value])
            else:
                return json.dumps(topic_tags_value if topic_tags_value is not None else [])
        except Exception as e:
            logger.error(f"Error serializing topic_tags for post {sid}: {e}. Defaulting to empty list.")
            return json.dumps([])
    
    async def _insert_main_post(
        self, 
        cursor: aiosqlite.Cursor, 
        clean_sid: str, 
        data: ScrapedData, 
        original_url: str, 
        scrape_date: str, 
        ai_report: Optional[str], 
        images_json: str, 
        topic_tags_serialized: str
    ) -> None:
        """Insert main post into database."""
        await cursor.execute(
            """
            INSERT INTO posts (
                status_id, author, username, text, date, permalink, images_json, 
                original_url, scrape_date, ai_report, likes, retweets, 
                replies_count, topic_tags, factual_context, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                clean_sid,
                data.main_post.user,
                data.main_post.username,
                data.main_post.text,
                data.main_post.date,
                data.main_post.permalink,
                images_json,
                original_url,
                scrape_date,
                self._ensure_scalar(ai_report),
                data.main_post.likes,
                data.main_post.retweets,
                data.main_post.replies_count,
                self._ensure_scalar(topic_tags_serialized),
                self._ensure_scalar(data.factual_context),
                self._ensure_scalar(data.source)
            )
        )
    
    async def _insert_replies(self, cursor: aiosqlite.Cursor, clean_sid: str, replies: List[Post]) -> None:
        """Insert replies into database."""
        for reply in replies:
            reply_images_json = json.dumps([img.__dict__ for img in reply.images])
            await cursor.execute("SELECT reply_db_id FROM replies WHERE permalink = ?", (reply.permalink,))
            if await cursor.fetchone():
                logger.info(f"Reply with permalink {reply.permalink} already exists. Skipping insertion.")
                continue
            reply_sid = SecurityValidator.sanitize_filename(reply.status_id) if reply.status_id else ""
            await cursor.execute(
                "INSERT INTO replies (post_status_id, status_id, user, username, text, date, permalink, images_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (clean_sid, reply_sid, reply.user, reply.username, reply.text, reply.date,
                 reply.permalink, reply_images_json)
            )

    def _serialize_to_json(
        self,
        data: ScrapedData,
        original_url: str,
        scrape_date: str,
        ai_report: Optional[str],
        author_profile: Optional['UserProfile'],
        author_note: Optional['AuthorNote']
    ) -> dict:
        """Extracted: Serialize scraped data and metadata to a JSON-serializable dict."""
        main_post_dict = data.main_post.__dict__.copy()
        main_post_dict['images'] = [img.__dict__ for img in data.main_post.images]
        replies_dicts = []
        for reply in data.replies:
            reply_dict = reply.__dict__.copy()
            reply_dict['images'] = [img.__dict__ for img in reply.images]
            replies_dicts.append(reply_dict)
        return {
            "main_post": main_post_dict,
            "replies": replies_dicts,
            "original_url": original_url,
            "scrape_date": scrape_date,
            "ai_report": ai_report,
            "author_profile": author_profile.to_dict() if author_profile else None,
            "author_note": author_note.note_content if author_note else None,
            "factual_context": data.factual_context,
            "source": data.source
        }

    async def delete(self, status_id: str) -> bool:
        """Delete a saved post by status ID from the database and file system."""
        if not self.conn:
            logger.error("Database not connected. Cannot delete post.")
            return False
        
        cursor = await self.conn.cursor()
        try:
            # Delete the post from the database (replies will be deleted automatically due to CASCADE)
            await cursor.execute("DELETE FROM posts WHERE status_id = ?", (status_id,))
            if cursor.rowcount > 0:
                await self.conn.commit()
                self.seen.discard(status_id)
                logger.info(f"Deleted post {status_id} from database.")
                
                # Attempt to delete the corresponding JSON file
                json_file_path = self.data_dir / 'scraped_data' / f'post_{status_id}.json'
                if json_file_path.exists():
                    try:
                        json_file_path.unlink()
                        logger.info(f"Deleted JSON file for post {status_id} at {json_file_path}.")
                    except Exception as e:
                        logger.error(f"Error deleting JSON file for post {status_id}: {e}")
                return True
            else:
                await self.conn.rollback()
                logger.warning(f"Post {status_id} not found in database.")
                return False
        except aiosqlite.Error as e:
            logger.error(f"Error deleting post {status_id} from database: {e}")
            await self.conn.rollback()
            return False
        finally:
            await cursor.close()

    async def list_meta(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """List metadata of saved posts, optionally limited to a number."""
        if not self.conn:
            logger.error("Database not connected. Cannot list posts.")
            return []
        
        cursor = await self.conn.cursor()
        try:
            query = "SELECT status_id, author, scrape_date FROM posts ORDER BY scrape_date DESC"
            if limit is not None:
                query += f" LIMIT {limit}"
            await cursor.execute(query)
            rows = await cursor.fetchall()
            return [{"status_id": row["status_id"], "author": row["author"], "scrape_date": row["scrape_date"]} for row in rows]
        except aiosqlite.Error as e:
            logger.error(f"Error listing posts: {e}")
            return []
        finally:
            await cursor.close()

    async def delete_all(self) -> bool:
        """Delete all saved posts from the database and corresponding JSON files from the file system."""
        if not self.conn:
            logger.error("Database not connected. Cannot delete all posts.")
            return False
        
        cursor = await self.conn.cursor()
        try:
            # Delete all posts from the database (replies will be deleted automatically due to CASCADE)
            await cursor.execute("DELETE FROM posts")
            deleted_count = cursor.rowcount
            await self.conn.commit()
            self.seen.clear()
            logger.info(f"Deleted {deleted_count} posts from database.")
            
            # Attempt to delete all JSON files in the scraped_data directory
            scraped_data_dir = self.data_dir / 'scraped_data'
            if scraped_data_dir.exists():
                for json_file in scraped_data_dir.glob('post_*.json'):
                    try:
                        json_file.unlink()
                        logger.info(f"Deleted JSON file at {json_file}.")
                    except Exception as e:
                        logger.error(f"Error deleting JSON file at {json_file}: {e}")
            return True
        except aiosqlite.Error as e:
            logger.error(f"Error deleting all posts from database: {e}")
            await self.conn.rollback()
            return False
        finally:
            await cursor.close()

    async def save_author_note(self, author_note: 'AuthorNote') -> bool:
        """Save or update an author note in the database."""
        if not self.conn:
            logger.error("Database not connected. Cannot save author note.")
            return False
        
        cursor = await self.conn.cursor()
        try:
            await cursor.execute(
                """
                INSERT OR REPLACE INTO author_notes (username, note_content)
                VALUES (?, ?)
                """,
                (author_note.username, author_note.note_content)
            )
            await self.conn.commit()
            logger.info(f"Saving author note for {author_note.username}: {author_note.note_content}")
            return True
        except aiosqlite.Error as e:
            logger.error(f"Error saving author note for {author_note.username}: {author_note.note_content} {e}")
            await self.conn.rollback()
            return False
        finally:
            await cursor.close()

    async def get_author_note(self, username: str) -> Optional['AuthorNote']:
        """Retrieve an author note from the database by username."""
        if not self.conn:
            logger.error("Database not connected. Cannot fetch author note.")
            return None
        
        cursor = await self.conn.cursor()
        try:
            await cursor.execute(
                "SELECT * FROM author_notes WHERE username = ?",
                (username,)
            )
            row = await cursor.fetchone()
            if row:
                logger.info(f"get_author_note: Author note found for {username}: {row['note_content']}")
                from xread.models import AuthorNote  # Local import to avoid circular import
                return AuthorNote(
                    username=row["username"],
                    note_content=row["note_content"]
                )
            else:
                logger.info(f"get_author_note: No author note found for {username}")
                return None
        except aiosqlite.Error as e:
            logger.error(f"Error fetching author note for {username}: {e}")
            return None
        finally:
            await cursor.close()

    async def add_author_note(self, post_id: str, note: 'AuthorNote') -> bool:
        """Add an author note to a specific post by updating the posts table."""
        if not self.conn:
            logger.error("Database not connected. Cannot add author note.")
            return False
        
        cursor = await self.conn.cursor()
        try:
            # Update the author_note field for the specific post
            await cursor.execute(
                "UPDATE posts SET author_note = ? WHERE status_id = ?",
                (note.note_content, post_id)
            )
            if cursor.rowcount > 0:
                await self.conn.commit()
                logger.info(f"Added author note to post {post_id}: {note.note_content}")
                return True
            else:
                logger.warning(f"Post {post_id} not found. Cannot add author note.")
                return False
        except aiosqlite.Error as e:
            logger.error(f"Error adding author note to post {post_id}: {e}")
            await self.conn.rollback()
            return False
        finally:
            await cursor.close()
    
    async def add_general_author_note(self, username: str, note_content: str) -> bool:
        """Add or update a general note about an author."""
        from xread.models import AuthorNote
        note = AuthorNote(username=username, note_content=note_content)
        return await self.save_author_note(note)
            
    async def close(self) -> None:
        """Close the database connection and clean up resources."""
        if self._closed:
            logger.debug("Data manager already closed.")
            return
            
        if self.conn:
            try:
                logger.info("Closing database connection...")
                await self.conn.close()
                logger.info("Database connection closed.")
            except Exception as e:
                logger.error(f"Error closing database connection: {e}")
            finally:
                self.conn = None
                self._closed = True

    async def get_full_post_data(self, post_id: str) -> Optional[Dict[str, Any]]:
        """Get full post data by ID from database, including replies and parsed JSON fields."""
        if not self.conn:
            logger.error("Database not connected.")
            return None
        
        cursor = await self.conn.cursor()
        try:
            # Get main post
            await cursor.execute("""
                SELECT status_id, author, username, text, date, permalink, 
                       images_json, original_url, scrape_date, ai_report,
                       likes, retweets, replies_count, topic_tags, factual_context, source,
                       suggested_search_terms, research_questions, perplexity_report, author_note
                FROM posts WHERE status_id = ?
            """, (post_id,))
            
            post_row = await cursor.fetchone()
            if not post_row:
                return None
            
            post_data = dict(post_row)
            
            # Parse JSON fields
            for key in ['images_json', 'topic_tags']:
                if post_data.get(key):
                    try:
                        post_data[key.replace('_json', '')] = json.loads(post_data[key])
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to decode JSON for {key} for post {post_id}. Setting to empty.")
                        post_data[key.replace('_json', '')] = []
                else:
                    post_data[key.replace('_json', '')] = []
            
            # Ensure AI reports are treated as strings
            if 'ai_report' in post_data and post_data['ai_report'] is not None:
                if isinstance(post_data['ai_report'], (list, dict)):
                    post_data['ai_report'] = json.dumps(post_data['ai_report'])
                post_data['ai_report'] = str(post_data['ai_report'])
            else:
                post_data['ai_report'] = "" # Default to empty string if None

            # Handle factual_context and source as potentially lists/strings
            if 'factual_context' in post_data and post_data['factual_context'] is not None:
                try:
                    # Attempt to load as JSON list, fallback to single string
                    post_data['factual_context'] = json.loads(post_data['factual_context'])
                except (json.JSONDecodeError, TypeError):
                    post_data['factual_context'] = [post_data['factual_context']]
            else:
                post_data['factual_context'] = []

            if 'source' in post_data and post_data['source'] is not None and isinstance(post_data['source'], str):
                pass # Already a string
            else:
                post_data['source'] = "" # Default to empty string if None or not string


            # Get replies
            await cursor.execute("""
                SELECT reply_db_id, post_status_id, status_id, user, username, text, date, permalink, images_json
                FROM replies WHERE post_status_id = ?
                ORDER BY date ASC
            """, (post_id,))
            
            reply_rows = await cursor.fetchall()
            replies = []
            for reply_row in reply_rows:
                reply_data = dict(reply_row)
                if reply_data.get('images_json'):
                    try:
                        reply_data['images'] = json.loads(reply_data['images_json'])
                    except json.JSONDecodeError:
                        reply_data['images'] = []
                else:
                    reply_data['images'] = []
                replies.append(reply_data)
            
            post_data['replies'] = replies

            # Clean up the original json string fields
            post_data.pop('images_json', None)
            post_data.pop('topic_tags', None) # Pop original topic_tags if needed, as it's now 'topic_tags'
            post_data.pop('suggested_search_terms', None)
            post_data.pop('research_questions', None)
            post_data.pop('perplexity_report', None) # perplexity_report is aliased to ai_report

            # Re-map main_post to 'main_post' key for compatibility with ScrapedData object creation later
            # (assuming this method might be used to reconstruct a ScrapedData object)
            main_post_reformatted = {
                'status_id': post_data.get('status_id'),
                'user': post_data.get('author'),
                'username': post_data.get('username'),
                'text': post_data.get('text'),
                'date': post_data.get('date'),
                'permalink': post_data.get('permalink'),
                'images': post_data.get('images', []),
                'likes': post_data.get('likes', 0),
                'retweets': post_data.get('retweets', 0),
                'replies_count': post_data.get('replies_count', 0),
                'topic_tags': post_data.get('topic_tags', [])
            }
            
            return {
                'main_post': main_post_reformatted,
                'replies': replies,
                'factual_context': post_data.get('factual_context'),
                'source': post_data.get('source'),
                'ai_report': post_data.get('ai_report'),
                'scrape_date': post_data.get('scrape_date'),
                'original_url': post_data.get('original_url'),
                'author_note': post_data.get('author_note')
            }
            
        except Exception as e:
            logger.error(f"Error getting post {post_id} from DB: {e}")
            return None
        finally:
            await cursor.close()
    
    async def search_posts(self, query: str, author: Optional[str] = None, limit: int = 10, include_ai_reports: bool = False) -> List[Dict[str, Any]]:
        """Search posts in database by content and/or author."""
        if not self.conn:
            logger.error("Database not connected.")
            return []
        
        cursor = await self.conn.cursor()
        try:
            select_cols = "status_id, author, username, text, date, permalink"
            if include_ai_reports:
                select_cols += ", ai_report"

            sql = f"""
                SELECT {select_cols}
                FROM posts 
                WHERE text LIKE ? 
            """
            params = [f"%{query}%"]
            
            if author:
                sql += " AND username LIKE ?"
                params.append(f"%{author}%")
            
            sql += " ORDER BY scrape_date DESC LIMIT ?"
            params.append(limit)
            
            await cursor.execute(sql, params)
            rows = await cursor.fetchall()
            
            results = []
            for row in rows:
                post_data = dict(row)
                if 'ai_report' in post_data and post_data['ai_report'] is not None:
                    if isinstance(post_data['ai_report'], (list, dict)): # Ensure it's a string
                         post_data['ai_report'] = json.dumps(post_data['ai_report'])
                else:
                    post_data['ai_report'] = "" # Default to empty string
                results.append(post_data)
            return results
            
        except Exception as e:
            logger.error(f"Error searching posts in DB: {e}")
            return []
        finally:
            await cursor.close()
    
    async def get_recent_posts(self, limit: int = 20, include_ai_reports: bool = False) -> List[Dict[str, Any]]:
        """Get recent posts from database."""
        if not self.conn:
            logger.error("Database not connected.")
            return []
        
        cursor = await self.conn.cursor()
        try:
            select_cols = "status_id, author, username, text, date, permalink"
            if include_ai_reports:
                select_cols += ", ai_report"

            await cursor.execute(f"""
                SELECT {select_cols}
                FROM posts 
                ORDER BY scrape_date DESC 
                LIMIT ?
            """, (limit,))
            
            rows = await cursor.fetchall()
            
            results = []
            for row in rows:
                post_data = dict(row)
                if 'ai_report' in post_data and post_data['ai_report'] is not None:
                    if isinstance(post_data['ai_report'], (list, dict)): # Ensure it's a string
                        post_data['ai_report'] = json.dumps(post_data['ai_report'])
                else:
                    post_data['ai_report'] = "" # Default to empty string
                results.append(post_data)
            return results
            
        except Exception as e:
            logger.error(f"Error getting recent posts from DB: {e}")
            return []
        finally:
            await cursor.close()
