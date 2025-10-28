# PR #133 Review - Issue #113 Implementation Analysis

## Issue Requirements vs Implementation

### ✅ Completed Requirements

1. **Django Management Command** - DONE
   - Created `benchmark_superseded_additions` command
   - CLI options for limit, wiki, page-id
   - Proper Django integration

2. **Dual Method Testing** - DONE
   - Tests current similarity-based method
   - Tests new REST API method
   - Compares both methods

3. **Discrepancy Reporting** - DONE
   - Shows which method said superseded/not superseded
   - Provides diff URLs for human review
   - Reports statistics and agreement rate

### ❌ Missing/Incomplete Requirements

#### 1. **Block-Based Comparison NOT Implemented**

**Issue Requirement:**
> "Instead of treating individual input revisions separately, treat consecutive edits by the same editor as a single edit block"

**Status:** NOT IMPLEMENTED

**Needed:**
```python
def _group_consecutive_edits(self, revisions):
    """Group consecutive edits by the same editor."""
    blocks = []
    current_block = []
    current_user = None
    
    for revision in revisions:
        if revision.user == current_user:
            current_block.append(revision)
        else:
            if current_block:
                blocks.append(current_block)
            current_block = [revision]
            current_user = revision.user
    
    if current_block:
        blocks.append(current_block)
    
    return blocks
```

#### 2. **Move Detection NOT Implemented**

**Issue Requirement:**
> "Determine added, removed, and moved text... Only text actually added by the user should be considered (i.e., separate the moved and added texts)"

**Status:** NOT IMPLEMENTED

**Current Code:**
```python
# Only handles type 0, 1, 2
if line.get("type") == 1:  # Added text
    additions.append(line.get("text", ""))
```

**Needed:**
- Detect moved blocks using MediaWiki diff API
- Filter out moved text from additions
- Only consider truly new text as additions

#### 3. **Incorrect Diff Comparison Logic**

**Problem:** Current implementation compares `revision → stable` directly, which doesn't show what the USER added.

**Current Code:**
```python
api_url = f"https://{wiki.code}.wikipedia.org/w/rest.php/v1/revision/{revision.revid}/compare/{stable_rev.revid}"
```

**Should Be:**
```python
# Step 1: Find what user added
parent_to_revision_url = f"https://{wiki.code}.wikipedia.org/w/rest.php/v1/revision/{revision.parentid}/compare/{revision.revid}"

# Step 2: Check if those additions are in stable
# Need to track specific added text and see if it appears in stable version
```

#### 4. **Oversimplified Text Matching**

**Current Code:**
```python
if addition in context_text or context_text in addition:
    return True
```

**Problems:**
- Too loose substring matching
- Doesn't properly analyze diff structure
- May produce false positives/negatives

**Needed:**
- Proper word-level or line-level matching
- Consider text transformations
- Use diff structure information properly

## Recommended Implementation Changes

### Priority 1: Fix Diff Comparison Logic

```python
def _test_with_rest_api(self, revision: PendingRevision, stable_rev: PendingRevision) -> bool:
    """Test using MediaWiki REST API diff to check if additions are still present."""
    try:
        wiki = revision.page.wiki
        
        # Step 1: Get what the user added (parent → revision)
        added_text = self._get_user_additions(revision, wiki)
        if not added_text:
            return True  # No additions, so they're "superseded" (nothing to check)
        
        # Step 2: Check if additions still exist in stable version
        # Compare revision → stable and see if user's additions appear as deletions
        revision_to_stable_url = f"https://{wiki.code}.wikipedia.org/w/rest.php/v1/revision/{revision.revid}/compare/{stable_rev.revid}"
        
        response = requests.get(revision_to_stable_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        diff = data.get("diff", [])
        if not diff:
            return True  # No changes from revision to stable
        
        # If user's additions appear as deletions (type 2), they were superseded
        deletions = [line.get("text", "") for line in diff if line.get("type") == 2]
        
        # Check if user's additions are in the deletions
        for addition in added_text:
            if any(addition in deletion or deletion in addition for deletion in deletions):
                return True  # User's text was deleted = superseded
        
        return False  # User's additions are still present
        
    except Exception as e:
        logger.exception(f"Error in REST API test for revision {revision.revid}: {e}")
        return False

def _get_user_additions(self, revision: PendingRevision, wiki) -> list[str]:
    """Get text that user actually added (excluding moves)."""
    try:
        parent_to_revision_url = f"https://{wiki.code}.wikipedia.org/w/rest.php/v1/revision/{revision.parentid}/compare/{revision.revid}"
        
        response = requests.get(parent_to_revision_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        diff = data.get("diff", [])
        
        # Extract only added text (type 1), excluding moved blocks
        # TODO: MediaWiki API may mark moves differently - need to check documentation
        additions = []
        for line in diff:
            if line.get("type") == 1:  # Added text
                # TODO: Check if this is a move rather than pure addition
                additions.append(line.get("text", ""))
        
        return additions
        
    except Exception as e:
        logger.exception(f"Error getting user additions for revision {revision.revid}: {e}")
        return []
```

### Priority 2: Implement Block-Based Comparison

```python
def handle(self, *args: Any, **options: Any) -> None:
    # ... existing code ...
    
    if options.get("use_blocks"):
        # Group consecutive edits by same editor
        revision_blocks = self._group_consecutive_edits(revisions)
        
        for block in revision_blocks:
            result = self._test_revision_block(block)
            # ... process results ...
    else:
        # Existing individual revision testing
        for revision in revisions:
            result = self._test_revision(revision)
            # ... process results ...
```

### Priority 3: Implement Move Detection

This requires understanding MediaWiki's diff format better. Need to:
1. Check MediaWiki REST API documentation for move markers
2. Filter out moved text from additions
3. Only consider truly new text

## Summary

**Overall Assessment:** 
- PR addresses **~60%** of the issue requirements
- Core functionality works but missing key features
- Logic needs refinement for accuracy

**Must-Have Changes:**
1. Fix diff comparison logic (currently incorrect)
2. Properly extract user additions (parent → revision diff)
3. Improve text matching algorithm

**Nice-to-Have Changes:**
1. Implement block-based comparison
2. Add move detection
3. Better handling of edge cases

**Recommendation:**
- Request changes before merging
- Core concept is solid but implementation needs refinement
- Maintainers should review the diff comparison logic carefully

