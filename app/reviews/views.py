from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from http import HTTPStatus
from urllib.parse import urlencode


import requests
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .autoreview import run_autoreview_for_page
from .models import EditorProfile, PendingPage, Wiki, WikiConfiguration
from .services import WikiClient

logger = logging.getLogger(__name__)
CACHE_TTL = 60 * 60 * 1

VALIDATION_TIMEOUT = 8  # seconds
USER_AGENT = "PendingChangesBot/1.0 (https://github.com/Wikimedia-Suomi/PendingChangesBot-ng)"


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
        configuration.blocking_categories = blocking_categories
        configuration.auto_approved_groups = auto_groups
        configuration.save(
            update_fields=["blocking_categories", "auto_approved_groups", "updated_at"]
        )
    return JsonResponse(
        {
            "blocking_categories": configuration.blocking_categories,
            "auto_approved_groups": configuration.auto_approved_groups,
        }
    )

def fetch_diff(request):
    url = request.GET.get("url")
    if not url:
        return JsonResponse(
            {
                "error": "Missing 'url' parameter"
            }, status=400)

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



def liftwing_page(request):
    return render(request, "reviews/lift.html")

def test_endpoints_page(request):
    return render(request, "reviews/test_endpoints.html")

@csrf_exempt
def validate_article(request):
    """
    POST JSON: { "wiki": <wiki id|code|{id:,code:}>, "article": "Page title" }
    Response JSON: { "valid": bool, "exists": bool, "pageid": int|null,
        "normalized_title": str|null, "missing": bool, "error": null|str }
    """
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    article = payload.get("article")
    wiki_payload = payload.get("wiki")

    if not article or not isinstance(article, str) or not article.strip():
        return JsonResponse({"valid": False, "error": "Empty article title"}, status=200)

    try:
        wiki = _resolve_wiki_from_payload(wiki_payload)
    except LookupError as e:
        return JsonResponse({"valid": False, "error": str(e)}, status=400)

    api_endpoint = wiki.api_endpoint
    if not api_endpoint:
        return JsonResponse(
            {"valid": False, "error": "Wiki has no configured api_endpoint"}, status=500
        )

    params = {
        "action": "query",
        "format": "json",
        "formatversion": 2,
        "titles": article,
        "redirects": 1,
        "prop": "info",
    }

    # Build query URL safely
    if "?" not in api_endpoint:
        query_url = f"{api_endpoint}?{urlencode(params)}"
    else:
        query_url = f"{api_endpoint}&{urlencode(params)}"

    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(query_url, headers=headers, timeout=VALIDATION_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.exception("Failed to call MediaWiki API for validation: %s", exc)
        return JsonResponse(
            {"valid": False, "error": f"API request failed: {str(exc)}"},
            status=HTTPStatus.BAD_GATEWAY,
        )

    try:
        data = resp.json()
    except ValueError:
        logger.error("MediaWiki API returned non-json for %s", query_url)
        return JsonResponse(
            {"valid": False, "error": "API returned invalid JSON"},
            status=HTTPStatus.BAD_GATEWAY,
        )

    query = data.get("query", {})
    pages = query.get("pages", [])
    if not pages:
        return JsonResponse({"valid": False, "error": "Unexpected API response"}, status=500)

    page = pages[0]
    missing = bool(page.get("missing", False))
    normalized_title = page.get("title")
    pageid = page.get("pageid")

    result = {
        "valid": True,
        "exists": not missing,
        "missing": missing,
        "pageid": pageid if pageid is not None else None,
        "normalized_title": normalized_title,
        "error": None,
    }
    return JsonResponse(result, status=200)


def _resolve_wiki_from_payload(wiki_value):
    """
    Accept either integer pk, string code, or dictionary with 'id'/'code'.
    Returns Wiki instance or raises LookupError.
    """
    from .models import Wiki

    if wiki_value is None:
        raise LookupError("Missing wiki parameter")

    # If a dict was passed (from frontend), try keys
    if isinstance(wiki_value, dict):
        if "id" in wiki_value:
            try:
                return Wiki.objects.get(pk=int(wiki_value["id"]))
            except Exception:
                raise LookupError(f"Unknown wiki id {wiki_value['id']}")
        if "code" in wiki_value:
            try:
                return Wiki.objects.get(code=str(wiki_value["code"]))
            except Exception:
                raise LookupError(f"Unknown wiki code {wiki_value['code']}")

    # If numeric string or int -> assume pk
    try:
        pk = int(wiki_value)
        try:
            return Wiki.objects.get(pk=pk)
        except Exception:
            pass
    except Exception:
        pass

    # Otherwise assume code
    try:
        return Wiki.objects.get(code=str(wiki_value))
    except Exception:
        raise LookupError(f"Unknown wiki identifier: {wiki_value!r}")
    
@csrf_exempt
def fetch_revisions(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Invalid method"}, status=405)
    
    try:
        data = json.loads(request.body)
        wiki = data.get('wiki', 'en')
        article = data.get('article', '')
        
        if not article:
            return JsonResponse({"error": "Missing article parameter"}, status=400)
        
        base_url = f"https://{wiki}.wikipedia.org/w/api.php"
        headers = {"User-Agent": USER_AGENT}

        params = {
            "action": "query",
            "prop": "revisions",
            "titles": article,
            "rvlimit": "max",
            "rvprop": "ids|timestamp|user|comment",
            "format": "json"
        }

        revisions = []
        cont = True
        cont_token = None
        max_iterations = 10  # Prevent infinite loops

        while cont and max_iterations > 0:
            if cont_token:
                params['rvcontinue'] = cont_token

            try:
                response = requests.get(base_url, params=params, headers=headers, timeout=10)
                response.raise_for_status()
                api_data = response.json()
            except requests.exceptions.Timeout:
                return JsonResponse({"error": "Request to Wikipedia API timed out"}, status=504)
            except requests.exceptions.JSONDecodeError as e:
                return JsonResponse({"error": f"Invalid JSON from Wikipedia API: {str(e)}"}, status=500)
            except requests.exceptions.RequestException as e:
                return JsonResponse({"error": f"Wikipedia API error: {str(e)}"}, status=500)

            pages = api_data.get("query", {}).get("pages", {})
            for page_id, page_info in pages.items():
                revs = page_info.get("revisions", [])
                revisions.extend(revs)

            cont_token = api_data.get("continue", {}).get("rvcontinue")
            cont = bool(cont_token)
            max_iterations -= 1

        return JsonResponse({"title": article, "revisions": revisions})
    
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON in request body"}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)
    
@csrf_exempt
def fetch_liftwing_predictions(request):
    """
    POST JSON: { "wiki": "en", "model": "articlequality", "revisions": [12345, 67890] }
    Response: { "predictions": { "12345": {...}, "67890": {...} } }
    
    Optimized to use concurrent requests with ThreadPoolExecutor for parallel processing.
    Much faster than sequential requests.
    """
    data = json.loads(request.body)
    wiki = data.get("wiki", "en")
    model = data.get("model", "articlequality")
    revisions = data.get("revisions", [])

    if not revisions:
        return JsonResponse({"error": "Missing revisions list"}, status=400)

    # Base URL for LiftWing API
    base_url = f"https://api.wikimedia.org/service/lw/inference/v1/models/{wiki}wiki-{model}/predict"
    headers = {"User-Agent": USER_AGENT}
    
    def fetch_single_prediction(rev_id):
        """Fetch prediction for a single revision ID"""
        try:
            payload = {"rev_id": rev_id}
            resp = requests.post(base_url, json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
            result = resp.json()
            return (rev_id, result.get("output", result))
        except requests.exceptions.Timeout:
            return (rev_id, {"error": "Request timed out"})
        except requests.exceptions.HTTPError as e:
            return (rev_id, {"error": f"HTTP {e.response.status_code}: {str(e)}"})
        except Exception as e:
            return (rev_id, {"error": str(e)})
    
    predictions = {}
    
    # Use ThreadPoolExecutor for parallel requests (max 10 concurrent)
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Submit all tasks
        future_to_rev = {executor.submit(fetch_single_prediction, rev_id): rev_id 
                        for rev_id in revisions}
        
        # Collect results as they complete
        for future in as_completed(future_to_rev):
            rev_id, prediction = future.result()
            predictions[rev_id] = prediction

    return JsonResponse({"predictions": predictions})

@csrf_exempt
def fetch_predictions(request):
    """
    POST JSON: { "wiki": "en", "article": "Allu Arjun", "model": "articlequality" }
    Calls the LiftWing API to fetch predictions for an article.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    wiki = data.get("wiki", "en")
    article = data.get("article", "")
    model = data.get("model", "articlequality")

    if not article:
        return JsonResponse({"error": "Missing article title"}, status=400)

    # LiftWing API endpoint for model inference
    api_url = f"https://api.wikimedia.org/service/lw/inference/v1/models/{wiki}wiki-{model}/predict"

    # For simplicity, we fetch the latest revision ID of the article first
    rev_api = f"https://{wiki}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "titles": article,
        "prop": "revisions",
        "rvlimit": 1,
        "rvprop": "ids",
        "format": "json",
    }
    verify=False
    response = requests.get(
    "https://en.wikipedia.org/w/api.php",
    headers=headers,
    params=params
    )
    response.raise_for_status()
    

    try:
        rev_resp = requests.get(rev_api, params=params, timeout=10)
        rev_resp.raise_for_status()
        rev_data = rev_resp.json()
        pages = rev_data.get("query", {}).get("pages", {})
        rev_id = None
        for page_id, page_info in pages.items():
            if "revisions" in page_info:
                rev_id = page_info["revisions"][0]["revid"]
                break
    except Exception as e:
        return JsonResponse({"error": f"Failed to fetch revision ID: {e}"}, status=500)

    if not rev_id:
        return JsonResponse({"error": "No revision found for this article"}, status=404)

    # Call LiftWing API
    payload = {"rev_id": rev_id}
    headers = {"User-Agent": "PendingChangesBot/1.0 (LiftWingIntegration)"}

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        prediction = response.json()
        return JsonResponse({
            "wiki": wiki,
            "article": article,
            "rev_id": rev_id,
            "model": model,
            "prediction": prediction
        })
    except requests.RequestException as e:
        return JsonResponse({"error": f"LiftWing request failed: {str(e)}"}, status=500)

    

@require_GET
def liftwing_models(request, wiki_code):
    """Return available LiftWing models for the given wiki."""
    # For now, return a static list of available models
    models = [
        {
            "name": "articlequality",
            "version": "1.0.0",
            "description": "Predicts the quality class of Wikipedia articles"
        },
        {
            "name": "draftquality",
            "version": "1.0.0",
            "description": "Predicts the quality of new article drafts"
        }
    ]
    return JsonResponse({"models": models})
