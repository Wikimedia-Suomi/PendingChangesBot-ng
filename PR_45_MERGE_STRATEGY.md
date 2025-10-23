# PR #45 Merge Conflict Resolution Strategy

## Overview
PR #45 (revertrisk integration) needs to be merged with the latest `main` branch. Main has 4 new commits since PR #45 was created, including an ISBN validation feature that conflicts with the revertrisk implementation.

## Commits in main (not in PR #45):
1. `32cf790` - Add ISBN checksum validation test (#26) (#30)
2. `06d9dc5` - Show human readable reviews when you run autoreview (#42)
3. `c771bd5` - Added free text search filter  (#41)
4. `8fd855c` - adding test to check for manual unapproves (#60)

## Conflicts Identified

### Conflict 1: `app/reviews/autoreview.py`
**Issue**: Both branches added new test functions at the end of `_evaluate_revision()`

**PR #45 adds**: Test 7 - revertrisk check + `_get_revertrisk_score()` function
**main adds**: Test 8 - ISBN validation + helper functions (`_validate_isbn_10`, `_validate_isbn_13`, `_find_invalid_isbns`)

**Resolution**: Keep BOTH tests. After merge:
- Tests 1-6: Existing tests (unchanged)
- Test 7: Revertrisk check (from PR #45)
- Test 8: ISBN validation (from main)

### Conflict 2: `app/reviews/tests/test_views.py`
**Issue**: Test count expectations differ

**PR #45 expects**: 7 tests total (added revertrisk)
**main expects**: 8 tests total (added ISBN)

**Resolution**: After merge, expect **9 tests total** (all original tests + revertrisk + ISBN)

## Step-by-Step Resolution

### Step 1: Merge main into pr-45
```bash
git checkout pr-45
git merge origin/main
```

### Step 2: Resolve `autoreview.py`
In the conflict, we need to:
1. Keep the revertrisk check (Test 7) from PR #45
2. Add the ISBN validation (Test 8) from main AFTER the revertrisk check
3. Keep all helper functions from both branches

The final order in `_evaluate_revision()` should be:
```
Test 1: Bot user check
Test 2: Blocked user check
Test 3: Auto-approved groups
Test 4: Article to redirect conversion
Test 5: Blocking categories
Test 6: Render errors
Test 7: Revertrisk check (from PR #45)
Test 8: ISBN validation (from main)
```

At the end of the file, keep ALL helper functions:
- `_get_render_error_count()`
- ... existing helpers ...
- `_is_article_to_redirect_conversion()`
- `_get_revertrisk_score()` (from PR #45)
- `_validate_isbn_10()` (from main)
- `_validate_isbn_13()` (from main)
- `_find_invalid_isbns()` (from main)

### Step 3: Resolve `test_views.py`
In the test `test_api_autoreview_requires_manual_review_when_no_rules_apply`:

**Change line 477-481 from:**
```python
# Now we have 7 tests: bot-user, blocked-user, auto-approved-group,
# article-to-redirect, blocking-categories, render-errors, revertrisk
self.assertEqual(len(result["tests"]), 7)
self.assertEqual(result["tests"][4]["status"], "ok")
self.assertEqual(result["tests"][-1]["status"], "ok")
```

**To:**
```python
# Now we have 9 tests: bot-user, blocked-user, auto-approved-group,
# article-to-redirect, blocking-categories, render-errors, revertrisk, invalid-isbn
self.assertEqual(len(result["tests"]), 9)
self.assertEqual(result["tests"][4]["status"], "ok")  # blocking-categories
self.assertEqual(result["tests"][-1]["status"], "ok")  # invalid-isbn (last test)
```

### Step 4: Test the merge
```bash
# Run the affected tests
cd app
python manage.py test reviews.tests.test_views.ViewTests.test_api_autoreview_requires_manual_review_when_no_rules_apply

# Run all tests
python manage.py test reviews
```

### Step 5: Commit the merge
```bash
git add app/reviews/autoreview.py app/reviews/tests/test_views.py
git commit -m "Merge main into feature/18: integrate ISBN validation with revertrisk

- Resolves conflicts between revertrisk check (Test 7) and ISBN validation (Test 8)
- Both features now work together: revertrisk checks revert risk, ISBN validates checksums
- Updated test expectations to reflect 9 total tests (was 7 in PR #45, 8 in main)
- All helper functions from both features preserved"
```

### Step 6: Push and notify
```bash
git push origin HEAD:feature/18  # Push to the PR branch
```

Then comment on PR #45:
```
@zache-fi Merge conflicts resolved! Integrated the ISBN validation feature from main (#30) with the revertrisk implementation.

The autoreview pipeline now runs 9 tests total:
1-6: Original tests
7: Revertrisk check (this PR)
8: ISBN validation (from main)

All tests passing. Ready for the Vue.js UI work next.
```

## Notes
- The revertrisk check comes BEFORE ISBN validation because it's cheaper (single API call vs parsing entire wikitext)
- Both checks are independent and don't interfere with each other
- Test numbering is sequential (Test 7, Test 8) for clarity
- Comment updates help future developers understand the test structure

## After Merge: Next Steps
1. ✅ Merge conflicts resolved
2. ⏳ Add revertrisk_threshold to Vue.js configuration panel (zache's request)
3. ⏳ Create issue for generic ML model support (future work)
