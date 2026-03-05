from __future__ import annotations

import csv
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from http import HTTPStatus
from io import StringIO

from django.db.models import Count
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods
from reviews.models import EditorProfile, Wiki, WikiConfiguration
from reviews.services import WikiClient

from .direct_sql_services import get_direct_sql_client
from .models import (
    FlaggedRevsStatistics,
    ReviewActivity,
    ReviewStatisticsCache,
    ReviewStatisticsMetadata,
)

logger = logging.getLogger(__name__)
CACHE_TTL = 60 * 60 * 1


def _parse_timestamp(timestamp_value) -> datetime | None:
    """Parse MediaWiki timestamp format (YYYYMMDDHHMMSS)."""
    if timestamp_value is None:
        return None
    try:
        # Handle both string and integer formats
        if isinstance(timestamp_value, bytes):
            timestamp_str = timestamp_value.decode("utf-8")
        else:
            timestamp_str = str(timestamp_value)

        # Remove any whitespace
        timestamp_str = timestamp_str.strip()

        if len(timestamp_str) == 14:
            return datetime.strptime(timestamp_str, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        pass
    return None


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


def _get_wiki(pk: int) -> Wiki:
    wiki = get_object_or_404(Wiki, pk=pk)
    WikiConfiguration.objects.get_or_create(wiki=wiki)
    return wiki


def statistics_page(request: HttpRequest) -> HttpResponse:
    """Render the standalone statistics page."""
    from reviews.views import index  # Avoid circular import

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
        "review_statistics/statistics.html",
        {
            "initial_wikis": json.dumps(payload),
        },
    )


