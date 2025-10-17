from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("api/wikis/", views.api_wikis, name="api_wikis"),
    path("api/wikis/<int:pk>/refresh/", views.api_refresh, name="api_refresh"),
    path("api/wikis/<int:pk>/pending/", views.api_pending, name="api_pending"),
    path(
        "api/wikis/<int:pk>/pages/<int:pageid>/revisions/",
        views.api_page_revisions,
        name="api_page_revisions",
    ),
    path(
        "api/wikis/<int:pk>/pages/<int:pageid>/autoreview/",
        views.api_autoreview,
        name="api_autoreview",
    ),
    path("api/wikis/<int:pk>/clear/", views.api_clear_cache, name="api_clear_cache"),
    path("api/wikis/<int:pk>/configuration/", views.api_configuration, name="api_configuration"),
    path("api/wikis/fetch-diff/", views.fetch_diff, name="fetch_diff"),
    path("api/statistics/", views.api_statistics, name="api_statistics"),
    path(
        "api/statistics/available-months/", views.api_available_months, name="api_available_months"
    ),
    path("api/review-activity/", views.api_review_activity, name="api_review_activity"),
    path("statistics/", views.statistics_page, name="statistics_page"),
]
