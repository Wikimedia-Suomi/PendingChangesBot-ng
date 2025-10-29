from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from http import HTTPStatus

import requests
from django.core.cache import cache
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, JsonResponse, QueryDict
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .autoreview.checks import AVAILABLE_CHECKS
from .autoreview.runner import run_autoreview_for_page
from .models import (
    EditorProfile,
    PendingPage,
    ReviewStatisticsCache,
    ReviewStatisticsMetadata,
    Wiki,
    WikiConfiguration,
)
from .models.flaggedrevs_statistics import FlaggedRevsStatistics, ReviewActivity
from .services import WikiClient

logger = logging.getLogger(__name__)
CACHE_TTL = 60 * 60 * 1


def calculate_percentile(values: list[float], percentile: float) -> float:
    """
    Calculate the percentile of a list of values using linear interpolation.

    This function implements the standard percentile calculation method:
    1. Sort the values in ascending order
    2. Calculate the index position: (n-1) * (percentile/100)
    3. If the index is not a whole number, interpolate between the floor and ceiling values

    For median (P50), this returns the middle value for odd-length lists,
    or the average of the two middle values for even-length lists.

    Args:
        values: List of numeric values to calculate percentile from
        percentile: The percentile to calculate (0-100), e.g., 50 for median

    Returns:
        The calculated percentile value, or 0.0 if the list is empty

    Examples:
        >>> calculate_percentile([1, 2, 3, 4, 5], 50)  # Median
        3.0
        >>> calculate_percentile([1, 2, 3, 4], 50)  # Median of even list
        2.5
        >>> calculate_percentile([1, 5, 10, 20], 90)  # P90
        17.0
    """
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = (len(sorted_values) - 1) * (percentile / 100.0)
    floor = int(index)
    ceil = floor + 1
    if ceil >= len(sorted_values):
        return sorted_values[floor]
    # Linear interpolation between floor and ceil
    return sorted_values[floor] + (sorted_values[ceil] - sorted_values[floor]) * (index - floor)


def get_time_filter_cutoff(time_filter: str) -> datetime | None:
    """Get the cutoff datetime for a time filter."""
    now = timezone.now()
    if time_filter == "day":
        return now - timedelta(days=1)
    elif time_filter == "week":
        return now - timedelta(days=7)
    return None


def statistics_page(request: HttpRequest) -> HttpResponse:
    """Render the standalone statistics page."""
    wikis = Wiki.objects.all().order_by("code")
    if not wikis.exists():
        # If no wikis, redirect to main page to populate them
        return index(request)

    payload = []
    for wiki in wikis:
        configuration, _ = WikiConfiguration.objects.get_or_create(wiki=wiki)
        payload.append(
            {
                "id": wiki.id,
                "name": wiki.name,
                "code": wiki.code,
                "api_endpoint": wiki.api_endpoint,
                "configuration": {
                    "blocking_categories": configuration.blocking_categories,
                    "auto_approved_groups": configuration.auto_approved_groups,
                },
            }
        )
    return render(
        request,
        "reviews/statistics.html",
        {
            "initial_wikis": json.dumps(payload),
        },
    )


