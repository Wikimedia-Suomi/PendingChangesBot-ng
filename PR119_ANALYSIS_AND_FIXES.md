# PR #119 - Word Annotation System - Analysis & Fixes

## 📋 PR Summary

**Branch**: `issue-114-word-annotation`  
**Issue**: #114 - Detecting Superseded Pending Changes (Token/Word-Level Diff Tracking)  
**Status**: Has merge conflicts that need resolution

---

## ✅ **What's Already Good**

### 1. **Well-Designed Models** ✅
- `WordAnnotation`: Tracks word-level metadata with proper indexing
- `RevisionAnnotation`: Stores annotation status and metadata
- Proper foreign keys and unique constraints

### 2. **Solid Annotation Engine** ✅
- MediaWiki REST API integration
- Token/word-level diff processing
- Move detection logic
- Author attribution system
- Stable word ID generation using MD5 hashing

### 3. **Management Commands** ✅
- `annotate_article`: Annotate article history
- `get_annotated_revision`: Retrieve annotation data
- Proper error handling and logging

###4. **Web UI Prepared** ✅
- Template for word visualization
- Color coding by author
- Author filtering
- Stats display

---

## ❌ **Issues Found**

### **1. Merge Conflicts (Critical)**

The branch is based on an older version of main. Conflicts in:
- `app/reviews/models/__init__.py` - File structure changed in main
- `app/reviews/urls.py` - URLs reorganized in main
- `app/reviews/views.py` - Views significantly refactored in main

**Impact**: PR cannot be merged without resolving these

---

### **2. Missing Admin Registration**

**File**: `app/reviews/admin.py`

**Issue**: Word annotation models not registered in Django admin

**Current Code**:
```python
# Only registers: Wiki, WikiConfiguration, PendingPage, PendingRevision, 
# EditorProfile, ModelScores
```

**Missing**:
```python
from .models import WordAnnotation, RevisionAnnotation

@admin.register(WordAnnotation)
class WordAnnotationAdmin(admin.ModelAdmin):
    list_display = ("page", "revision_id", "word", "author_user_name", "position")
    search_fields = ("word", "author_user_name", "stable_word_id")
    list_filter = ("page__wiki", "is_moved", "is_modified", "is_deleted")

@admin.register(RevisionAnnotation)
class RevisionAnnotationAdmin(admin.ModelAdmin):
    list_display = ("page", "revision_id", "status", "words_annotated", "created_at")
    search_fields = ("page__title",)
    list_filter = ("status", "page__wiki")
```

---

### **3. Incomplete Move Detection**

**File**: `app/reviews/annotations/engine.py` 

**Line 251-255**:
```python
def _check_if_moved(self, word: str, parent_annotations: list[dict]) -> dict | None:
    """Check if word was moved from another location."""
    # Simple check - look for word in deleted sections of parent
    # This is a simplified version - full implementation would be more complex
    return None  # ❌ Always returns None!
```

**Impact**: Move detection doesn't actually work - always treats moved text as new

**Proposed Fix**:
```python
def _check_if_moved(self, word: str, parent_annotations: list[dict]) -> dict | None:
    """Check if word was moved from another location."""
    # Look for exact word match in parent
    for ann in parent_annotations:
        if ann["word"] == word and ann.get("is_deleted", False):
            # This word was in parent but deleted - might be moved
            return ann
    return None
```

---

### **4. Simple Tokenization**

**File**: `app/reviews/annotations/engine.py`

**Line 212-218**:
```python
def _tokenize(self, text: str) -> list[str]:
    """Tokenize text into words."""
    words = re.split(r"(\s+)", text)
    return [w for w in words if w.strip() or w in ["\n", "\t", " "]]
```

**Issue**: Very basic tokenization that doesn't handle:
- Wikitext templates `{{template}}`
- Links `[[Article|text]]`
- References `<ref></ref>`
- HTML tags

**Impact**: Pollutes annotations with wikitext markup

**Proposed Enhancement**:
```python
def _tokenize(self, text: str) -> list[str]:
    """Tokenize text into words with wikitext awareness."""
    # Remove templates
    text = re.sub(r'\{\{[^}]+\}\}', '', text)
    # Extract link text [[Article|text]] -> text
    text = re.sub(r'\[\[(?:[^|\]]+\|)?([^\]]+)\]\]', r'\1', text)
    # Remove refs
    text = re.sub(r'<ref[^>]*>.*?</ref>', '', text, flags=re.DOTALL)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    words = re.split(r'(\s+)', text)
    return [w for w in words if w.strip() or w in ["\n", "\t", " "]]
```

---

### **5. No Database Migration**

**Missing**: Django migration file for WordAnnotation and RevisionAnnotation models

**Impact**: Cannot create tables without migration

**Need to run**:
```bash
python manage.py makemigrations reviews
```

---

### **6. No URL/View Integration**

**File**: `app/reviews/urls.py`

