import logging

from django.utils import timezone

logger = logging.getLogger("audit_log")


class AuditLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        timestamp = timezone.now().isoformat()
        method = request.method
        path = request.path
        ip = self._get_client_ip(request)
        username = request.META.get("HTTP_X_WIKI_USERNAME") or "anonymous"

        from .permissions import get_user_role

        wiki_code = request.META.get("HTTP_X_WIKI_CODE", "fi")
        role = (
            get_user_role(username, wiki_code).name.lower() if username != "anonymous" else "public"
        )

        response = self.get_response(request)

        logger.info(
            "AUDIT: timestamp=%s | user=%s | role=%s | method=%s | path=%s | status=%s | ip=%s",
            timestamp,
            username,
            role,
            method,
            path,
            response.status_code,
            ip,
        )

        return response

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "unknown")
