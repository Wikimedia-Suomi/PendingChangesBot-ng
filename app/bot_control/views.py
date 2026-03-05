import json
import os
import signal
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

# Re-usable Q import for complex lookups
from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .models import AuditLog, BotActivity, BotStatus
from .permissions import UserRole, get_user_info, require_permission


def bot_control_page(request):
    """Render the bot control panel page"""
    return render(request, "bot_control/control_panel.html")


@csrf_exempt  # TODO: Add proper CSRF protection in production
@require_http_methods(["POST"])
@require_permission(UserRole.ADMIN)
def start_bot(request):
    """Start the bot process (requires ADMIN role)"""
    bot_status = BotStatus.get_current_status()

    if bot_status.is_running:
        return JsonResponse({"error": "Bot is already running"}, status=400)

    try:
        # Get the bot runner script path
        bot_script = Path(__file__).parent / "bot_runner.py"

        # Create log directory for bot output
        log_dir = Path(__file__).parent.parent.parent / "logs"
        log_dir.mkdir(exist_ok=True)
        stdout_log = log_dir / "bot_stdout.log"
        stderr_log = log_dir / "bot_stderr.log"

        # Start the bot as a background process
        # Redirect stdout and stderr to log files
        with open(stdout_log, "a") as stdout_file, open(stderr_log, "a") as stderr_file:
            process = subprocess.Popen(  # noqa: S603
                [sys.executable, str(bot_script)],
                stdout=stdout_file,
                stderr=stderr_file,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )

        # Update database status
        bot_status.is_running = True
        bot_status.process_id = process.pid
        bot_status.started_at = timezone.now()
        bot_status.stopped_at = None
        bot_status.error_message = ""
        bot_status.last_activity = timezone.now()
        bot_status.save()

        return JsonResponse(
            {
                "message": f"Bot started successfully! Process ID: {process.pid}",
                "status": {
                    "is_running": bot_status.is_running,
                    "started_at": bot_status.started_at.isoformat()
                    if bot_status.started_at
                    else None,
                    "stopped_at": bot_status.stopped_at.isoformat()
                    if bot_status.stopped_at
                    else None,
                    "error_message": bot_status.error_message,
                },
            }
        )
    except Exception as e:
        return JsonResponse({"error": f"Failed to start bot: {str(e)}"}, status=500)


@csrf_exempt  # TODO: Add proper CSRF protection in production
@require_http_methods(["POST"])
@require_permission(UserRole.ADMIN)
def stop_bot(request):
    """Stop the bot process (requires ADMIN role)"""
    bot_status = BotStatus.get_current_status()

    if not bot_status.is_running:
        return JsonResponse({"error": "Bot is not running"}, status=400)

    try:
        # First, set the flag so the bot stops gracefully
        bot_status.is_running = False
        bot_status.stopped_at = timezone.now()
        bot_status.last_activity = timezone.now()
        bot_status.save()

        # If we have a PID, try to terminate the process
        if bot_status.process_id:
            try:
                if os.name == "nt":  # Windows
                    # On Windows, send CTRL_BREAK_EVENT
                    os.kill(bot_status.process_id, signal.CTRL_BREAK_EVENT)
                else:  # Unix/Linux
                    os.kill(bot_status.process_id, signal.SIGTERM)
            except ProcessLookupError:
                # Process already dead, that's fine
                pass
            except Exception as e:
                # Log the error but continue (the flag is already set)
                print(f"Warning: Could not kill process {bot_status.process_id}: {e}")

        bot_status.process_id = None
        bot_status.save()

        return JsonResponse(
            {
                "message": "Bot stopped successfully!",
                "status": {
                    "is_running": bot_status.is_running,
                    "started_at": bot_status.started_at.isoformat()
                    if bot_status.started_at
                    else None,
                    "stopped_at": bot_status.stopped_at.isoformat()
                    if bot_status.stopped_at
                    else None,
                    "error_message": bot_status.error_message,
                },
            }
        )
    except Exception as e:
        return JsonResponse({"error": f"Failed to stop bot: {str(e)}"}, status=500)


