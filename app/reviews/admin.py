from django.contrib import admin

from .models import (
    ArticleRevisionHistory,
    EditorProfile,
    LiftWingPrediction,
    ModelScores,
    PendingPage,
    PendingRevision,
    Wiki,
    WikiConfiguration,
)


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


@admin.register(LiftWingPrediction)
class LiftWingPredictionAdmin(admin.ModelAdmin):
    list_display = ("revid", "wiki", "model_name", "fetched_at")
    search_fields = ("revid", "model_name")
    list_filter = ("wiki", "model_name", "fetched_at")
    readonly_fields = ("fetched_at",)


@admin.register(ArticleRevisionHistory)
class ArticleRevisionHistoryAdmin(admin.ModelAdmin):
    list_display = ("page_title", "wiki", "created_at")
    search_fields = ("page_title",)
    list_filter = ("wiki", "created_at")
    readonly_fields = ("created_at",)


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
