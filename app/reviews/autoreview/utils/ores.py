from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from django.conf import settings
from pywikibot.comms import http

from .living_person import is_living_person_article

if TYPE_CHECKING:
    from reviews.models import PendingRevision

logger = logging.getLogger(__name__)


def get_ores_thresholds(revision: PendingRevision) -> tuple[float, float]:
    """Get ORES thresholds with living person adjustments."""
    configuration = revision.page.wiki.configuration

    damaging_threshold = settings.ORES_DAMAGING_THRESHOLD
    if configuration.ores_damaging_threshold is not None:
        damaging_threshold = configuration.ores_damaging_threshold

    goodfaith_threshold = settings.ORES_GOODFAITH_THRESHOLD
    if configuration.ores_goodfaith_threshold is not None:
        goodfaith_threshold = configuration.ores_goodfaith_threshold

    if is_living_person_article(revision):
        living_damaging = (
            configuration.ores_damaging_threshold_living or settings.ORES_DAMAGING_THRESHOLD_LIVING
        )
        living_goodfaith = (
            configuration.ores_goodfaith_threshold_living
            or settings.ORES_GOODFAITH_THRESHOLD_LIVING
        )
        damaging_threshold = living_damaging
        goodfaith_threshold = living_goodfaith

    return damaging_threshold, goodfaith_threshold


def fetch_ores_scores(
    revision: PendingRevision, check_damaging: bool, check_goodfaith: bool
) -> tuple[float | None, float | None]:
    """Fetch ORES scores from API and cache them."""
    from reviews.models import ModelScores

    wiki_code = revision.page.wiki.code
    wiki_family = revision.page.wiki.family
    ores_wiki = f"{wiki_code}{wiki_family[0:4]}"

    models_to_check = []
    if check_damaging:
        models_to_check.append("damaging")
    if check_goodfaith:
        models_to_check.append("goodfaith")
    models_param = "|".join(models_to_check)

    url = f"https://ores.wikimedia.org/v3/scores/{ores_wiki}/{revision.revid}?models={models_param}"

    try:
        response = http.fetch(url, headers={"User-Agent": "PendingChangesBot/1.0"})
        data = json.loads(response.text)
        scores = data.get(ores_wiki, {}).get("scores", {}).get(str(revision.revid), {})

        damaging_prob = (
            scores.get("damaging", {}).get("score", {}).get("probability", {}).get("true", 0.0)
            if check_damaging
            else None
        )
        goodfaith_prob = (
            scores.get("goodfaith", {}).get("score", {}).get("probability", {}).get("true", 1.0)
            if check_goodfaith
            else None
        )

        ModelScores.objects.create(
            revision=revision,
            ores_damaging_score=damaging_prob,
            ores_goodfaith_score=goodfaith_prob,
        )

        return damaging_prob, goodfaith_prob

    except Exception as e:
        logger.error(f"Error fetching ORES scores for revision {revision.revid}: {e}")
        return None, None


def get_ores_scores(
    revision: PendingRevision, check_damaging: bool, check_goodfaith: bool
) -> tuple[float | None, float | None]:
    """Get ORES scores, using cache if available."""
    from reviews.models import ModelScores

    try:
        model_scores = ModelScores.objects.get(revision=revision)
        return model_scores.ores_damaging_score, model_scores.ores_goodfaith_score
    except ModelScores.DoesNotExist:
        return fetch_ores_scores(revision, check_damaging, check_goodfaith)