@require_http_methods(["GET"])
def get_status(request):
    """Get current bot status (public endpoint)"""
    bot_status = BotStatus.get_current_status()

    return JsonResponse(
        {
            "is_running": bot_status.is_running,
            "process_id": bot_status.process_id,
            "started_at": bot_status.started_at.isoformat() if bot_status.started_at else None,
            "stopped_at": bot_status.stopped_at.isoformat() if bot_status.stopped_at else None,
            "last_activity": bot_status.last_activity.isoformat()
            if bot_status.last_activity
            else None,
            "error_message": bot_status.error_message,
        }
    )


@require_http_methods(["GET"])
def get_user_permissions(request):
    """Get current user's role and permissions"""
    username = request.session.get("wiki_username")
    wiki_code = request.session.get("wiki_code", "fi")

    if not username:
        # Return public user permissions
        return JsonResponse(
            {
                "username": None,
                "wiki": f"{wiki_code}.wikipedia",
                "role": "public",
                "groups": [],
                "permissions": {
                    "can_start_stop_bot": False,
                    "can_manual_review": False,
                    "can_change_settings": False,
                    "can_view_status": True,
                },
            }
        )

    # Get authenticated user's permissions
    user_info = get_user_info(username, wiki_code)
    return JsonResponse(user_info)


@csrf_exempt  # TODO: Add proper CSRF protection in production
@require_http_methods(["POST"])
@require_permission(UserRole.REVIEWER)
def manual_review(request):
    """Manually trigger a review for a specific page (requires REVIEWER role)"""
    try:
        # Parse request body
        data = json.loads(request.body)
        page_title = data.get("page_title", "").strip()
        revision_id = data.get("revision_id", "").strip()
        wiki = data.get("wiki", "fi")  # Default to Finnish Wikipedia

        # Validation
        if not page_title:
            return JsonResponse({"error": "page_title is required"}, status=400)

        # TODO: Add actual validation
        # - Check if page exists on the wiki
        # - Check if revision exists (if provided)
        # - Check if FlaggedRevs is enabled on the wiki
        # - Check user permissions

        # TODO: Implement actual review logic
        # For now, just simulate success
        result = {
            "status": "success",
            "message": f"Manual review triggered for page: {page_title}",
            "page_title": page_title,
            "revision_id": revision_id if revision_id else "latest",
            "wiki": wiki,
            "reviewed": False,  # TODO: Set to True when actually reviewed
            "note": "TODO: Implement actual FlaggedRevs review logic",
        }

        return JsonResponse(result)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON in request body"}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Failed to trigger manual review: {str(e)}"}, status=500)


@require_GET
def get_bot_activity(request):
    """Get bot activity records for display in statistics"""
    wiki = request.GET.get("wiki", "").strip()
    decision = request.GET.get("decision", "").strip()
    limit = min(int(request.GET.get("limit", 100)), 500)

    queryset = BotActivity.objects.all()

    if wiki:
        queryset = queryset.filter(wiki_code=wiki)

    if decision:
        queryset = queryset.filter(decision=decision)

    activities = queryset[:limit]

    records = [
        {
            "wiki_code": activity.wiki_code,
            "page_id": activity.page_id,
            "page_title": activity.page_title,
            "revision_id": activity.revision_id,
            "user_name": activity.user_name,
            "decision": activity.decision,
            "decision_label": activity.decision_label,
            "decision_reason": activity.decision_reason,
            "determining_check": activity.determining_check,
            "total_checks_run": activity.total_checks_run,
            "execution_time_ms": activity.execution_time_ms,
            "created_at": activity.created_at.isoformat(),
            "is_dry_run": activity.is_dry_run,
        }
        for activity in activities
    ]

    return JsonResponse({"activities": records, "count": len(records)})


