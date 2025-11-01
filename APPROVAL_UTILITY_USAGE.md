# Comprehensive Approval Utility System Usage

This document explains how to use the comprehensive approval utility system that was implemented as part of issue #105. The system includes multiple utility functions, processing capabilities, and testing tools for generating consolidated approval comments.

## Overview

The approval utility system provides a complete solution for processing autoreview results and generating consolidated approval comments. It includes:

- **Core comment generation functions** for creating consolidated approval comments
- **High-level processing functions** for managing approval workflows
- **Batch processing capabilities** for handling multiple pages
- **Comprehensive testing tools** including management commands
- **Statistics and analytics** for approval decisions

## Core Functions

### 1. Basic Comment Generation

```python
def generate_approval_comment_and_revision(autoreview_results: list[dict]) -> tuple[int | None, str]:
```

**Parameters:**
- `autoreview_results`: Results from `run_autoreview_for_page()` containing approval decisions

**Returns:**
- `rev_id`: Highest approved revision ID (None if no revisions can be approved)
- `comment`: Consolidated summary of all approvals

### 2. Advanced Comment Generation

```python
def generate_approval_comment(autoreview_results: list[dict], comment_prefix: str = "") -> tuple[int | None, str]:
```

**Parameters:**
- `autoreview_results`: Results from autoreview system
- `comment_prefix`: Optional prefix for approval comments

**Returns:**
- `rev_id`: Highest approved revision ID
- `comment`: Consolidated summary with prefix

### 3. Processing and Approval

```python
def process_and_approve_revisions(autoreview_results: list[dict], comment_prefix: str = "", dry_run: bool = True) -> dict:
```

**Parameters:**
- `autoreview_results`: Results from autoreview system
- `comment_prefix`: Optional prefix for approval comments
- `dry_run`: If True, only preview without making actual approvals

**Returns:**
- Dictionary with comprehensive processing results

### 4. Batch Processing

```python
def batch_process_pages(pages_data: list[dict], comment_prefix: str = "", dry_run: bool = True) -> dict:
```

**Parameters:**
- `pages_data`: List of page data with autoreview results
- `comment_prefix`: Optional prefix for approval comments
- `dry_run`: If True, only preview without making actual approvals

**Returns:**
- Dictionary with batch processing results

### 5. Statistics Generation

```python
def get_approval_statistics(autoreview_results: list[dict]) -> dict:
```

**Parameters:**
- `autoreview_results`: Results from autoreview system

**Returns:**
- Dictionary with comprehensive approval statistics

## Example Usage

### Basic Usage

```python
from reviews.autoreview import run_autoreview_for_page, generate_approval_comment_and_revision
from reviews.utils import generate_approval_comment, process_and_approve_revisions

# Get autoreview results for a page
page = PendingPage.objects.get(pageid=12345)
results = run_autoreview_for_page(page)

# Generate approval comment and find highest approvable revision
max_approvable_revid, approval_comment = generate_approval_comment_and_revision(results)

if max_approvable_revid:
    print(f"Can approve up to revision {max_approvable_revid}")
    print(f"Comment: {approval_comment}")
else:
    print("No revisions can be approved")
```

### Advanced Usage

```python
from reviews.utils import (
    generate_approval_comment, 
    process_and_approve_revisions,
    batch_process_pages,
    get_approval_statistics
)

# Advanced comment generation with prefix
max_revid, comment = generate_approval_comment(results, "Auto:")

# Process with comprehensive results
result = process_and_approve_revisions(results, "Auto:", dry_run=True)
print(f"Success: {result['success']}")
print(f"Approved: {result['approved_count']}/{result['total_count']}")

# Batch processing multiple pages
pages_data = [
    {"pageid": 12345, "results": results1},
    {"pageid": 12346, "results": results2}
]
batch_result = batch_process_pages(pages_data, "Batch:", dry_run=True)

# Get comprehensive statistics
stats = get_approval_statistics(results)
print(f"Approval rate: {stats['approval_rate']:.1f}%")
```

