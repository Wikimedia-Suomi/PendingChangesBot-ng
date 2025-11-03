from __future__ import annotations

import logging
from datetime import datetime, timezone

import mwparserfromhell

logger = logging.getLogger(__name__)


def parse_categories(wikitext: str) -> list[str]:
    code = mwparserfromhell.parse(wikitext or "")
    categories: list[str] = []
    for link in code.filter_wikilinks():
        target = str(link.title).strip()
        if target.lower().startswith("category:"):
            categories.append(target.split(":", 1)[-1])
    return sorted(set(categories))


def parse_superset_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        timestamp = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            timestamp = datetime.fromisoformat(normalized.replace(" ", "T"))
        except ValueError:
            if normalized.isdigit() and len(normalized) == 14:
                try:
                    timestamp = datetime.strptime(normalized, "%Y%m%d%H%M%S")
                except ValueError:
                    logger.warning("Unable to parse Superset timestamp: %s", value)
                    return None
                else:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
            else:
                logger.warning("Unable to parse Superset timestamp: %s", value)
                return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp


def parse_superset_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item and item.strip()]


def parse_optional_int(value) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_superset_bool(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "null"}:
            return None
        if normalized in {"1", "true", "t", "yes", "y"}:
            return True
        if normalized in {"0", "false", "f", "no", "n"}:
            return False
    return bool(value)


def prepare_superset_metadata(entry: dict) -> dict:
    metadata = dict(entry)
    for key in (
        "change_tags",
        "user_groups",
        "user_former_groups",
        "page_categories",
    ):
        if key in metadata and isinstance(metadata[key], str):
            metadata[key] = parse_superset_list(metadata[key])
    if "actor_user" in metadata:
        metadata["actor_user"] = parse_optional_int(metadata.get("actor_user"))
    if "rc_bot" in metadata:
        metadata["rc_bot"] = parse_superset_bool(metadata.get("rc_bot"))
    if "rc_patrolled" in metadata:
        metadata["rc_patrolled"] = parse_superset_bool(metadata.get("rc_patrolled"))
    return metadata
