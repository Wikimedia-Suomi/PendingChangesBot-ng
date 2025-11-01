from django.urls import path

from . import views

urlpatterns = [
    path("statistics/", views.statistics_page, name="statistics_page"),
    path("api/wikis/<int:pk>/statistics/", views.api_statistics, name="api_statistics"),
    path(
        "api/wikis/<int:pk>/statistics/charts/",
        views.api_statistics_charts,
        name="api_statistics_charts",
    ),
    path(
        "api/wikis/<int:pk>/statistics/refresh/",
        views.api_statistics_refresh,
        name="api_statistics_refresh",
    ),
    path(
        "api/wikis/<int:pk>/statistics/clear/",
        views.api_statistics_clear_and_reload,
        name="api_statistics_clear_and_reload",
    ),
    path(
        "api/flaggedrevs-statistics/",
        views.api_flaggedrevs_statistics,
        name="api_flaggedrevs_statistics",
    ),
    path(
        "api/flaggedrevs-statistics/available-months/",
        views.api_flaggedrevs_months,
        name="api_flaggedrevs_months",
    ),
    path(
        "api/flaggedrevs-activity/",
        views.api_flaggedrevs_activity,
        name="api_flaggedrevs_activity",
    ),
    path(
        "flaggedrevs-statistics/",
        views.flaggedrevs_statistics_page,
        name="flaggedrevs_statistics_page",
    ),
]
