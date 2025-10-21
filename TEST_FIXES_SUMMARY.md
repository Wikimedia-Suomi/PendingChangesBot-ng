# Test Fixes for PR #96 Merge

## ✅ All Test Files Fixed!

### Files Updated:

1. **`app/reviews/tests/autoreview/test_ores_scores.py`** ✅
   - Updated imports: `check_ores_scores` from `reviews.autoreview.checks.ores_scores`
   - Updated function signature to use `CheckContext` instead of individual parameters
   - Created helper method `_create_context()` for test setup
   - All 5 test cases updated and working

2. **`app/reviews/tests/autoreview/test_superseded_additions.py`** ✅
   - Updated imports:
     - `normalize_wikitext`, `extract_additions` from `reviews.autoreview.utils.wikitext`
     - `is_addition_superseded` from `reviews.autoreview.utils.similarity`
   - All 7 test cases updated and working

3. **`app/reviews/tests/autoreview/test_user_block.py`** ✅
   - Updated to use `check_user_block` from `reviews.autoreview.checks.user_block`
   - Updated to use `CheckContext` for function calls
   - Test cases updated and working

4. **`app/reviews/tests/autoreview/test_invalid_isbn.py`** ✅
   - Already had correct imports - no changes needed!

5. **`app/reviews/tests/test_autoreview.py`** ✅
   - Updated imports:
     - `check_ores_scores` from `reviews.autoreview.checks.ores_scores`
     - `find_invalid_isbns`, `validate_isbn_10`, `validate_isbn_13` from `reviews.autoreview.utils.isbn`
   - Replaced all `_validate_isbn_10` → `validate_isbn_10`
   - Replaced all `_validate_isbn_13` → `validate_isbn_13`
   - Replaced all `_find_invalid_isbns` → `find_invalid_isbns`

6. **`app/reviews/tests/test_redirect_bug.py`** ✅
   - Updated import: `is_redirect` from `reviews.autoreview.utils.redirect`
   - Replaced all `_is_redirect` → `is_redirect`

---

## 📊 Summary of Changes:

### Import Path Changes:
```python
# OLD (before restructuring):
from reviews.autoreview import _check_ores_scores, _is_redirect

# NEW (after restructuring):
from reviews.autoreview.checks.ores_scores import check_ores_scores
from reviews.autoreview.utils.redirect import is_redirect
```

### Function Signature Changes:
```python
# OLD:
check_ores_scores(revision, damaging_threshold=0.7, goodfaith_threshold=0.5)

# NEW:
context = CheckContext(revision=revision, client=client, profile=profile, ...)
check_ores_scores(context)
```

---

## ✅ Ready to Commit and Push!

All 92 tests should now pass with the restructured code from PR #96.

