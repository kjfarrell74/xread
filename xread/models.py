"""Data models for representing scraped content in xread."""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
import re

from xread.settings import settings

@dataclass
class Image:
    """Represents an image with its URL and optional description."""
    url: str
    description: Optional[str] = None


@dataclass
class Post:
    """Represents a post with user info, text, date, permalink, and images."""
    user: str
    username: str
    text: str
    date: str
    permalink: str
    images: List[Image] = field(default_factory=list)
    status_id: Optional[str] = None
    likes: Optional[int] = 0
    retweets: Optional[int] = 0
    replies_count: Optional[int] = 0
    topic_tags: Optional[List[str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.permalink and self.permalink != "N/A":
            match = re.search(settings.status_id_regex, self.permalink)
            if match:
                self.status_id = match.group(1)

    def to_dict(self) -> Dict[str, Any]:
        """Convert Post to a JSON-serializable dictionary."""
        return asdict(self)


@dataclass
class ScrapedData:
    """Holds the main post and its replies after scraping."""
    main_post: Post
    replies: List[Post]
    factual_context: Optional[str] = None
    source: Optional[str] = None

    def get_full_text(self) -> str:
        """Combine main post text and reply texts into a single string."""
        parts = [f"Main Post (@{self.main_post.username}):\n{self.main_post.text}\n\n"]
        
        if self.replies:
            parts.append("Replies:\n")
            for i, reply in enumerate(self.replies, start=1):
                # Filter out duplicate consecutive replies
                if i > 1 and reply.text == self.replies[i-2].text and reply.username == self.replies[i-2].username:
                    continue
                parts.append(f"--- Reply {i} (@{reply.username}) ---\n{reply.text}\n")
        
        return "".join(parts).strip()


@dataclass
class UserProfile:
    """Represents a Twitter user profile with relevant information."""
    username: str
    display_name: str
    bio: Optional[str] = None
    location: Optional[str] = None
    website: Optional[str] = None
    profile_image_url: Optional[str] = None
    followers_count: Optional[int] = None
    following_count: Optional[int] = None
    join_date: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert UserProfile to a JSON-serializable dictionary."""
        return asdict(self)

@dataclass
class AuthorNote:
    """Represents an author note with username and content."""
    username: str
    note_content: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert AuthorNote to a JSON-serializable dictionary."""
        return asdict(self)
