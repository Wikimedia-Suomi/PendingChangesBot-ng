import time

from django.utils import timezone

from .models import AuditLog

# Paths to skip logging (static files, health checks, etc.)
SKIP_PATHS = ("/static/", "/favicon.ico")


class AuditLogMiddleware:
    """Logs all HTTP requests to the AuditLog model for public transparency."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.monotonic()

        response = self.get_response(request)

        # Skip static file requests
        if any(request.path.startswith(p) for p in SKIP_PATHS):
            return response

        elapsed_ms = (time.monotonic() - start_time) * 1000

        username = (
            request.session.get("wiki_username", "anonymous")
            if hasattr(request, "session")
            else "anonymous"
        )

        from .permissions import get_user_role

        wiki_code = request.session.get("wiki_code", "fi") if hasattr(request, "session") else "fi"
        role = get_user_role(username, wiki_code).value if username != "anonymous" else "public"

        ip = self._get_client_ip(request)
        query_string = request.META.get("QUERY_STRING", "")

        try:
            AuditLog.objects.create(
                timestamp=timezone.now(),
                method=request.method,
                path=request.path[:2048],
                status_code=response.status_code,
                username=username,
                role=role,
                ip_address=ip if ip != "unknown" else None,
                query_params=query_string[:2048] if query_string else "",
                response_time_ms=round(elapsed_ms, 2),
            )
        except Exception:  # noqa: S110
            # Never let audit logging break the request
            pass

        return response

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "unknown")
