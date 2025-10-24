from __future__ import annotations

import logging
from functools import lru_cache

import pywikibot

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1000)
def was_user_blocked_after(code: str, family: str, username: str, year: int) -> bool:
    """
    Check if user was blocked after a specific year.

    Timestamp precision is reduced to year to improve cache hit rate.
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