def index(request: HttpRequest) -> HttpResponse:
    """Render the Vue.js application shell."""

    wikis = Wiki.objects.all().order_by("code")
    if not wikis.exists():
        # All Wikipedias using FlaggedRevisions extension
        # Source: https://noc.wikimedia.org/conf/highlight.php?file=flaggedrevs.php
        default_wikis = (
            {
                "name": "Alemannic Wikipedia",
                "code": "als",
                "api_endpoint": "https://als.wikipedia.org/w/api.php",
            },
            {
                "name": "Arabic Wikipedia",
                "code": "ar",
                "api_endpoint": "https://ar.wikipedia.org/w/api.php",
            },
            {
                "name": "Belarusian Wikipedia",
                "code": "be",
                "api_endpoint": "https://be.wikipedia.org/w/api.php",
            },
            {
                "name": "Bengali Wikipedia",
                "code": "bn",
                "api_endpoint": "https://bn.wikipedia.org/w/api.php",
            },
            {
                "name": "Bosnian Wikipedia",
                "code": "bs",
                "api_endpoint": "https://bs.wikipedia.org/w/api.php",
            },
            {
                "name": "Chechen Wikipedia",
                "code": "ce",
                "api_endpoint": "https://ce.wikipedia.org/w/api.php",
            },
            {
                "name": "Central Kurdish Wikipedia",
                "code": "ckb",
                "api_endpoint": "https://ckb.wikipedia.org/w/api.php",
            },
            {
                "name": "German Wikipedia",
                "code": "de",
                "api_endpoint": "https://de.wikipedia.org/w/api.php",
            },
            {
                "name": "English Wikipedia",
                "code": "en",
                "api_endpoint": "https://en.wikipedia.org/w/api.php",
            },
            {
                "name": "Esperanto Wikipedia",
                "code": "eo",
                "api_endpoint": "https://eo.wikipedia.org/w/api.php",
            },
            {
                "name": "Persian Wikipedia",
                "code": "fa",
                "api_endpoint": "https://fa.wikipedia.org/w/api.php",
            },
            {
                "name": "Finnish Wikipedia",
                "code": "fi",
                "api_endpoint": "https://fi.wikipedia.org/w/api.php",
            },
            {
                "name": "Hindi Wikipedia",
                "code": "hi",
                "api_endpoint": "https://hi.wikipedia.org/w/api.php",
            },
            {
                "name": "Hungarian Wikipedia",
                "code": "hu",
                "api_endpoint": "https://hu.wikipedia.org/w/api.php",
            },
            {
                "name": "Interlingua Wikipedia",
                "code": "ia",
                "api_endpoint": "https://ia.wikipedia.org/w/api.php",
            },
            {
                "name": "Indonesian Wikipedia",
                "code": "id",
                "api_endpoint": "https://id.wikipedia.org/w/api.php",
            },
            {
                "name": "Georgian Wikipedia",
                "code": "ka",
                "api_endpoint": "https://ka.wikipedia.org/w/api.php",
            },
            {
                "name": "Polish Wikipedia",
                "code": "pl",
                "api_endpoint": "https://pl.wikipedia.org/w/api.php",
            },
            {
                "name": "Portuguese Wikipedia",
                "code": "pt",
                "api_endpoint": "https://pt.wikipedia.org/w/api.php",
            },
            {
                "name": "Russian Wikipedia",
                "code": "ru",
                "api_endpoint": "https://ru.wikipedia.org/w/api.php",
            },
            {
                "name": "Albanian Wikipedia",
                "code": "sq",
                "api_endpoint": "https://sq.wikipedia.org/w/api.php",
            },
            {
                "name": "Turkish Wikipedia",
                "code": "tr",
                "api_endpoint": "https://tr.wikipedia.org/w/api.php",
            },
            {
                "name": "Ukrainian Wikipedia",
                "code": "uk",
                "api_endpoint": "https://uk.wikipedia.org/w/api.php",
            },
            {
                "name": "Venetian Wikipedia",
                "code": "vec",
                "api_endpoint": "https://vec.wikipedia.org/w/api.php",
            },
        )
        for defaults in default_wikis:
            wiki, _ = Wiki.objects.get_or_create(
                code=defaults["code"],
                defaults={
                    "name": defaults["name"],
                    "api_endpoint": defaults["api_endpoint"],
                },
            )
            WikiConfiguration.objects.get_or_create(wiki=wiki)
        wikis = Wiki.objects.all().order_by("code")
    payload = []
    for wiki in wikis:
        configuration, _ = WikiConfiguration.objects.get_or_create(wiki=wiki)
        payload.append(
            {
                "id": wiki.id,
                "name": wiki.name,
                "code": wiki.code,
                "api_endpoint": wiki.api_endpoint,
                "configuration": {
                    "blocking_categories": configuration.blocking_categories,
                    "auto_approved_groups": configuration.auto_approved_groups,
                    "ores_damaging_threshold": configuration.ores_damaging_threshold,
                    "ores_goodfaith_threshold": configuration.ores_goodfaith_threshold,
                    "ores_damaging_threshold_living": configuration.ores_damaging_threshold_living,
                    "ores_goodfaith_threshold_living": configuration.ores_goodfaith_threshold_living,  # noqa E501
                },
            }
        )
    return render(
        request,
        "reviews/index.html",
        {
            "initial_wikis": payload,
        },
    )


