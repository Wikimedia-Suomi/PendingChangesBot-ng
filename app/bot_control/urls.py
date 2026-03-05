from django.urls import path

from . import views

app_name = "bot_control"

urlpatterns = [
    # Web UI
    path("", views.bot_control_page, name="control_panel"),
    path("audit-logs/", views.audit_logs_page, name="audit_logs"),
    # API endpoints
    path("api/start/", views.start_bot, name="api_start"),
    path("api/stop/", views.stop_bot, name="api_stop"),
    path("api/status/", views.get_status, name="api_status"),
    path("api/review/", views.manual_review, name="api_manual_review"),
    path("api/user/permissions/", views.get_user_permissions, name="api_user_permissions"),
    path("api/activity/", views.get_bot_activity, name="api_activity"),
    path("api/activity/summary/", views.get_bot_activity_summary, name="api_activity_summary"),
    path("api/audit-logs/", views.get_audit_logs, name="api_audit_logs"),
]