@require_GET
def api_statistics(request: HttpRequest, pk: int) -> JsonResponse:
    """Get cached review statistics for a wiki."""
    wiki = _get_wiki(pk)

    # Get metadata
    try:
        metadata = ReviewStatisticsMetadata.objects.get(wiki=wiki)
        metadata_payload = {
            "last_refreshed_at": metadata.last_refreshed_at.isoformat(),
            "last_data_loaded_at": (
                metadata.last_data_loaded_at.isoformat() if metadata.last_data_loaded_at else None
            ),
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
            "last_data_loaded_at": None,
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
    reviewers_by_date: defaultdict[str, set] = defaultdict(set)
    pending_by_date: defaultdict[str, int] = defaultdict(int)
    delays_by_date: defaultdict[str, list] = defaultdict(list)

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
        {"date": date, "avg_delay": sum(d for d in delays if d >= 0) / max(1, sum(1 for d in delays if d >= 0))}
        for date, delays in sorted(delays_by_date.items())
    ]

    delay_percentiles = [
        {
            "date": date,
            "p10": calculate_percentile([d for d in delays if d >= 0], 10),
            "p50": calculate_percentile([d for d in delays if d >= 0], 50),
            "p90": calculate_percentile([d for d in delays if d >= 0], 90),
        }
        for date, delays in sorted(delays_by_date.items())
    ]

    # Calculate overall statistics (exclude negative delays from bad legacy data)
    all_delays = [delay for delays in delays_by_date.values() for delay in delays if delay >= 0]
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
    """Incrementally refresh review statistics for a wiki using direct SQL."""
    from django.db import transaction

    wiki = _get_wiki(pk)

    try:
        # Get metadata for incremental loading
        metadata, _ = ReviewStatisticsMetadata.objects.get_or_create(wiki=wiki)
        min_log_id = metadata.max_log_id

        # Create direct SQL client
        sql_client = get_direct_sql_client(wiki)

        # Fetch new records (limit to 10k per refresh)
        limit = 10000
        payload = sql_client.fetch_review_statistics_from_logging(
            limit=limit,
            min_log_id=min_log_id,
        )

        if not payload:
            return JsonResponse(
                {
                    "total_records": metadata.total_records,
                    "oldest_timestamp": (
                        metadata.oldest_review_timestamp.isoformat()
                        if metadata.oldest_review_timestamp
                        else None
                    ),
                    "newest_timestamp": (
                        metadata.newest_review_timestamp.isoformat()
                        if metadata.newest_review_timestamp
                        else None
                    ),
                    "is_incremental": True,
                    "batches_fetched": 0,
                    "batch_limit_reached": False,
                }
            )

        saved_count = 0
        max_log_id = min_log_id or 0

        with transaction.atomic():
            for entry in payload:
                try:
                    log_id = entry.get("log_id")
                    if log_id:
                        max_log_id = max(max_log_id, log_id)

                    # Parse timestamps
                    reviewed_timestamp_str = entry.get("reviewed_timestamp")
                    pending_timestamp_str = entry.get("pending_timestamp")

                    if not reviewed_timestamp_str or not pending_timestamp_str:
                        continue

                    reviewed_timestamp = _parse_timestamp(reviewed_timestamp_str)
                    pending_timestamp = _parse_timestamp(pending_timestamp_str)

                    if not reviewed_timestamp or not pending_timestamp:
                        continue

                    # Create or update record
                    ReviewStatisticsCache.objects.update_or_create(
                        wiki=wiki,
                        reviewed_revision_id=entry.get("reviewed_revision_id"),
                        defaults={
                            "reviewer_name": entry.get("reviewer_name", ""),
                            "reviewed_user_name": entry.get("reviewed_user_name", ""),
                            "page_title": entry.get("page_title", ""),
                            "page_id": entry.get("page_id", 0),
                            "pending_revision_id": entry.get("pending_revision_id", 0),
                            "reviewed_timestamp": reviewed_timestamp,
                            "pending_timestamp": pending_timestamp,
                            "review_delay_days": entry.get("review_delay_days", 0),
                        },
                    )
                    saved_count += 1

                except Exception as e:
                    logger.warning(f"Failed to process entry: {e}")
                    continue

            # Update metadata
            metadata.max_log_id = max_log_id
            metadata.total_records = ReviewStatisticsCache.objects.filter(wiki=wiki).count()
            metadata.last_data_loaded_at = timezone.now()

            # Update oldest/newest timestamps
            oldest = (
                ReviewStatisticsCache.objects.filter(wiki=wiki)
                .order_by("reviewed_timestamp")
                .first()
            )
            newest = (
                ReviewStatisticsCache.objects.filter(wiki=wiki)
                .order_by("-reviewed_timestamp")
                .first()
            )
            if oldest:
                metadata.oldest_review_timestamp = oldest.reviewed_timestamp
            if newest:
                metadata.newest_review_timestamp = newest.reviewed_timestamp

            metadata.save()

        return JsonResponse(
            {
                "total_records": metadata.total_records,
                "oldest_timestamp": (
                    metadata.oldest_review_timestamp.isoformat()
                    if metadata.oldest_review_timestamp
                    else None
                ),
                "newest_timestamp": (
                    metadata.newest_review_timestamp.isoformat()
                    if metadata.newest_review_timestamp
                    else None
                ),
                "is_incremental": True,
                "batches_fetched": 1 if saved_count > 0 else 0,
                "batch_limit_reached": saved_count >= limit,
            }
        )

    except Exception as exc:
        logger.exception("Failed to refresh statistics for %s", wiki.code)
        return JsonResponse(
            {"error": str(exc)},
            status=HTTPStatus.BAD_GATEWAY,
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

    months: list[dict[str, str]] = []
    for date in months_data:
        month_value = date.strftime("%Y%m")

        if not any(m["value"] == month_value for m in months):
            months.append({"value": month_value, "label": month_value})

    return JsonResponse({"months": months})


def flaggedrevs_statistics_page(request: HttpRequest) -> HttpResponse:
    """Render the statistics visualization page."""
    wikis = Wiki.objects.all().order_by("code")
    wikis_json = json.dumps([{"code": w.code, "name": w.name} for w in wikis])
    return render(request, "review_statistics/flaggedrevs_statistics.html", {"wikis": wikis_json})


@require_GET
def api_statistics_export(request: HttpRequest, pk: int) -> HttpResponse:
    """Export review statistics for a wiki in JSON or CSV format.

    Query parameters:
        format: 'json' (default) or 'csv'
        reviewer: Filter by reviewer username
        reviewed_user: Filter by reviewed user username
        time_filter: 'all' (default), 'day', or 'week'
        exclude_auto_reviewers: 'true' or 'false' (default)
        limit: Maximum number of records (default: 10000)
    """
    wiki = _get_wiki(pk)

    # Get filter parameters
    export_format = request.GET.get("format", "json").lower()
    reviewer_filter = request.GET.get("reviewer", "").strip()
    reviewed_user_filter = request.GET.get("reviewed_user", "").strip()
    time_filter = request.GET.get("time_filter", "all").strip()
    exclude_auto_reviewers = request.GET.get("exclude_auto_reviewers", "false").lower() == "true"
    limit = min(int(request.GET.get("limit", 10000)), 50000)  # Cap at 50k records

    # Build query
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
        auto_reviewers = EditorProfile.objects.filter(wiki=wiki, is_autoreviewed=True).values_list(
            "username", flat=True
        )
        statistics_qs = statistics_qs.exclude(reviewed_user_name__in=auto_reviewers)

    # Get records - use only() to fetch only needed fields for better performance
    records = statistics_qs.only(
        "reviewer_name",
        "reviewed_user_name",
        "page_title",
        "page_id",
        "reviewed_revision_id",
        "pending_revision_id",
        "reviewed_timestamp",
        "pending_timestamp",
        "review_delay_days",
    ).order_by("-reviewed_timestamp")[:limit]

    # Build data list
    data = [
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

    if export_format == "csv":
        return _export_csv(
            data,
            filename=f"review_statistics_{wiki.code}.csv",
            fieldnames=[
                "reviewer_name",
                "reviewed_user_name",
                "page_title",
                "page_id",
                "reviewed_revision_id",
                "pending_revision_id",
                "reviewed_timestamp",
                "pending_timestamp",
                "review_delay_days",
            ],
        )

    # Default to JSON
    response = JsonResponse({"wiki": wiki.code, "records": data, "count": len(data)})
    response["Content-Disposition"] = f'attachment; filename="review_statistics_{wiki.code}.json"'
    return response


@require_GET
def api_flaggedrevs_statistics_export(request: HttpRequest) -> HttpResponse:
    """Export FlaggedRevs statistics in JSON or CSV format.

    Query parameters:
        format: 'json' (default) or 'csv'
        wiki: Filter by wiki code
        start_date: Start date filter (YYYY-MM-DD)
        end_date: End date filter (YYYY-MM-DD)
    """
    export_format = request.GET.get("format", "json").lower()
    wiki_code = request.GET.get("wiki")
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

    data = [
        {
            "wiki": stat.wiki.code,
            "date": stat.date.isoformat(),
            "total_pages_ns0": stat.total_pages_ns0,
            "synced_pages_ns0": stat.synced_pages_ns0,
            "reviewed_pages_ns0": stat.reviewed_pages_ns0,
            "pending_lag_average": stat.pending_lag_average,
            "pending_changes": stat.pending_changes,
        }
        for stat in statistics
    ]

    if export_format == "csv":
        filename = f"flaggedrevs_statistics_{wiki_code or 'all'}.csv"
        return _export_csv(
            data,
            filename=filename,
            fieldnames=[
                "wiki",
                "date",
                "total_pages_ns0",
                "synced_pages_ns0",
                "reviewed_pages_ns0",
                "pending_lag_average",
                "pending_changes",
            ],
        )

    # Default to JSON
    response = JsonResponse({"data": data, "count": len(data)})
    filename = f"flaggedrevs_statistics_{wiki_code or 'all'}.json"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@require_GET
def api_flaggedrevs_activity_export(request: HttpRequest) -> HttpResponse:
    """Export FlaggedRevs activity data in JSON or CSV format.

    Query parameters:
        format: 'json' (default) or 'csv'
        wiki: Filter by wiki code
        start_date: Start date filter (YYYY-MM-DD)
        end_date: End date filter (YYYY-MM-DD)
    """
    export_format = request.GET.get("format", "json").lower()
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

    data = [
        {
            "wiki": activity.wiki.code,
            "date": activity.date.isoformat(),
            "number_of_reviewers": activity.number_of_reviewers,
            "number_of_reviews": activity.number_of_reviews,
            "number_of_pages": activity.number_of_pages,
            "reviews_per_reviewer": activity.reviews_per_reviewer,
        }
        for activity in activities
    ]

    if export_format == "csv":
        filename = f"flaggedrevs_activity_{wiki_code or 'all'}.csv"
        return _export_csv(
            data,
            filename=filename,
            fieldnames=[
                "wiki",
                "date",
                "number_of_reviewers",
                "number_of_reviews",
                "number_of_pages",
                "reviews_per_reviewer",
            ],
        )

    # Default to JSON
    response = JsonResponse({"data": data, "count": len(data)})
    filename = f"flaggedrevs_activity_{wiki_code or 'all'}.json"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _export_csv(data: list[dict], filename: str, fieldnames: list[str]) -> HttpResponse:
    """Helper function to export data as CSV."""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(data)

    response = HttpResponse(output.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
