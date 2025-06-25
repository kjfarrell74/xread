"""Advanced caching decorators for XReader."""

import functools
import hashlib
import json
import pickle
from typing import Any, Callable, Optional, Union
from datetime import timedelta

from xread.settings import logger


def cached(
    ttl: Union[int, timedelta] = 3600,
    key_prefix: str = "cache",
    use_memory: bool = True,
    serialize_method: str = "json"
):
    """Advanced caching decorator with multiple storage backends.
    
    Args:
        ttl: Time to live for cached values
        key_prefix: Prefix for cache keys
        use_memory: Whether to use in-memory caching
        serialize_method: Serialization method ('json' or 'pickle')
    """
    def decorator(func: Callable) -> Callable:
        # In-memory cache for this function
        memory_cache = {} if use_memory else None
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = _generate_cache_key(key_prefix, func.__name__, args, kwargs)
            
            # Check memory cache first
            if memory_cache and cache_key in memory_cache:
                cached_data, timestamp = memory_cache[cache_key]
                if _is_cache_valid(timestamp, ttl):
                    logger.debug(f"Cache hit (memory) for {func.__name__}")
                    return cached_data
                else:
                    # Remove expired entry
                    del memory_cache[cache_key]
            
            # Execute function
            logger.debug(f"Cache miss for {func.__name__}, executing function")
            result = await func(*args, **kwargs)
            
            # Cache the result
            if memory_cache is not None:
                import time
                memory_cache[cache_key] = (result, time.time())
                
                # Limit memory cache size
                if len(memory_cache) > 100:  # Max 100 items per function
                    # Remove oldest item
                    oldest_key = min(memory_cache.keys(), 
                                   key=lambda k: memory_cache[k][1])
                    del memory_cache[oldest_key]
            
            return result
            
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = _generate_cache_key(key_prefix, func.__name__, args, kwargs)
            
            # Check memory cache first
            if memory_cache and cache_key in memory_cache:
                cached_data, timestamp = memory_cache[cache_key]
                if _is_cache_valid(timestamp, ttl):
                    logger.debug(f"Cache hit (memory) for {func.__name__}")
                    return cached_data
                else:
                    # Remove expired entry
                    del memory_cache[cache_key]
            
            # Execute function
            logger.debug(f"Cache miss for {func.__name__}, executing function")
            result = func(*args, **kwargs)
            
            # Cache the result
            if memory_cache is not None:
                import time
                memory_cache[cache_key] = (result, time.time())
                
                # Limit memory cache size
                if len(memory_cache) > 100:  # Max 100 items per function
                    # Remove oldest item
                    oldest_key = min(memory_cache.keys(), 
                                   key=lambda k: memory_cache[k][1])
                    del memory_cache[oldest_key]
            
            return result
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
            
    return decorator


def _generate_cache_key(prefix: str, func_name: str, args: tuple, kwargs: dict) -> str:
    """Generate a unique cache key from function parameters."""
    # Create a deterministic string from args and kwargs
    key_data = {
        'function': func_name,
        'args': [str(arg) for arg in args],
        'kwargs': {k: str(v) for k, v in sorted(kwargs.items())}
    }
    
    # Use JSON for deterministic serialization
    key_string = json.dumps(key_data, sort_keys=True)
    
    # Generate hash
    key_hash = hashlib.md5(key_string.encode()).hexdigest()
    
    return f"{prefix}:{func_name}:{key_hash}"


def _is_cache_valid(timestamp: float, ttl: Union[int, timedelta]) -> bool:
    """Check if cached data is still valid."""
    import time
    
    if isinstance(ttl, timedelta):
        ttl_seconds = ttl.total_seconds()
    else:
        ttl_seconds = ttl
    
    return (time.time() - timestamp) < ttl_seconds


def clear_function_cache(func: Callable) -> None:
    """Clear the cache for a specific function."""
    if hasattr(func, '__wrapped__'):
        # Get the wrapper's memory cache
        wrapper = func
        while hasattr(wrapper, '__wrapped__'):
            if hasattr(wrapper, 'memory_cache'):
                wrapper.memory_cache.clear()
                logger.info(f"Cleared cache for function {func.__name__}")
                return
            wrapper = wrapper.__wrapped__
    
    logger.warning(f"No cache found for function {func.__name__}")


# Example usage decorators for common caching patterns
def cache_short_term(func):
    """Cache for 5 minutes - good for frequently changing data."""
    return cached(ttl=300, key_prefix="short")(func)


def cache_medium_term(func):
    """Cache for 1 hour - good for moderately stable data."""
    return cached(ttl=3600, key_prefix="medium")(func)


def cache_long_term(func):
    """Cache for 24 hours - good for stable data."""
    return cached(ttl=86400, key_prefix="long")(func)