### Example Output

For input results like:
```python
[
    {"revid": 12345, "decision": {"status": "approve", "reason": "user was bot"}},
    {"revid": 12346, "decision": {"status": "approve", "reason": "no content change in last article"}},
    {"revid": 12347, "decision": {"status": "approve", "reason": "user was autoreviewed"}},
    {"revid": 12348, "decision": {"status": "approve", "reason": "user was autoreviewed"}},
    {"revid": 12349, "decision": {"status": "approve", "reason": "ORES score goodfaith=0.53, damaging: 0.251"}},
]
```

The function would return:
```python
(12349, "rev_id 12345 approved because user was bot, rev_id 12346 approved because no content change in last article, rev_id 12347, 12348 approved because user was autoreviewed, rev_id 12349 approved because ORES score goodfaith=0.53, damaging: 0.251")
```

## Features

### Revision Grouping

The function intelligently groups consecutive revisions with identical approval reasons to keep comments concise:

- Single revision: `"rev_id 12345 approved because user was bot"`
- Multiple revisions: `"rev_id 12347, 12348 approved because user was autoreviewed"`

### Edge Case Handling

- **No approvable revisions**: Returns `(None, "No revisions can be approved")`
- **Mixed results**: Only includes revisions with `"approve"` status
- **Empty results**: Returns `(None, "No revisions can be approved")`

### Integration with API

The function is integrated into the autoreview API endpoint (`/api/autoreview/`) and returns an `approval_summary` object:

```json
{
  "pageid": 12345,
  "title": "Test Page",
  "mode": "dry-run",
  "results": [...],
  "approval_summary": {
    "max_approvable_revid": 12349,
    "approval_comment": "rev_id 12345 approved because user was bot, ..."
  }
}
```

## Benefits

1. **Reduces approval actions**: Only one call to `approve_revision()` needed instead of multiple
2. **Provides transparency**: Documents all approval decisions in a single comment
3. **Creates audit trail**: Clear record of why multiple revisions were approved together
4. **Handles edge cases**: Gracefully manages scenarios with no approvable revisions

## Management Command

The system includes a comprehensive management command for testing:

```bash
# Test all scenarios
python manage.py test_approval_comment --scenario all

# Test specific scenario
python manage.py test_approval_comment --scenario mixed --preview-only

# Test with custom prefix
python manage.py test_approval_comment --scenario bot --comment-prefix "Auto: "

# Test with verbose output
python manage.py test_approval_comment --scenario all --verbose
```

**Available scenarios:**
- `bot`: Bot user approvals
- `ores`: ORES score approvals
- `mixed`: Mixed approval reasons
- `none`: No approvable revisions
- `single`: Single revision approval
- `all`: All scenarios

## Testing

The system includes comprehensive unit tests covering:
- Single and multiple approved revisions
- Mixed approvable and non-approvable revisions
- Edge cases (empty results, no approvals)
- Different approval reasons (bot users, ORES scores, revert detection, etc.)
- Revision grouping with same reasons
- Integration with API endpoints
- Batch processing functionality
- Statistics generation
- Error handling

Run tests with:
```bash
python manage.py test reviews.tests.test_approval_utility
python manage.py test reviews.tests.test_approval_integration
python manage.py test reviews.tests.test_approval_comment
```

## File Structure

```
app/reviews/
├── utils/
│   ├── __init__.py
│   ├── approval_comment.py      # Core comment generation logic
│   └── approval_processor.py    # High-level processing functions
├── management/
│   └── commands/
│       └── test_approval_comment.py  # Testing management command
└── tests/
    ├── test_approval_utility.py      # Basic utility tests
    ├── test_approval_integration.py  # API integration tests
    └── test_approval_comment.py      # Comprehensive utility tests
```
