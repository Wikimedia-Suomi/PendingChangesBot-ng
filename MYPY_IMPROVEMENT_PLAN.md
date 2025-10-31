# Mypy Type Checking Improvement Plan

## Background

PR #80 added mypy type checking infrastructure, but the checks were commented out due to type errors in the codebase. This document outlines an incremental approach to enable full mypy type checking.

## Current Status

### What's Already Set Up (PR #80)
- ✅ Mypy configuration in `pyproject.toml`
- ✅ Django stubs and type stubs for third-party libraries
- ✅ GitHub workflow (commented out in `.github/workflows/security.yml` lines 15-36)
- ✅ Lenient initial settings (allows gradual adoption)

### Current Configuration
```toml
[tool.mypy]
python_version = "3.9"
plugins = ["mypy_django_plugin.main"]

# Starting lenient - can tighten later
disallow_untyped_defs = false          # Don't require type annotations everywhere
disallow_incomplete_defs = false        # Don't require complete type annotations
disallow_untyped_calls = false          # Allow calling untyped functions
check_untyped_defs = true              # But do check functions that ARE typed
```

## Incremental Improvement Strategy

### Phase 1: Identify and Categorize Errors (This PR)

**Goal**: Run mypy, collect all errors, categorize by type and module

**Steps**:
1. Run `cd app && python -m mypy reviews --config-file=../pyproject.toml > mypy_errors.txt 2>&1`
2. Analyze error types:
   - Missing return type annotations
   - Missing parameter type annotations
   - `Any` type issues
   - Optional/None handling issues
   - Django model typing issues
   - Third-party library stub issues
3. Group by module/file
4. Create prioritized issue list

**Deliverable**: `mypy_errors_analysis.md` with categorized errors and fix priorities

### Phase 2: Fix Low-Hanging Fruit (Week 1)

**Target**: Files with <5 errors that are straightforward to fix

**Common Easy Fixes**:
```python
# Before
def get_wiki(pk):
    return Wiki.objects.get(pk=pk)

# After
def get_wiki(pk: int) -> Wiki:
    return Wiki.objects.get(pk=pk)
```

**Files to Start With** (typically easiest):
- Utility modules (`app/reviews/utils/`)
- Simple helper functions
- Management commands that aren't complex

**Deliverable**: PR with 5-10 files fully typed

### Phase 3: Django Models and QuerySets (Week 2)

**Target**: Models, managers, and Django-specific patterns

**Common Django Patterns**:
```python
from typing import Optional
from django.db.models import QuerySet

class WikiManager(models.Manager["Wiki"]):
    def get_by_code(self, code: str) -> Optional["Wiki"]:
        try:
            return self.get(code=code)
        except Wiki.DoesNotExist:
            return None

class Wiki(models.Model):
    objects: WikiManager = WikiManager()

    code: str  # Django stubs understand this
    family: str
```

**Files to Focus On**:
- `app/reviews/models/`
- Model methods that return QuerySets
- Custom managers

**Deliverable**: PR with all models properly typed

### Phase 4: Views and API Endpoints (Week 3)

**Target**: Django views, request/response typing

**Common View Patterns**:
```python
from django.http import HttpRequest, HttpResponse, JsonResponse
from typing import Any

def api_wikis(request: HttpRequest) -> JsonResponse:
    wikis = Wiki.objects.all()
    data: list[dict[str, Any]] = [...]
    return JsonResponse(data, safe=False)
```

**Files to Focus On**:
- `app/reviews/views.py`
- API endpoint functions
- Form handling

**Deliverable**: PR with all views properly typed

### Phase 5: Services and Business Logic (Week 4)

**Target**: Core business logic, autoreview checks, services

**Complex Patterns**:
```python
from typing import Protocol, TypedDict

class CheckContext(TypedDict):
    revision: PendingRevision
    configuration: WikiConfiguration

class AutoreviewCheck(Protocol):
    def __call__(self, context: CheckContext) -> CheckResult:
        ...
```

**Files to Focus On**:
- `app/reviews/autoreview/`
- `app/reviews/services/`
- Complex algorithms (`_is_addition_superseded`, etc.)

**Deliverable**: PR with services and checks typed

### Phase 6: Tighten Mypy Settings (Week 5)

**Goal**: Enable stricter mypy checks after codebase is mostly typed

