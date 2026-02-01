import json
import os
import signal
import subprocess
import sys
from pathlib import Path

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import BotStatus
from .permissions import UserRole, require_permission, get_user_info


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
    username = request.META.get("HTTP_X_WIKI_USERNAME")
    wiki_code = request.META.get("HTTP_X_WIKI_CODE", "fi")

    if not username:
        # Return public user permissions
        return JsonResponse({
            "username": None,
            "wiki": f"{wiki_code}.wikipedia",
            "role": "public",
            "groups": [],
            "permissions": {
                "can_start_stop_bot": False,
                "can_manual_review": False,
                "can_change_settings": False,
                "can_view_status": True,
            }
        })

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
