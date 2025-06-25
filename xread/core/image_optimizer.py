"""Image optimization utilities for XReader."""

import asyncio
import hashlib
import mimetypes
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import aiohttp
import aiofiles

from xread.settings import settings, logger


class ImageOptimizer:
    """Handles image downloading, caching, and optimization."""
    
    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or (settings.data_dir / 'image_cache')
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: Dict[str, bytes] = {}
        self.max_memory_cache_size = 50  # Maximum number of images in memory
        
    async def get_optimized_image(
        self, 
        url: str, 
        max_size: int = 10 * 1024 * 1024,  # 10MB default
        cache_ttl: int = 3600 * 24  # 24 hours
    ) -> Optional[Tuple[bytes, str]]:
        """Get optimized image data with caching.
        
        Args:
            url: Image URL to fetch
            max_size: Maximum file size in bytes
            cache_ttl: Cache time-to-live in seconds
            
        Returns:
            Tuple of (image_data, mime_type) or None if failed
        """
        # Generate cache key
        url_hash = hashlib.md5(url.encode()).hexdigest()
        
        # Check memory cache first
        if url_hash in self._memory_cache:
            logger.debug(f"Found image in memory cache: {url}")
            mime_type = self._get_mime_type(url)
            return self._memory_cache[url_hash], mime_type
            
        # Check disk cache
        cache_file = self.cache_dir / f"{url_hash}.cache"
        if cache_file.exists():
            # Check if cache is still valid
            import time
            if time.time() - cache_file.stat().st_mtime < cache_ttl:
                try:
                    async with aiofiles.open(cache_file, 'rb') as f:
                        data = await f.read()
                    mime_type = self._get_mime_type(url)
                    self._add_to_memory_cache(url_hash, data)
                    logger.debug(f"Found image in disk cache: {url}")
                    return data, mime_type
                except Exception as e:
                    logger.warning(f"Failed to read cached image {url}: {e}")
        
        # Download and cache
        try:
            data, mime_type = await self._download_image(url, max_size)
            if data:
                # Cache to disk
                await self._cache_to_disk(cache_file, data)
                # Cache to memory
                self._add_to_memory_cache(url_hash, data)
                logger.info(f"Downloaded and cached image: {url}")
                return data, mime_type
        except Exception as e:
            logger.error(f"Failed to download image {url}: {e}")
            
        return None
    
    async def _download_image(self, url: str, max_size: int) -> Optional[Tuple[bytes, str]]:
        """Download image with size validation."""
        async with aiohttp.ClientSession() as session:
            async with asyncio.timeout(30):  # 30 second timeout
                async with session.get(url, allow_redirects=True) as response:
                    if response.status != 200:
                        logger.warning(f"Failed to download image {url}: HTTP {response.status}")
                        return None
                        
                    # Check content length
                    content_length = response.headers.get('Content-Length')
                    if content_length and int(content_length) > max_size:
                        logger.warning(f"Image {url} too large: {content_length} bytes")
                        return None
                    
                    # Read with size limit
                    data = BytesIO()
                    downloaded = 0
                    async for chunk in response.content.iter_chunked(8192):
                        downloaded += len(chunk)
                        if downloaded > max_size:
                            logger.warning(f"Image {url} too large during download: {downloaded} bytes")
                            return None
                        data.write(chunk)
                    
                    image_data = data.getvalue()
                    mime_type = response.headers.get('Content-Type') or self._get_mime_type(url)
                    
                    # Validate it's actually an image
                    if not mime_type.startswith('image/'):
                        logger.warning(f"Downloaded content is not an image: {mime_type}")
                        return None
                        
                    return image_data, mime_type
    
    def _get_mime_type(self, url: str) -> str:
        """Get MIME type from URL or default to JPEG."""
        mime_type, _ = mimetypes.guess_type(url)
        return mime_type if mime_type and mime_type.startswith('image/') else 'image/jpeg'
    
    async def _cache_to_disk(self, cache_file: Path, data: bytes) -> None:
        """Cache image data to disk."""
        try:
            async with aiofiles.open(cache_file, 'wb') as f:
                await f.write(data)
        except Exception as e:
            logger.error(f"Failed to cache image to disk {cache_file}: {e}")
    
    def _add_to_memory_cache(self, key: str, data: bytes) -> None:
        """Add image to memory cache with size management."""
        # Remove oldest items if cache is full
        if len(self._memory_cache) >= self.max_memory_cache_size:
            # Remove first item (FIFO)
            oldest_key = next(iter(self._memory_cache))
            del self._memory_cache[oldest_key]
            
        self._memory_cache[key] = data
    
    def clear_memory_cache(self) -> None:
        """Clear the memory cache."""
        self._memory_cache.clear()
        logger.info("Cleared image memory cache")
    
    async def clear_disk_cache(self, older_than_hours: int = 24) -> None:
        """Clear disk cache of files older than specified hours."""
        import time
        cutoff_time = time.time() - (older_than_hours * 3600)
        
        try:
            for cache_file in self.cache_dir.glob('*.cache'):
                if cache_file.stat().st_mtime < cutoff_time:
                    cache_file.unlink()
                    logger.debug(f"Removed old cached image: {cache_file}")
        except Exception as e:
            logger.error(f"Failed to clear disk cache: {e}")


# Global image optimizer instance
image_optimizer = ImageOptimizer()