**Settings to Enable Gradually**:
```toml
[tool.mypy]
# Phase 6a: Enable after most functions are typed
disallow_untyped_defs = true           # Require all functions to have types

# Phase 6b: Enable after Phase 6a is complete
disallow_incomplete_defs = true         # Require complete type annotations

# Phase 6c: Final strictness
disallow_untyped_calls = true          # Require typed function calls
```

**Approach**:
- Enable one setting at a time
- Fix errors module by module
- Use `# type: ignore[error-code]` sparingly with explanatory comments

**Deliverable**: PR enabling stricter mypy settings

### Phase 7: Enable Mypy in CI (Final)

**Goal**: Uncomment mypy workflow, make it required check

**Steps**:
1. Uncomment lines 15-36 in `.github/workflows/security.yml`
2. Run test PR to ensure it passes
3. Make mypy check required for all PRs

**Success Criteria**:
- All PRs must pass mypy checks
- No `# type: ignore` comments without explanation
- New code must be fully typed

## Guidelines for Type Annotations

### DO:
```python
# ✅ Use specific types
def get_pending_count(wiki: Wiki) -> int:
    return PendingRevision.objects.filter(page__wiki=wiki).count()

# ✅ Use Optional for nullable values
def find_user(username: str) -> Optional[EditorProfile]:
    try:
        return EditorProfile.objects.get(username=username)
    except EditorProfile.DoesNotExist:
        return None

# ✅ Use TypedDict for structured dicts
from typing import TypedDict

class RevisionResult(TypedDict):
    revid: int
    decision: str
    tests: list[dict[str, Any]]
```

### DON'T:
```python
# ❌ Don't use bare `Any` everywhere
def process_data(data: Any) -> Any:  # Too vague
    ...

# ❌ Don't ignore errors without explanation
result = some_function()  # type: ignore  # BAD: why are we ignoring?

# ✅ DO explain when ignoring
result = external_library()  # type: ignore[no-untyped-call]  # pywikibot has no stubs
```

## Handling Common Patterns

### Django QuerySets
```python
from django.db.models import QuerySet

def get_recent_revisions(wiki: Wiki) -> QuerySet[PendingRevision]:
    return PendingRevision.objects.filter(page__wiki=wiki).order_by("-timestamp")
```

### JSON Responses
```python
from typing import Any, TypedDict

class WikiDict(TypedDict):
    id: int
    code: str
    family: str

def serialize_wiki(wiki: Wiki) -> WikiDict:
    return {"id": wiki.id, "code": wiki.code, "family": wiki.family}
```

### Pywikibot (No Stubs)
```python
import pywikibot
from typing import Any

# Option 1: Use Any for pywikibot objects
site: Any = pywikibot.Site("en", "wikipedia")

# Option 2: Ignore specific lines
site = pywikibot.Site("en", "wikipedia")  # type: ignore[no-untyped-call]
```

## Metrics

Track progress with:
```bash
# Count total errors
mypy reviews --config-file=../pyproject.toml 2>&1 | grep "error:" | wc -l

# Count errors by type
mypy reviews --config-file=../pyproject.toml 2>&1 | grep "error:" | cut -d: -f4 | sort | uniq -c | sort -rn
```

## Success Criteria

- [ ] Phase 1: Error analysis document created
- [ ] Phase 2: 10+ files with zero mypy errors
- [ ] Phase 3: All models fully typed
- [ ] Phase 4: All views fully typed
- [ ] Phase 5: All services/checks fully typed
- [ ] Phase 6: Stricter mypy settings enabled
- [ ] Phase 7: Mypy CI check enabled and required
- [ ] Total mypy errors: 0
- [ ] Type coverage: >90%

## Timeline

- **Week 1**: Phases 1-2 (Analysis + easy fixes)
- **Week 2**: Phase 3 (Models)
- **Week 3**: Phase 4 (Views)
- **Week 4**: Phase 5 (Services)
- **Week 5**: Phase 6 (Stricter settings)
- **Week 6**: Phase 7 (Enable CI)

Each phase should be a separate PR for easier review.

## Resources

- [Mypy documentation](https://mypy.readthedocs.io/)
- [Django-stubs documentation](https://github.com/typeddjango/django-stubs)
- [Python typing module](https://docs.python.org/3/library/typing.html)
- [Real Python: Type Checking](https://realpython.com/python-type-checking/)