@require_GET
def get_bot_activity_summary(request):
    """Get summary statistics of bot activity for charts"""
    wiki = request.GET.get("wiki", "").strip()
    days = int(request.GET.get("days", 7))

    cutoff = timezone.now() - timedelta(days=days)

    queryset = BotActivity.objects.filter(created_at__gte=cutoff)

    if wiki:
        queryset = queryset.filter(wiki_code=wiki)

    # Decision breakdown
    decision_counts = queryset.values("decision").annotate(count=Count("id")).order_by("-count")

    # Activity by day
    daily_activity = (
        queryset.annotate(date=TruncDate("created_at"))
        .values("date")
        .annotate(count=Count("id"))
        .order_by("date")
    )

    # Top determining checks
    top_checks = (
        queryset.exclude(determining_check="")
        .values("determining_check")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )

    # Total stats
    total_activities = queryset.count()
    approved_count = queryset.filter(decision="approve").count()
    blocked_count = queryset.filter(decision="blocked").count()
    manual_count = queryset.filter(decision="manual").count()

    return JsonResponse(
        {
            "summary": {
                "total": total_activities,
                "approved": approved_count,
                "blocked": blocked_count,
                "manual": manual_count,
                "days": days,
            },
            "decision_breakdown": list(decision_counts),
            "daily_activity": [
                {"date": item["date"].isoformat(), "count": item["count"]}
                for item in daily_activity
            ],
            "top_checks": list(top_checks),
        }
    )


def audit_logs_page(request):
    """Render the public audit logs page"""
    return render(request, "bot_control/audit_logs.html")


@require_GET
def get_audit_logs(request):
    """
    Search and filter audit logs. Public endpoint.

    Query params:
        q: Search term (matches path, username, or role)
        method: Filter by HTTP method (GET, POST, etc.)
        status: Filter by status code range (2xx, 3xx, 4xx, 5xx)
        user: Filter by username
        date_from: ISO date string (YYYY-MM-DD)
        date_to: ISO date string (YYYY-MM-DD)
        sort: Field to sort by (timestamp, method, path, status_code, username, response_time_ms)
        order: Sort direction (asc or desc, default desc)
        page: Page number (default 1)
        per_page: Results per page (default 50, max 200)
    """
    queryset = AuditLog.objects.all()

    # Full-text search across path, username, and role
    q = request.GET.get("q", "").strip()
    if q:
        queryset = queryset.filter(
            Q(path__icontains=q) | Q(username__icontains=q) | Q(role__icontains=q)
        )

    # Filter by HTTP method
    method = request.GET.get("method", "").strip().upper()
    if method:
        queryset = queryset.filter(method=method)

    # Filter by status code range
    status = request.GET.get("status", "").strip()
    if status == "2xx":
        queryset = queryset.filter(status_code__gte=200, status_code__lt=300)
    elif status == "3xx":
        queryset = queryset.filter(status_code__gte=300, status_code__lt=400)
    elif status == "4xx":
        queryset = queryset.filter(status_code__gte=400, status_code__lt=500)
    elif status == "5xx":
        queryset = queryset.filter(status_code__gte=500, status_code__lt=600)

    # Filter by username
    user = request.GET.get("user", "").strip()
    if user:
        queryset = queryset.filter(username__icontains=user)

    # Date range filters
    date_from = request.GET.get("date_from", "").strip()
    if date_from:
        queryset = queryset.filter(timestamp__date__gte=date_from)

    date_to = request.GET.get("date_to", "").strip()
    if date_to:
        queryset = queryset.filter(timestamp__date__lte=date_to)

    # Sorting
    allowed_sort_fields = {
        "timestamp",
        "method",
        "path",
        "status_code",
        "username",
        "response_time_ms",
    }
    sort_field = request.GET.get("sort", "timestamp").strip()
    if sort_field not in allowed_sort_fields:
        sort_field = "timestamp"
    sort_order = request.GET.get("order", "desc").strip().lower()
    order_prefix = "-" if sort_order == "desc" else ""
    queryset = queryset.order_by(f"{order_prefix}{sort_field}")

    # Pagination
    page = max(int(request.GET.get("page", 1)), 1)
    per_page = min(int(request.GET.get("per_page", 50)), 200)
    total = queryset.count()
    offset = (page - 1) * per_page
    logs = queryset[offset : offset + per_page]

    records = [
        {
            "timestamp": log.timestamp.isoformat(),
            "method": log.method,
            "path": log.path,
            "status_code": log.status_code,
            "username": log.username,
            "role": log.role,
            "query_params": log.query_params,
            "response_time_ms": log.response_time_ms,
        }
        for log in logs
    ]

    return JsonResponse(
        {
            "logs": records,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": (total + per_page - 1) // per_page if per_page else 1,
            },
        }
    )