@require_GET
def api_wikis(request: HttpRequest) -> JsonResponse:
    payload = []
    for wiki in Wiki.objects.all().order_by("code"):
        configuration = getattr(wiki, "configuration", None)
        payload.append(
            {
                "id": wiki.id,
                "name": wiki.name,
                "code": wiki.code,
                "api_endpoint": wiki.api_endpoint,
                "configuration": {
                    "blocking_categories": (
                        configuration.blocking_categories if configuration else []
                    ),
                    "auto_approved_groups": (
                        configuration.auto_approved_groups if configuration else []
                    ),
                    "ores_damaging_threshold": (
                        configuration.ores_damaging_threshold if configuration else 0.0
                    ),
                    "ores_goodfaith_threshold": (
                        configuration.ores_goodfaith_threshold if configuration else 0.0
                    ),
                    "ores_damaging_threshold_living": (
                        configuration.ores_damaging_threshold_living if configuration else 0.0
                    ),
                    "ores_goodfaith_threshold_living": (
                        configuration.ores_goodfaith_threshold_living if configuration else 0.0
                    ),
                },
            }
        )
    return JsonResponse({"wikis": payload})


def _get_wiki(pk: int) -> Wiki:
    wiki = get_object_or_404(Wiki, pk=pk)
    WikiConfiguration.objects.get_or_create(wiki=wiki)
    return wiki


@csrf_exempt
@require_http_methods(["POST"])
def api_refresh(request: HttpRequest, pk: int) -> JsonResponse:
    wiki = _get_wiki(pk)
    client = WikiClient(wiki)
    try:
        pages = client.refresh()
    except Exception as exc:  # pragma: no cover - network failures handled in UI
        logger.exception("Failed to refresh pending changes for %s", wiki.code)
        return JsonResponse(
            {"error": str(exc)},
            status=HTTPStatus.BAD_GATEWAY,
        )
    return JsonResponse({"pages": [page.pageid for page in pages]})


def _build_revision_payload(revisions, wiki):
    usernames: set[str] = {revision.user_name for revision in revisions if revision.user_name}
    profiles = {
        profile.username: profile
        for profile in EditorProfile.objects.filter(wiki=wiki, username__in=usernames)
    }

    payload: list[dict] = []
    for revision in revisions:
        if revision.page and revision.revid == revision.page.stable_revid:
            continue
        profile = profiles.get(revision.user_name)
        superset_data = revision.superset_data or {}
        user_groups = profile.usergroups if profile else superset_data.get("user_groups", [])
        if not user_groups:
            user_groups = []
        group_set = set(user_groups)
        revision_categories = list(revision.categories or [])
        if revision_categories:
            categories = revision_categories
        else:
            page_categories = revision.page.categories or []
            if isinstance(page_categories, list) and page_categories:
                categories = [str(category) for category in page_categories if category]
            else:
                superset_categories = superset_data.get("page_categories") or []
                if isinstance(superset_categories, list):
                    categories = [str(category) for category in superset_categories if category]
                else:
                    categories = []

        payload.append(
            {
                "revid": revision.revid,
                "parentid": revision.parentid,
                "timestamp": revision.timestamp.isoformat(),
                "age_seconds": int(revision.age_at_fetch.total_seconds()),
                "user_name": revision.user_name,
                "change_tags": revision.change_tags
                if revision.change_tags
                else superset_data.get("change_tags", []),
                "comment": revision.comment,
                "categories": categories,
                "sha1": revision.sha1,
                "editor_profile": {
                    "usergroups": user_groups,
                    "is_blocked": (
                        profile.is_blocked
                        if profile
                        else bool(superset_data.get("user_blocked", False))
                    ),
                    "is_bot": (
                        profile.is_bot
                        if profile
                        else ("bot" in group_set or bool(superset_data.get("rc_bot")))
                    ),
                    "is_autopatrolled": (
                        profile.is_autopatrolled if profile else ("autopatrolled" in group_set)
                    ),
                    "is_autoreviewed": (
                        profile.is_autoreviewed
                        if profile
                        else bool(
                            group_set
                            & {"autoreview", "autoreviewer", "editor", "reviewer", "sysop", "bot"}
                        )
                    ),
                },
            }
        )
    return payload


