from django.contrib import admin

from .models import EditorProfile, PendingPage, PendingRevision, Wiki, WikiConfiguration


@admin.register(Wiki)
class WikiAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "api_endpoint", "updated_at")
    search_fields = ("name", "code")


@admin.register(WikiConfiguration)
class WikiConfigurationAdmin(admin.ModelAdmin):
    list_display = ("wiki", "revertrisk_threshold", "updated_at")
    search_fields = ("wiki__name", "wiki__code")
    fields = ["wiki", "revertrisk_threshold"]


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