def activity_timeline_page(request):
    """Render the public activity timeline page"""
    return render(request, "bot_control/activity_timeline.html")


@require_GET
def get_activity_timeline(request):
    """
    Get a unified activity timeline combining audit logs and bot decisions.
    Public read-only endpoint.

    Query params:
        days: Number of days to look back (default 7, max 30)
        type: Filter by event type (audit, bot, or all)
        page: Page number (default 1)
        per_page: Results per page (default 50, max 200)
    """
    days = min(int(request.GET.get("days", 7)), 30)
    event_type = request.GET.get("type", "all").strip()
    page = max(int(request.GET.get("page", 1)), 1)
    per_page = min(int(request.GET.get("per_page", 50)), 200)

    cutoff = timezone.now() - timedelta(days=days)
    events = []

    # Gather audit log events
    if event_type in ("all", "audit"):
        audit_logs = AuditLog.objects.filter(timestamp__gte=cutoff).order_by("-timestamp")
        for log in audit_logs[:500]:
            events.append(
                {
                    "type": "request",
                    "timestamp": log.timestamp.isoformat(),
                    "icon": "🌐",
                    "summary": f"{log.method} {log.path}",
                    "detail": {
                        "status_code": log.status_code,
                        "username": log.username,
                        "role": log.role,
                        "response_time_ms": log.response_time_ms,
                    },
                }
            )

    # Gather bot activity events
    if event_type in ("all", "bot"):
        bot_activities = BotActivity.objects.filter(created_at__gte=cutoff).order_by("-created_at")
        for activity in bot_activities[:500]:
            icon = {"approve": "✅", "blocked": "🚫", "manual": "👁️"}.get(activity.decision, "⚙️")
            events.append(
                {
                    "type": "bot_decision",
                    "timestamp": activity.created_at.isoformat(),
                    "icon": icon,
                    "summary": f"{activity.get_decision_display()} — {activity.page_title}",
                    "detail": {
                        "wiki": activity.wiki_code,
                        "page_id": activity.page_id,
                        "revision_id": activity.revision_id,
                        "user_name": activity.user_name,
                        "decision": activity.decision,
                        "reason": activity.decision_reason,
                        "check": activity.determining_check,
                        "execution_time_ms": activity.execution_time_ms,
                        "dry_run": activity.is_dry_run,
                    },
                }
            )

    # Sort combined events by timestamp descending
    events.sort(key=lambda e: e["timestamp"], reverse=True)

    # Summary stats
    total_requests = AuditLog.objects.filter(timestamp__gte=cutoff).count()
    total_bot_actions = BotActivity.objects.filter(created_at__gte=cutoff).count()
    avg_response = AuditLog.objects.filter(
        timestamp__gte=cutoff, response_time_ms__isnull=False
    ).aggregate(avg=Avg("response_time_ms"))["avg"]

    total = len(events)
    offset = (page - 1) * per_page
    page_events = events[offset : offset + per_page]

    return JsonResponse(
        {
            "events": page_events,
            "summary": {
                "days": days,
                "total_requests": total_requests,
                "total_bot_actions": total_bot_actions,
                "avg_response_ms": round(avg_response, 1) if avg_response else None,
            },
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": (total + per_page - 1) // per_page if per_page else 1,
            },
        }
    )