The PR adds these URLs but they conflict with main:
```python
path("word-annotation/", views.word_annotation_page, name="word_annotation_page"),
path("api/annotations/revisions/", views.api_get_revisions, name="api_get_revisions"),
path("api/annotations/words/", views.api_get_annotations, name="api_get_annotations"),
```

**But**: `views.py` doesn't have these view functions implemented!

**Missing Views**:
- `word_annotation_page()`
- `api_get_revisions()`
- `api_get_annotations()`

---

### **7. No Tests**

**Missing**: Unit tests for:
- `WordAnnotationEngine`
- Tokenization
- Move detection
- Admin interfaces
- Management commands

---

## 🔧 **Fixes to Implement**

### **Priority 1: Resolve Merge Conflicts**

```bash
# Rebase on current main
git fetch origin main
git rebase origin/main

# Resolve conflicts in:
# - app/reviews/models/__init__.py
# - app/reviews/urls.py
# - app/reviews/views.py
```

---

### **Priority 2: Implement Missing Views**

**Create**: `app/reviews/views.py` additions:

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
        
        data = [
            {
                "revid": rev.revid,
                "user_name": rev.user_name,
                "timestamp": rev.timestamp.isoformat(),
                "comment": rev.comment or "",
            }
            for rev in revisions
        ]
        
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
        
        data = [
            {
                "word": ann.word,
                "author": ann.author_user_name,
                "position": ann.position,
                "is_moved": ann.is_moved,
                "is_modified": ann.is_modified,
                "stable_word_id": ann.stable_word_id,
            }
            for ann in annotations
        ]
        
        return JsonResponse({"annotations": data})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
```

---

### **Priority 3: Fix Admin Registration**

Add to `app/reviews/admin.py`:

```python
from .models import WordAnnotation, RevisionAnnotation

@admin.register(WordAnnotation)
class WordAnnotationAdmin(admin.ModelAdmin):
    list_display = ("page", "revision_id", "word", "author_user_name", "position", "is_moved")
    search_fields = ("word", "author_user_name", "stable_word_id")
    list_filter = ("page__wiki", "is_moved", "is_modified", "is_deleted")
    readonly_fields = ("created_at",)

@admin.register(RevisionAnnotation)
class RevisionAnnotationAdmin(admin.ModelAdmin):
    list_display = ("page", "revision_id", "status", "words_annotated", "created_at", "completed_at")
    search_fields = ("page__title",)
    list_filter = ("status", "page__wiki")
    readonly_fields = ("created_at", "updated_at")
```

---

### **Priority 4: Implement Move Detection**

Fix `_check_if_moved()` in `engine.py` to actually detect moves.

---

### **Priority 5: Create Database Migration**

```bash
cd app
python manage.py makemigrations reviews --name add_word_annotation_models
python manage.py migrate
```

---

### **Priority 6: Enhance Tokenization**

Improve tokenization to handle wikitext markup properly.

---

## 📊 **Testing Strategy**

### Unit Tests Needed:

1. **Test WordAnnotation Model**
   - Creation
   - Unique constraints
   - Relationships

2. **Test WordAnnotationEngine**
   - First revision annotation
   - Diff processing
   - Move detection
   - Tokenization

3. **Test Management Commands**
   - `annotate_article`
   - `get_annotated_revision`

4. **Test API Endpoints**
   - Get revisions
   - Get annotations
   - Error handling

---

## 🎯 **Implementation Plan**

### Phase 1: Resolve Conflicts
1. ✅ Rebase on main
2. ✅ Resolve merge conflicts
3. ✅ Test that code still runs

### Phase 2: Fix Core Issues
1. ✅ Implement missing views
2. ✅ Add admin registration
3. ✅ Fix move detection
4. ✅ Create migration

### Phase 3: Enhancements
1. ✅ Improve tokenization
2. ✅ Add error handling
3. ✅ Add logging

### Phase 4: Testing
1. ✅ Write unit tests
2. ✅ Manual testing
3. ✅ Documentation

### Phase 5: Final Review
1. ✅ Code review
2. ✅ Documentation update
3. ✅ Ready for merge

---

## 📝 **Recommended Changes Summary**

| File | Change Type | Priority |
|------|-------------|----------|
| `models/__init__.py` | Resolve conflict | P1 |
| `urls.py` | Resolve conflict | P1 |
| `views.py` | Add missing views + resolve conflict | P1 |
| `admin.py` | Add model registration | P2 |
| `engine.py` | Fix move detection | P2 |
| `engine.py` | Enhance tokenization | P3 |
| Create migration | New file | P2 |
| Add tests | New files | P3 |

---

## ✨ **Once Fixed, This PR Will Provide:**

✅ Complete word-level annotation system  
✅ MediaWiki REST API integration  
✅ Move detection for relocated text  
✅ Author attribution tracking  
✅ Web UI for visualization  
✅ Management commands for annotation  
✅ Database models with proper indexing  
✅ Admin interface for management  

---

## 🚀 **Status After Fixes**

**Current**: ❌ Has conflicts, incomplete implementation  
**After Fixes**: ✅ Production-ready word annotation system

**Estimated Work**: 2-3 hours to implement all fixes and test thoroughly

