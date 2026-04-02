"""
Lift Wing ML Model utilities with caching support.

This module provides functions to query Wikimedia's Lift Wing ML API
and cache results to avoid repeated API calls.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from django.utils import timezone
from pywikibot.comms import http

from .ml_model_compatibility import is_model_compatible

if TYPE_CHECKING:
    from reviews.models import PendingRevision

logger = logging.getLogger(__name__)

# Lift Wing ML Model Configuration
LIFTWING_ML_MODELS = {
    "revertrisk": {
        "endpoint": "revertrisk-language-agnostic:predict",
        "probability_key": "true",
        "description": "Language-agnostic revert risk prediction",
        "field_name": "lw_revertrisk_score",
    },
    "revertrisk_language_agnostic": {
        "endpoint": "revertrisk-language-agnostic:predict",
        "probability_key": "true",
        "description": "Language-agnostic revert risk prediction",
        "field_name": "lw_revertrisk_language_agnostic_score",
    },
    "revertrisk_multilingual": {
        "endpoint": "revertrisk-multilingual:predict",
        "probability_key": "true",
        "description": "Multilingual revert risk prediction",
        "field_name": "lw_revertrisk_multilingual_score",
    },
    "damaging": {
        "endpoint": "damaging:predict",
        "probability_key": "true",
        "description": "Damaging edit detection",
        "field_name": "lw_damaging_score",
    },
    "goodfaith": {
        "endpoint": "goodfaith:predict",
        "probability_key": "false",  # Inverted: false = bad faith
        "description": "Good faith prediction",
        "field_name": "lw_goodfaith_score",
    },
    "articlequality": {
        "endpoint": "articlequality:predict",
        "probability_key": "stub",  # Low quality indicator
        "description": "Article quality assessment",
        "field_name": None,  # Not cached (returns JSON)
    },
    "articletopic": {
        "endpoint": "articletopic:predict",
        "probability_key": None,  # Requires special handling
        "description": "Article topic classification",
        "field_name": None,  # Not cached (returns JSON)
    },
}


def fetch_liftwing_score(
    revision: PendingRevision, model_type: str = "revertrisk"
) -> float | None:
    """
    Fetch ML score from Lift Wing API (no caching).

    Args:
        revision: The pending revision to check
        model_type: The ML model to use

    Returns:
        The ML model score (0.0-1.0) or None if the API call fails
    """
    # Check compatibility
    wiki_lang = revision.page.wiki.code
    if not is_model_compatible(model_type, wiki_lang):
        logger.warning(
            f"Model {model_type} is not compatible with language {wiki_lang}. Skipping."
        )
        return None

    model_config = LIFTWING_ML_MODELS.get(model_type)
    if not model_config:
        logger.error(f"Unknown Lift Wing ML model type: {model_type}")
        return None

    url = f'https://api.wikimedia.org/service/lw/inference/v1/models/{model_config["endpoint"]}'
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "PendingChangesBot/1.0 (https://github.com/Wikimedia-Suomi/PendingChangesBot-ng)",
    }
    payload = json.dumps({
        "rev_id": revision.revid,
        "lang": revision.page.wiki.code,
        "project": revision.page.wiki.family,
    })

    try:
        resp = http.fetch(url, method="POST", headers=headers, data=payload)

        if resp.status_code != 200:
            logger.warning(
                f"{model_type} Lift Wing API returned status {resp.status_code} for revision {revision.revid}"
            )
            return None

        result = json.loads(resp.text)
        probabilities = result.get("output", {}).get("probabilities", {})
        probability_key = model_config["probability_key"]

        if probability_key is None:
            logger.warning(f"Model {model_type} requires special handling not yet implemented")
            return None

        score = probabilities.get(probability_key)

        if score is None:
            logger.warning(
                f"{model_type} Lift Wing API response missing '{probability_key}' probability for revision {revision.revid}"
            )
            return None

        return float(score)
    except Exception as e:
        logger.exception(f"Failed to fetch {model_type} score from Lift Wing API for revision {revision.revid}: {e}")
        return None


def get_liftwing_score(revision: PendingRevision, model_type: str = "revertrisk") -> float | None:
    """
    Get Lift Wing ML score, using cache if available.

    This implements the same caching pattern as ORES scores.

    Args:
        revision: The pending revision to check
        model_type: The ML model to use

    Returns:
        The ML model score (0.0-1.0) or None if unavailable
    """
    from reviews.models import ModelScores

    model_config = LIFTWING_ML_MODELS.get(model_type)
    if not model_config:
        logger.error(f"Unknown Lift Wing ML model type: {model_type}")
        return None

    field_name = model_config.get("field_name")
    if not field_name:
        # Models without cache field (articlequality, articletopic)
        # Always fetch from API
        return fetch_liftwing_score(revision, model_type)

    # Try to get from cache
    try:
        model_scores = ModelScores.objects.get(revision=revision)
        cached_score = getattr(model_scores, field_name, None)
        if cached_score is not None:
            return cached_score
    except ModelScores.DoesNotExist:
        pass

    # Not in cache, fetch from API
    score = fetch_liftwing_score(revision, model_type)

    if score is not None:
        # Save to cache
        try:
            model_scores, created = ModelScores.objects.get_or_create(revision=revision)
            setattr(model_scores, field_name, score)
            model_scores.lw_fetched_at = timezone.now()
            model_scores.save(update_fields=[field_name, "lw_fetched_at"])
        except Exception as e:
            logger.warning(f"Failed to cache {model_type} score for revision {revision.revid}: {e}")

    return score


def get_liftwing_thresholds(revision: PendingRevision, model_type: str) -> tuple[float, str]:
    """
    Get threshold for a Lift Wing model.

    Args:
        revision: The pending revision
        model_type: The model type

    Returns:
        Tuple of (threshold, display_name)
    """
    configuration = revision.page.wiki.configuration
    model_config = LIFTWING_ML_MODELS.get(model_type, {})
    display_name = model_config.get("description", model_type)

    # For now, using ml_model_threshold from configuration
    # In the future, we can add per-model thresholds
    threshold = getattr(configuration, "ml_model_threshold", 0.0)

    return threshold, display_name
