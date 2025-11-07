from __future__ import annotations

import logging
import time
from functools import wraps
from typing import Callable, TypeVar

import pywikibot

logger = logging.getLogger(__name__)

# Cache TTL in seconds (1 hour)
CACHE_TTL = 3600

T = TypeVar("T")


def ttl_cache(maxsize: int = 128, ttl: int = CACHE_TTL) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    LRU cache decorator with time-to-live (TTL) expiration.

    Args:
        maxsize: Maximum number of cached entries
        ttl: Time to live in seconds (default: 1 hour)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        # Store cache with timestamps
        cache: dict[tuple, tuple[T, float]] = {}

        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from args and kwargs
            cache_key = args + tuple(sorted(kwargs.items()))
            current_time = time.time()

            # Check if cache entry exists and is not expired
            if cache_key in cache:
                result, timestamp = cache[cache_key]
                if current_time - timestamp <= ttl:
                    # Cache hit and not expired
                    return result
                else:
                    # Cache expired, remove entry
                    del cache[cache_key]

            # Cache miss or expired - call function
            result = func(*args, **kwargs)
            cache[cache_key] = (result, current_time)

            # Enforce maxsize limit
            if len(cache) > maxsize:
                # Remove oldest entry
                oldest_key = min(cache.items(), key=lambda item: item[1][1])[0]
                del cache[oldest_key]

            return result

        # Expose cache info and clear methods
        def cache_info():
            return {
                "hits": 0,  # Simplified for compatibility
                "misses": 0,
                "maxsize": maxsize,
                "currsize": len(cache),
            }

        def cache_clear():
            cache.clear()

        wrapper.cache_info = cache_info  # type: ignore
        wrapper.cache_clear = cache_clear  # type: ignore

        return wrapper
    return decorator


@ttl_cache(maxsize=1000, ttl=CACHE_TTL)
def was_user_blocked_after(code: str, family: str, username: str, year: int) -> bool:
    """
    Check if user was blocked after a specific year.

    Timestamp precision is reduced to year to improve cache hit rate.
    Cache expires after 1 hour to ensure block status is not stale.
    """
    try:
        site = pywikibot.Site(code, family)
        timestamp = pywikibot.Timestamp(year, 1, 1, 0, 0, 0)

        block_events = site.logevents(
            logtype="block",
            page=f"User:{username}",
            start=timestamp,
            reverse=True,
            total=1,
        )

        for event in block_events:
            if event.action() == "block":
                return True

        return False

    except Exception as e:
        logger.error(f"Error checking blocks for {username}: {e}")
        return False
