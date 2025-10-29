from django.contrib import admin

from .models import (
    EditorProfile,
    FlaggedRevsStatistics,
    ModelScores,
    PendingPage,
    PendingRevision,
    ReviewActivity,
    RevisionAnnotation,
    Wiki,
    WikiConfiguration,
    WordAnnotation,
)
from .models.flaggedrevs_statistics import FlaggedRevsStatistics, ReviewActivity


@admin.register(Wiki)
class WikiAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "api_endpoint", "updated_at")
    search_fields = ("name", "code")


@admin.register(WikiConfiguration)
class WikiConfigurationAdmin(admin.ModelAdmin):
    list_display = ("wiki", "updated_at")
    search_fields = ("wiki__name", "wiki__code")


@admin.register(PendingPage)
class PendingPageAdmin(admin.ModelAdmin):
    list_display = ("title", "wiki", "pending_since", "stable_revid")
    search_fields = ("title",)
    list_filter = ("wiki",)


@admin.register(PendingRevision)
class PendingRevisionAdmin(admin.ModelAdmin):
    list_display = ("page", "revid", "user_name", "timestamp")
    search_fields = ("page__title", "user_name")
    list_filter = ("page__wiki",)


@admin.register(EditorProfile)
class EditorProfileAdmin(admin.ModelAdmin):
    list_display = ("username", "wiki", "is_blocked", "is_bot")
    search_fields = ("username",)
    list_filter = ("wiki", "is_blocked", "is_bot")


@admin.register(ModelScores)
class ModelScoresAdmin(admin.ModelAdmin):
    list_display = (
        "revision",
        "ores_damaging_score",
        "ores_goodfaith_score",
        "ores_fetched_at",
    )
    search_fields = ("revision__revid", "revision__page__title")
    list_filter = ("ores_fetched_at",)
    readonly_fields = ("ores_fetched_at",)


@admin.register(WordAnnotation)
class WordAnnotationAdmin(admin.ModelAdmin):
    list_display = (
        "page",
        "revision_id",
        "word",
        "author_user_name",
        "position",
        "is_moved",
        "is_deleted",
    )
    search_fields = ("word", "author_user_name", "stable_word_id")
    list_filter = ("page__wiki", "is_moved", "is_modified", "is_deleted")
    readonly_fields = ("created_at",)
    ordering = ("page", "revision_id", "position")


@admin.register(RevisionAnnotation)
class RevisionAnnotationAdmin(admin.ModelAdmin):
    list_display = (
        "page",
        "revision_id",
        "status",
        "words_annotated",
        "created_at",
        "completed_at",
    )
    search_fields = ("page__title",)
    list_filter = ("status", "page__wiki", "created_at")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)


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
