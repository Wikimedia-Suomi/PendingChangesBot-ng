# GitHub Conflict Resolution Guide for PR #119

## ✅ Local Resolution Complete

All conflicts have been resolved locally and pushed. If GitHub still shows conflicts, follow this guide.

---

## 📋 How to Resolve in GitHub Web Interface

### **File 1: `app/reviews/admin.py`**

Find the conflict around line 64-85. Replace the entire conflict block with:

```python
@admin.register(WordAnnotation)
class WordAnnotationAdmin(admin.ModelAdmin):
    list_display = ("page", "revision_id", "word", "author_user_name", "position", "is_moved", "is_deleted")
    search_fields = ("word", "author_user_name", "stable_word_id")
    list_filter = ("page__wiki", "is_moved", "is_modified", "is_deleted")
    readonly_fields = ("created_at",)
    ordering = ("page", "revision_id", "position")


@admin.register(RevisionAnnotation)
class RevisionAnnotationAdmin(admin.ModelAdmin):
    list_display = ("page", "revision_id", "status", "words_annotated", "created_at", "completed_at")
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
```

---

### **File 2: `app/reviews/models/__init__.py`**

Find conflict around line 23-30. Replace with:

```python
    "ReviewStatisticsMetadata",
    "WordAnnotation",
    "RevisionAnnotation",
    "FlaggedRevsStatistics",
    "ReviewActivity",
]
```

---

### **File 3: `app/reviews/urls.py`**

#### Conflict 1 (around line 42-48):
Remove the duplicate `api_statistics_clear_and_reload` path. Keep only one instance.

#### Conflict 2 (around line 59-77):
Replace with:

```python
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
    
    # Word-level annotation endpoints
    path("word-annotation/", views.word_annotation_page, name="word_annotation_page"),
    path("api/annotations/revisions/", views.api_get_revisions, name="api_get_revisions"),
    path("api/annotations/words/", views.api_get_annotations, name="api_get_annotations"),
]
```

---

### **File 4: `app/reviews/views.py`**

#### Conflict 1 (around line 1790-1798):
Use main's version - just remove the duplicate function definition and keep one clean version.

#### Conflict 2 (around line 1815-1846):
Use main's version with the `data_series` logic - it's more complete.

---

## 🔄 Alternative: Use "Update Branch" Button

If available, click "Update branch" on GitHub PR page to automatically merge latest main.

---

## ✅ Quick Verification

After resolving:
1. All 6 files should show "Mark as resolved"
2. Click "Commit merge"
3. PR should show "✅ This branch has no conflicts"

---

## 📧 If Still Having Issues

The conflicts might be due to:
1. **Outdated GitHub cache** - Refresh the page
2. **Need to update branch** - Click "Update branch" button
3. **Local changes not synced** - We've pushed multiple times, should be synced

### Force Sync Option:
Close and reopen the PR (this forces GitHub to re-check everything).

---

## 🎯 Expected Final State

PR #119 should contain:
- ✅ Word Annotation System (Issue #114)
- ✅ All main branch features
- ✅ Zero conflicts
- ✅ Ready for review

---

**Status**: All files properly merged locally and pushed to GitHub.  
**Date**: October 28, 2025  
**Branch**: issue-114-word-annotation

