from __future__ import annotations

import json
import logging
from http import HTTPStatus

import requests
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .autoreview import run_autoreview_for_page
from .models import (
    EditorProfile,
    PendingPage,
    Wiki,
    WikiConfiguration,
)
from .models.flaggedrevs_statistics import FlaggedRevsStatistics, ReviewActivity
from .services import WikiClient

logger = logging.getLogger(__name__)
CACHE_TTL = 60 * 60 * 1


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
        if request.content_type == "application/json":
            payload = json.loads(request.body.decode("utf-8")) if request.body else {}
        else:
            payload = request.POST.dict()

        blocking_categories = payload.get("blocking_categories", [])
        auto_groups = payload.get("auto_approved_groups", [])
        if isinstance(blocking_categories, str):
            blocking_categories = [blocking_categories]
        if isinstance(auto_groups, str):
            auto_groups = [auto_groups]

        ores_damaging_threshold = payload.get("ores_damaging_threshold")
        ores_goodfaith_threshold = payload.get("ores_goodfaith_threshold")
        ores_damaging_threshold_living = payload.get("ores_damaging_threshold_living")
        ores_goodfaith_threshold_living = payload.get("ores_goodfaith_threshold_living")

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


def statistics_page(request: HttpRequest) -> HttpResponse:
    """Render the statistics visualization page."""
    wikis = Wiki.objects.all().order_by("code")
    wikis_json = json.dumps([{"code": w.code, "name": w.name} for w in wikis])
    return render(request, "reviews/flaggedrevs_statistics.html", {"wikis": wikis_json})
