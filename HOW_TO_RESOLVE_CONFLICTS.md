# How to Resolve PR #119 Merge Conflicts

## ✅ What's Already Fixed

Your changes to these files have been accepted:
- ✅ `app/reviews/admin.py` - Admin registration added
- ✅ `app/reviews/annotations/engine.py` - Move detection & tokenization fixed

## ⚠️ Files with Conflicts

GitHub shows conflicts in these 3 files:
1. `app/reviews/models/__init__.py`
2. `app/reviews/urls.py`
3. `app/reviews/views.py`

## 🔧 How to Resolve

### Option 1: Use GitHub's Web Interface (Easiest)

1. Go to your PR: https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/pull/119
2. Click the "Resolve conflicts" button
3. For each file, choose which changes to keep:
   - Keep your word annotation additions
   - Keep main branch's other changes
   - Merge them together
4. Click "Mark as resolved"
5. Commit the merge

### Option 2: Command Line

```bash
# Make sure you're on your branch
git checkout issue-114-word-annotation

# Fetch latest main
git fetch origin main

# Try to merge main into your branch
git merge origin/main

# Git will show you conflicts. Edit each file to resolve:
# 1. Look for <<<<<<< HEAD markers
# 2. Decide what to keep
# 3. Remove the markers
# 4. Save the file

# After resolving all conflicts:
git add app/reviews/models/__init__.py
git add app/reviews/urls.py
git add app/reviews/views.py
git commit -m "Resolve merge conflicts with main"
git push origin issue-114-word-annotation
```

## 📋 What to Keep in Each File

### `app/reviews/models/__init__.py`
**Keep BOTH**:
- All imports from main
- Your new imports: `WordAnnotation`, `RevisionAnnotation`

### `app/reviews/urls.py`
**Keep BOTH**:
- All URL patterns from main
- Your new patterns for word annotation

### `app/reviews/views.py`
**Problem**: Views file significantly changed in main
**Solution**: Need to add your view functions to the new structure

**Missing views you need to add**:
```python
def word_annotation_page(request: HttpRequest) -> HttpResponse:
    """Render word annotation visualization page."""
    return render(request, "reviews/word_annotation.html")

def api_get_revisions(request: HttpRequest) -> JsonResponse:
    """API endpoint to get revisions for a page."""
    page_id = request.GET.get("page_id")
    if not page_id:
        return JsonResponse({"error": "page_id required"}, status=400)
    
    try:
        page = PendingPage.objects.get(pk=page_id)
        revisions = PendingRevision.objects.filter(page=page).order_by("-timestamp")[:50]
        
        data = [{
            "revid": rev.revid,
            "user_name": rev.user_name,
            "timestamp": rev.timestamp.isoformat(),
            "comment": rev.comment or "",
        } for rev in revisions]
        
        return JsonResponse({"revisions": data})
    except PendingPage.DoesNotExist:
        return JsonResponse({"error": "Page not found"}, status=404)

def api_get_annotations(request: HttpRequest) -> JsonResponse:
    """API endpoint to get word annotations for a revision."""
    revision_id = request.GET.get("revision_id")
    if not revision_id:
        return JsonResponse({"error": "revision_id required"}, status=400)
    
    try:
        annotations = WordAnnotation.objects.filter(
            revision_id=revision_id
        ).order_by("position")
        
        data = [{
            "word": ann.word,
            "author": ann.author_user_name,
            "position": ann.position,
            "is_moved": ann.is_moved,
            "is_modified": ann.is_modified,
            "stable_word_id": ann.stable_word_id,
        } for ann in annotations]
        
        return JsonResponse({"annotations": data})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
```

## 🎯 Quick Summary

**Status**: Core fixes applied ✅, conflicts blocking merge ⚠️

**To Fix**:
1. Resolve 3 file conflicts
2. Add missing view functions
3. Create database migration: `python manage.py makemigrations reviews`

**After Fixing**:
- PR can be merged
- Full word annotation system working
- Ready for testing

## 🚀 Next Steps

1. **Resolve conflicts** (use GitHub web or command line)
2. **Add missing views** (copy code above)
3. **Create migration**: `cd app && python manage.py makemigrations reviews`
4. **Push changes**: `git push origin issue-114-word-annotation`
5. **Request review** from maintainers

---

**The hard part (fixing bugs) is done!** This is just integration work.