@require_GET
def api_pending(request: HttpRequest, pk: int) -> JsonResponse:
    wiki = _get_wiki(pk)
    pages_payload = []
    for page in PendingPage.objects.filter(wiki=wiki).prefetch_related("revisions"):
        revisions_payload = _build_revision_payload(page.revisions.all(), wiki)
        pages_payload.append(
            {
                "pageid": page.pageid,
                "title": page.title,
                "pending_since": page.pending_since.isoformat() if page.pending_since else None,
                "stable_revid": page.stable_revid,
                "revisions": revisions_payload,
            }
        )
    return JsonResponse({"pages": pages_payload})


@require_GET
def api_page_revisions(request: HttpRequest, pk: int, pageid: int) -> JsonResponse:
    wiki = _get_wiki(pk)
    page = get_object_or_404(
        PendingPage.objects.prefetch_related("revisions"),
        wiki=wiki,
        pageid=pageid,
    )
    revisions_payload = _build_revision_payload(page.revisions.all(), wiki)
    return JsonResponse(
        {
            "pageid": page.pageid,
            "revisions": revisions_payload,
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def api_autoreview(request: HttpRequest, pk: int, pageid: int) -> JsonResponse:
    wiki = _get_wiki(pk)
    page = get_object_or_404(
        PendingPage.objects.prefetch_related("revisions"),
        wiki=wiki,
        pageid=pageid,
    )
    results = run_autoreview_for_page(page)
    return JsonResponse(
        {
            "pageid": page.pageid,
            "title": page.title,
            "mode": "dry-run",
            "results": results,
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def api_clear_cache(request: HttpRequest, pk: int) -> JsonResponse:
    wiki = _get_wiki(pk)
    deleted_pages, _ = PendingPage.objects.filter(wiki=wiki).delete()
    return JsonResponse({"cleared": deleted_pages})


@csrf_exempt
@require_http_methods(["GET", "PUT"])
def api_configuration(request: HttpRequest, pk: int) -> JsonResponse:
    wiki = _get_wiki(pk)
    configuration = wiki.configuration
    if request.method == "PUT":
        content_type = request.content_type or ""
        if content_type.startswith("application/json"):
            payload = json.loads(request.body.decode("utf-8")) if request.body else {}
            blocking_categories = payload.get("blocking_categories", [])
            auto_groups = payload.get("auto_approved_groups", [])
            ores_damaging_threshold = payload.get("ores_damaging_threshold")
            ores_goodfaith_threshold = payload.get("ores_goodfaith_threshold")
            ores_damaging_threshold_living = payload.get("ores_damaging_threshold_living")
            ores_goodfaith_threshold_living = payload.get("ores_goodfaith_threshold_living")
        else:
            encoding = request.encoding or "utf-8"
            raw_body = request.body.decode(encoding) if request.body else ""
            form_payload = QueryDict(raw_body, mutable=False)
            blocking_categories = form_payload.getlist("blocking_categories")
            auto_groups = form_payload.getlist("auto_approved_groups")
            ores_damaging_threshold = form_payload.get("ores_damaging_threshold")
            ores_goodfaith_threshold = form_payload.get("ores_goodfaith_threshold")
            ores_damaging_threshold_living = form_payload.get("ores_damaging_threshold_living")
            ores_goodfaith_threshold_living = form_payload.get("ores_goodfaith_threshold_living")

        if isinstance(blocking_categories, str):
            blocking_categories = [blocking_categories]
        if isinstance(auto_groups, str):
            auto_groups = [auto_groups]

        def validate_threshold(value, name):
            if value is not None:
                try:
                    float_value = float(value)
                    if not (0.0 <= float_value <= 1.0):
                        return JsonResponse(
                            {"error": f"{name} must be between 0.0 and 1.0"},
                            status=400,
                        )
                    return float_value
                except (ValueError, TypeError):
                    return JsonResponse(
                        {"error": f"{name} must be a valid number"},
                        status=400,
                    )
            return None

        validated_damaging = validate_threshold(ores_damaging_threshold, "ores_damaging_threshold")
        if isinstance(validated_damaging, JsonResponse):
            return validated_damaging

        validated_goodfaith = validate_threshold(
            ores_goodfaith_threshold, "ores_goodfaith_threshold"
        )
        if isinstance(validated_goodfaith, JsonResponse):
            return validated_goodfaith

        validated_damaging_living = validate_threshold(
            ores_damaging_threshold_living, "ores_damaging_threshold_living"
        )
        if isinstance(validated_damaging_living, JsonResponse):
            return validated_damaging_living

        validated_goodfaith_living = validate_threshold(
            ores_goodfaith_threshold_living, "ores_goodfaith_threshold_living"
        )
        if isinstance(validated_goodfaith_living, JsonResponse):
            return validated_goodfaith_living

        configuration.blocking_categories = blocking_categories
        configuration.auto_approved_groups = auto_groups
        update_fields = ["blocking_categories", "auto_approved_groups", "updated_at"]

        if validated_damaging is not None:
            configuration.ores_damaging_threshold = validated_damaging
            update_fields.append("ores_damaging_threshold")
        if validated_goodfaith is not None:
            configuration.ores_goodfaith_threshold = validated_goodfaith
            update_fields.append("ores_goodfaith_threshold")
        if validated_damaging_living is not None:
            configuration.ores_damaging_threshold_living = validated_damaging_living
            update_fields.append("ores_damaging_threshold_living")
        if validated_goodfaith_living is not None:
            configuration.ores_goodfaith_threshold_living = validated_goodfaith_living
            update_fields.append("ores_goodfaith_threshold_living")

        configuration.save(update_fields=update_fields)

    return JsonResponse(
        {
            "blocking_categories": configuration.blocking_categories,
            "auto_approved_groups": configuration.auto_approved_groups,
            "ores_damaging_threshold": configuration.ores_damaging_threshold,
            "ores_goodfaith_threshold": configuration.ores_goodfaith_threshold,
            "ores_damaging_threshold_living": configuration.ores_damaging_threshold_living,
            "ores_goodfaith_threshold_living": configuration.ores_goodfaith_threshold_living,
        }
    )


@require_GET
def api_available_checks(request: HttpRequest) -> JsonResponse:
    """List all available autoreview checks."""
    checks = [
        {
            "id": check["id"],
            "name": check["name"],
            "priority": check["priority"],
        }
        for check in sorted(AVAILABLE_CHECKS, key=lambda c: c["priority"])
    ]
    return JsonResponse({"checks": checks})


@csrf_exempt
@require_http_methods(["GET", "PUT"])
def api_enabled_checks(request: HttpRequest, pk: int) -> JsonResponse:
    """Get or update enabled checks for a wiki."""
    wiki = _get_wiki(pk)
    configuration = wiki.configuration

    if request.method == "PUT":
        if request.content_type == "application/json":
            payload = json.loads(request.body.decode("utf-8")) if request.body else {}
        else:
            payload = request.POST.dict()

        enabled_checks = payload.get("enabled_checks")
        if enabled_checks is not None:
            if not isinstance(enabled_checks, list):
                return JsonResponse(
                    {"error": "enabled_checks must be a list of check IDs"},
                    status=400,
                )

            all_check_ids = {c["id"] for c in AVAILABLE_CHECKS}
            invalid_ids = [cid for cid in enabled_checks if cid not in all_check_ids]
            if invalid_ids:
                return JsonResponse(
                    {"error": f"Invalid check IDs: {', '.join(invalid_ids)}"},
                    status=400,
                )

            configuration.enabled_checks = enabled_checks
            configuration.save(update_fields=["enabled_checks", "updated_at"])

    all_check_ids = [c["id"] for c in sorted(AVAILABLE_CHECKS, key=lambda c: c["priority"])]
    enabled = configuration.enabled_checks if configuration.enabled_checks else all_check_ids

    return JsonResponse(
        {
            "enabled_checks": enabled,
            "all_checks": all_check_ids,
        }
    )


def fetch_diff(request):
    url = request.GET.get("url")
    if not url:
        return JsonResponse({"error": "Missing 'url' parameter"}, status=400)

    cached_html = cache.get(url)
    if cached_html:
        return HttpResponse(cached_html, content_type="text/html")

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; DiffFetcher/1.0; +https://yourdomain.com)",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        html_content = response.text

        cache.set(url, html_content, CACHE_TTL)

        return HttpResponse(html_content, content_type="text/html")
    except requests.RequestException as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_GET
def api_statistics(request: HttpRequest, pk: int) -> JsonResponse:
    """Get cached review statistics for a wiki."""
    wiki = _get_wiki(pk)

    # Get metadata
    try:
        metadata = ReviewStatisticsMetadata.objects.get(wiki=wiki)
        metadata_payload = {
            "last_refreshed_at": metadata.last_refreshed_at.isoformat(),
            "total_records": metadata.total_records,
            "oldest_review_timestamp": (
                metadata.oldest_review_timestamp.isoformat()
                if metadata.oldest_review_timestamp
                else None
            ),
            "newest_review_timestamp": (
                metadata.newest_review_timestamp.isoformat()
                if metadata.newest_review_timestamp
                else None
            ),
        }
    except ReviewStatisticsMetadata.DoesNotExist:
        metadata_payload = {
            "last_refreshed_at": None,
            "total_records": 0,
            "oldest_review_timestamp": None,
            "newest_review_timestamp": None,
        }

    # Get filter parameters
    reviewer_filter = request.GET.get("reviewer", "").strip()
    reviewed_user_filter = request.GET.get("reviewed_user", "").strip()
    time_filter = request.GET.get("time_filter", "all").strip()
    exclude_auto_reviewers = request.GET.get("exclude_auto_reviewers", "false").lower() == "true"
    limit = int(request.GET.get("limit", 100))

    # Build base query
    statistics_qs = ReviewStatisticsCache.objects.filter(wiki=wiki)

    # Apply time filter
    cutoff = get_time_filter_cutoff(time_filter)
    if cutoff:
        statistics_qs = statistics_qs.filter(reviewed_timestamp__gte=cutoff)

    # Apply reviewer filter
    if reviewer_filter:
        statistics_qs = statistics_qs.filter(reviewer_name__iexact=reviewer_filter)

    # Apply reviewed user filter
    if reviewed_user_filter:
        statistics_qs = statistics_qs.filter(reviewed_user_name__iexact=reviewed_user_filter)

    # Apply auto-reviewer exclusion filter
    if exclude_auto_reviewers:
        # Get users with auto-review rights
        auto_reviewers = EditorProfile.objects.filter(wiki=wiki, is_autoreviewed=True).values_list(
            "username", flat=True
        )
        # Exclude these users from reviewed_user_name
        statistics_qs = statistics_qs.exclude(reviewed_user_name__in=auto_reviewers)

    # Get aggregated data - Top Reviewers (with same filters)
    top_reviewers_qs = ReviewStatisticsCache.objects.filter(wiki=wiki)
    if cutoff:
        top_reviewers_qs = top_reviewers_qs.filter(reviewed_timestamp__gte=cutoff)
    if exclude_auto_reviewers:
        top_reviewers_qs = top_reviewers_qs.exclude(reviewed_user_name__in=auto_reviewers)

    top_reviewers = (
        top_reviewers_qs.values("reviewer_name")
        .annotate(review_count=Count("id"))
        .order_by("-review_count")[:20]
    )

    # Get aggregated data - Top Reviewed Users (with same filters)
    top_reviewed_users_qs = ReviewStatisticsCache.objects.filter(wiki=wiki)
    if cutoff:
        top_reviewed_users_qs = top_reviewed_users_qs.filter(reviewed_timestamp__gte=cutoff)
    if exclude_auto_reviewers:
        top_reviewed_users_qs = top_reviewed_users_qs.exclude(reviewed_user_name__in=auto_reviewers)

    top_reviewed_users = (
        top_reviewed_users_qs.values("reviewed_user_name")
        .annotate(review_count=Count("id"))
        .order_by("-review_count")[:20]
    )

    # Get individual records (with optional filters)
    records = statistics_qs.order_by("-reviewed_timestamp")[:limit]
    records_payload = [
        {
            "reviewer_name": record.reviewer_name,
            "reviewed_user_name": record.reviewed_user_name,
            "page_title": record.page_title,
            "page_id": record.page_id,
            "reviewed_revision_id": record.reviewed_revision_id,
            "pending_revision_id": record.pending_revision_id,
            "reviewed_timestamp": record.reviewed_timestamp.isoformat(),
            "pending_timestamp": record.pending_timestamp.isoformat(),
            "review_delay_days": record.review_delay_days,
        }
        for record in records
    ]

    return JsonResponse(
        {
            "metadata": metadata_payload,
            "top_reviewers": list(top_reviewers),
            "top_reviewed_users": list(top_reviewed_users),
            "records": records_payload,
        }
    )


@require_GET
def api_statistics_charts(request: HttpRequest, pk: int) -> JsonResponse:
    """Get chart data for review statistics."""
    wiki = _get_wiki(pk)

    # Get filter parameters
    time_filter = request.GET.get("time_filter", "all").strip()
    exclude_auto_reviewers = request.GET.get("exclude_auto_reviewers", "false").lower() == "true"

    # Build base query
    statistics_qs = ReviewStatisticsCache.objects.filter(wiki=wiki)

    # Apply time filter
    cutoff = get_time_filter_cutoff(time_filter)
    if cutoff:
        statistics_qs = statistics_qs.filter(reviewed_timestamp__gte=cutoff)

    # Apply auto-reviewer exclusion
    if exclude_auto_reviewers:
        auto_reviewers = EditorProfile.objects.filter(wiki=wiki, is_autoreviewed=True).values_list(
            "username", flat=True
        )
        statistics_qs = statistics_qs.exclude(reviewed_user_name__in=auto_reviewers)

    # Get all records for processing
    records = statistics_qs.values(
        "reviewed_timestamp", "reviewer_name", "review_delay_days"
    ).order_by("reviewed_timestamp")

    # Group data by date or hour depending on time filter
    reviewers_by_date = defaultdict(set)
    pending_by_date = defaultdict(int)
    delays_by_date = defaultdict(list)

    # For "day" filter, group by hour; otherwise by date
    use_hourly = time_filter == "day"

    for record in records:
        timestamp = record["reviewed_timestamp"]
        if use_hourly:
            # Group by hour: format as "YYYY-MM-DD HH:00"
            date_str = timestamp.strftime("%Y-%m-%d %H:00")
        else:
            # Group by date: format as "YYYY-MM-DD"
            date_str = timestamp.date().isoformat()

        reviewers_by_date[date_str].add(record["reviewer_name"])
        pending_by_date[date_str] += 1
        delays_by_date[date_str].append(float(record["review_delay_days"]))

    # Build chart data
    reviewers_over_time = [
        {"date": date, "count": len(reviewers)}
        for date, reviewers in sorted(reviewers_by_date.items())
    ]

    pending_reviews_per_day = [
        {"date": date, "count": count} for date, count in sorted(pending_by_date.items())
    ]

    average_delay_over_time = [
        {"date": date, "avg_delay": sum(delays) / len(delays) if delays else 0}
        for date, delays in sorted(delays_by_date.items())
    ]

    delay_percentiles = [
        {
            "date": date,
            "p10": calculate_percentile(delays, 10),
            "p50": calculate_percentile(delays, 50),
            "p90": calculate_percentile(delays, 90),
        }
        for date, delays in sorted(delays_by_date.items())
    ]

    # Calculate overall statistics
    all_delays = [delay for delays in delays_by_date.values() for delay in delays]
    overall_stats = {
        "avg_delay": sum(all_delays) / len(all_delays) if all_delays else 0,
        "p10": calculate_percentile(all_delays, 10),
        "p50": calculate_percentile(all_delays, 50),
        "p90": calculate_percentile(all_delays, 90),
        "total_reviews": len(all_delays),
        "unique_reviewers": len({rev for revs in reviewers_by_date.values() for rev in revs}),
    }

    return JsonResponse(
        {
            "reviewers_over_time": reviewers_over_time,
            "pending_reviews_per_day": pending_reviews_per_day,
            "average_delay_over_time": average_delay_over_time,
            "delay_percentiles": delay_percentiles,
            "overall_stats": overall_stats,
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def api_statistics_refresh(request: HttpRequest, pk: int) -> JsonResponse:
    """Incrementally refresh review statistics for a wiki (fetch only new data)."""
    wiki = _get_wiki(pk)
    client = WikiClient(wiki)

    try:
        result = client.refresh_review_statistics()
    except Exception as exc:  # pragma: no cover - network failures handled in UI
        logger.exception("Failed to refresh statistics for %s", wiki.code)
        return JsonResponse(
            {"error": str(exc)},
            status=HTTPStatus.BAD_GATEWAY,
        )

    return JsonResponse(
        {
            "total_records": result["total_records"],
            "oldest_timestamp": (
                result["oldest_timestamp"].isoformat() if result["oldest_timestamp"] else None
            ),
            "newest_timestamp": (
                result["newest_timestamp"].isoformat() if result["newest_timestamp"] else None
            ),
            "is_incremental": result.get("is_incremental", False),
            "batches_fetched": result.get("batches_fetched", 0),
            "batch_limit_reached": result.get("batch_limit_reached", False),
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def api_statistics_clear_and_reload(request: HttpRequest, pk: int) -> JsonResponse:
    """Clear statistics cache and reload fresh data for specified number of days."""
    wiki = _get_wiki(pk)
    client = WikiClient(wiki)

    # Get optional days parameter (default: 30)
    days = int(request.POST.get("days", 30))

    if days < 1 or days > 365:
        return JsonResponse(
            {"error": "days parameter must be between 1 and 365"},
            status=HTTPStatus.BAD_REQUEST,
        )

    try:
        result = client.fetch_review_statistics(days=days)
    except Exception as exc:  # pragma: no cover - network failures handled in UI
        logger.exception("Failed to clear and reload statistics for %s", wiki.code)
        return JsonResponse(
            {"error": str(exc)},
            status=HTTPStatus.BAD_GATEWAY,
        )

    return JsonResponse(
        {
            "total_records": result["total_records"],
            "oldest_timestamp": (
                result["oldest_timestamp"].isoformat() if result["oldest_timestamp"] else None
            ),
            "newest_timestamp": (
                result["newest_timestamp"].isoformat() if result["newest_timestamp"] else None
            ),
            "batches_fetched": result.get("batches_fetched", 0),
            "batch_limit_reached": result.get("batch_limit_reached", False),
            "days": days,
        }
    )


@require_GET
def api_flaggedrevs_statistics(request: HttpRequest) -> JsonResponse:
    wiki_code = request.GET.get("wiki")
    data_series = request.GET.get("series")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    queryset = FlaggedRevsStatistics.objects.select_related("wiki")

    if wiki_code:
        queryset = queryset.filter(wiki__code=wiki_code)

    if start_date:
        queryset = queryset.filter(date__gte=start_date)

    if end_date:
        queryset = queryset.filter(date__lte=end_date)

    statistics = queryset.order_by("date")

    data = []
    for stat in statistics:
        entry = {
            "wiki": stat.wiki.code,
            "date": stat.date.isoformat(),
            "totalPages_ns0": stat.total_pages_ns0,
            "syncedPages_ns0": stat.synced_pages_ns0,
            "reviewedPages_ns0": stat.reviewed_pages_ns0,
            "pendingLag_average": stat.pending_lag_average,
            "pendingChanges": stat.pending_changes,
        }

        if data_series:
            entry = {
                "wiki": entry["wiki"],
                "date": entry["date"],
                data_series: entry.get(data_series),
            }

        data.append(entry)

    return JsonResponse({"data": data})


@require_GET
def api_flaggedrevs_activity(request: HttpRequest) -> JsonResponse:
    wiki_code = request.GET.get("wiki")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    queryset = ReviewActivity.objects.select_related("wiki")

    if wiki_code:
        queryset = queryset.filter(wiki__code=wiki_code)

    if start_date:
        queryset = queryset.filter(date__gte=start_date)

    if end_date:
        queryset = queryset.filter(date__lte=end_date)

    activities = queryset.order_by("date")

    data = []
    for activity in activities:
        entry = {
            "wiki": activity.wiki.code,
            "date": activity.date.isoformat(),
            "number_of_reviewers": activity.number_of_reviewers,
            "number_of_reviews": activity.number_of_reviews,
            "number_of_pages": activity.number_of_pages,
            "reviews_per_reviewer": activity.reviews_per_reviewer,
        }
        data.append(entry)

    return JsonResponse({"data": data})


@require_GET
def api_flaggedrevs_months(request: HttpRequest) -> JsonResponse:
    months_data = (
        FlaggedRevsStatistics.objects.values_list("date", flat=True).distinct().order_by("-date")
    )

    months = []
    for date in months_data:
        month_value = date.strftime("%Y%m")

        if not any(m["value"] == month_value for m in months):
            months.append({"value": month_value, "label": month_value})

    return JsonResponse({"months": months})


def flaggedrevs_statistics_page(request: HttpRequest) -> HttpResponse:
    """Render the statistics visualization page."""
    wikis = Wiki.objects.all().order_by("code")
    wikis_json = json.dumps([{"code": w.code, "name": w.name} for w in wikis])
    return render(request, "reviews/flaggedrevs_statistics.html", {"wikis": wikis_json})
