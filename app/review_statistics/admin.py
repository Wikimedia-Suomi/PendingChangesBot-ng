from django.contrib import admin

from .models import (
    FlaggedRevsStatistics,
    ReviewActivity,
    ReviewStatisticsCache,
    ReviewStatisticsMetadata,
)


@admin.register(FlaggedRevsStatistics)
class FlaggedRevsStatisticsAdmin(admin.ModelAdmin):
    list_display = (
        "wiki",
        "date",
        "total_pages_ns0",
        "reviewed_pages_ns0",
        "synced_pages_ns0",
        "pending_changes",
        "pending_lag_average",
    )
    search_fields = ("wiki__name", "wiki__code")
    list_filter = ("wiki", "date")


@admin.register(ReviewActivity)
class ReviewActivityAdmin(admin.ModelAdmin):
    list_display = (
        "wiki",
        "date",
        "number_of_reviewers",
        "number_of_reviews",
        "number_of_pages",
        "reviews_per_reviewer",
    )
    search_fields = ("wiki__name", "wiki__code")
    list_filter = ("wiki", "date")


@admin.register(ReviewStatisticsCache)
class ReviewStatisticsCacheAdmin(admin.ModelAdmin):
    list_display = (
        "wiki",
        "reviewer_name",
        "reviewed_user_name",
        "page_title",
        "reviewed_timestamp",
        "review_delay_days",
    )
    search_fields = ("reviewer_name", "reviewed_user_name", "page_title")
    list_filter = ("wiki", "reviewed_timestamp")
    readonly_fields = ("fetched_at",)


@admin.register(ReviewStatisticsMetadata)
class ReviewStatisticsMetadataAdmin(admin.ModelAdmin):
    list_display = (
        "wiki",
        "last_refreshed_at",
        "last_data_loaded_at",
        "total_records",
        "oldest_review_timestamp",
        "newest_review_timestamp",
    )
    search_fields = ("wiki__name", "wiki__code")
    list_filter = ("last_refreshed_at", "last_data_loaded_at")
    readonly_fields = ("last_refreshed_at",)
