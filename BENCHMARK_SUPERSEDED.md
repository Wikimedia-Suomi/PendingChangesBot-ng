# Superseded Additions Benchmark Documentation

This document explains the benchmark tool for testing superseded additions detection methods (Issue #113).

## Overview

The `benchmark_superseded` management command compares two methods for detecting when pending revisions have been superseded:

1. **Current Method (Similarity-based)**: Uses character-level similarity matching with `SequenceMatcher` to determine if text additions from a pending revision still appear in the latest stable version.

2. **Proposed Method (Word-level diff)**: Uses MediaWiki REST API's visual diff endpoint to track word-level changes, including block moves and refined edits.

## Current Implementation Analysis

### How the Similarity Method Works

Located in `app/reviews/autoreview/utils/similarity.py` and `app/reviews/autoreview/utils/wikitext.py`, the current implementation:

1. **Extracts Additions** (`extract_additions`):
   - Uses Python's `difflib.SequenceMatcher` to compare parent → pending revision
   - Identifies inserted or replaced text blocks
   - Returns list of text additions

2. **Normalizes Text** (`normalize_wikitext`):
   - Removes wiki markup: `<ref>` tags, templates `{{}}`, categories, file links
   - Strips formatting: bold `'''`, italics `''`, internal links `[[]]`
   - Normalizes whitespace
   - Purpose: Compare semantic content, not formatting

3. **Checks Supersession** (`is_addition_superseded`):
   - For each significant addition (>20 chars after normalization):
     - Calculates what percentage appears in latest stable version
     - Uses `SequenceMatcher` to find matching blocks (≥4 chars)
     - If match ratio < threshold (default 0.2 = 20%), considers superseded
   - Returns `True` if any significant addition is below threshold → auto-approve

### Configuration

Controlled by `WikiConfiguration.superseded_similarity_threshold`:
- Type: `FloatField`
- Default: `0.2` (20%)
- Range: 0.0-1.0
- Location: `app/reviews/models.py:110-118`

**Lower values = stricter**: A threshold of 0.1 means only 10% of the addition needs to be missing to consider it superseded.

### Current Limitations

1. **Character-level, not word-level**: Can't distinguish meaningful text changes from formatting
2. **No block move detection**: If text is moved from intro to conclusion, appears as deletion + addition
3. **No refinement tracking**: Can't tell if an addition was improved vs removed
4. **Normalization artifacts**: Aggressive normalization may lose context

## Word-Level Diff Method

### How It Works

Uses MediaWiki REST API (`/w/rest.php/v1/revision/{from}/compare/{to}`):

1. **Fetch Added Words**:
   - Get visual diff between parent → pending revision
   - Parse HTML diff response for `<ins>` tags and `.diffchange-inline` classes
   - Extract added words (filtered to >2 chars)

2. **Fetch Current State**:
   - Get visual diff between parent → latest stable revision
   - Extract words present in latest version

3. **Calculate Retention**:
   - Compare word sets: `overlap = added_words ∩ stable_words`
   - Retention ratio: `len(overlap) / len(added_words)`
   - If retention < threshold, consider superseded

### Advantages

- **Word-level precision**: Tracks meaningful semantic units
- **Block move awareness**: MediaWiki API detects moved paragraphs
- **Refinement detection**: Can distinguish edited vs removed content
- **Wiki-markup aware**: Uses MediaWiki's own parser

### Limitations

- **API dependency**: Requires external API calls (slower, rate limits)
- **HTML parsing**: Depends on stable HTML structure from API
- **Word granularity**: Very short additions (<3 words) may be less reliable

## Usage

### Prerequisites

**Important**: Before running this command, ensure that pending revisions data has been loaded into the database via the web interface. The command will display a warning if no suitable data is found.

### Basic Command

```bash
python manage.py benchmark_superseded --wiki=fi --sample-size=50
```

### Parameters

- `--wiki=<code>` (required): Wiki language code (e.g., 'fi', 'en', 'sv')
- `--sample-size=<n>`: Number of revisions to test (default: 50)
- `--threshold=<0.0-1.0>`: Similarity threshold to test (default: 0.2)
- `--output=<file>`: JSON output file (default: benchmark_results.json)

### Examples

#### Test 100 revisions on Finnish Wikipedia

```bash
python manage.py benchmark_superseded --wiki=fi --sample-size=100 --output=fi_wiki_results.json
```

#### Test stricter threshold

```bash
python manage.py benchmark_superseded --wiki=fi --sample-size=50 --threshold=0.1
```

#### Test with custom output location

```bash
python manage.py benchmark_superseded --wiki=en --sample-size=200 --output=reports/en_wiki_benchmark.json
```

## Output Format

### Console Output

```
Benchmarking superseded detection on fi.wikipedia
Sample size: 50
Threshold: 0.2

Found 47 revisions to test

Processing 1/47: r12345678
  Similarity: APPROVE | Word-level: APPROVE | Match: ✓

Processing 2/47: r12345679
  Similarity: REVIEW | Word-level: APPROVE | Match: ✗

...

============================================================
BENCHMARK SUMMARY
============================================================

Total revisions tested: 47
Valid results: 45
Errors: 2

------------------------------------------------------------
AGREEMENT ANALYSIS
------------------------------------------------------------

Agreements: 38
Disagreements: 7
Agreement rate: 84.4%

------------------------------------------------------------
METHOD COMPARISON
------------------------------------------------------------

Similarity-based approvals: 12
Word-level diff approvals: 19

------------------------------------------------------------
DISAGREEMENT BREAKDOWN
------------------------------------------------------------

Only similarity approved: 0
Only word-level approved: 7

============================================================
```

### JSON Output

```json
{
  "statistics": {
    "total_tested": 47,
    "valid_results": 45,
    "errors": 2,
    "agreements": 38,
    "disagreements": 7,
    "agreement_rate": 0.844,
    "similarity_approvals": 12,
    "wordlevel_approvals": 19,
    "similarity_only_approvals": 0,
    "wordlevel_only_approvals": 7
  },
  "results": [
    {
      "revid": 12345678,
      "pageid": 98765,
      "page_title": "Example Article",
      "user": "ExampleUser",
      "timestamp": "2025-01-15T10:30:00+00:00",
      "similarity_superseded": true,
      "wordlevel_superseded": true,
      "agreement": true,
      "addition_count": 3,
      "significant_addition_count": 2,
      "diff_url": "https://fi.wikipedia.org/w/index.php?diff=12345678&oldid=12345600"
    },
    ...
  ]
}
```

## Interpreting Results

### Agreement Rate

High agreement (>80%) indicates both methods reach similar conclusions, validating the current approach.

Low agreement (<70%) suggests the methods capture different aspects of supersession.

### Disagreement Patterns

#### Similarity approved, word-level rejected

Possible causes:
- Current method over-normalizes and misses preserved meaning
- Word-level method is too strict on exact word preservation

#### Word-level approved, similarity rejected

Possible causes:
- Word-level method better detects refined content (improvements)
- Current method penalizes legitimate edits that change wording
- **This is the expected improvement direction**

### Manual Review

For disagreements, use the `diff_url` field to manually inspect:

```bash
# Extract disagreements for manual review
jq '.results[] | select(.agreement == false)' benchmark_results.json
```

Visit each `diff_url` to determine which method made the correct decision.

## Integration Path

If benchmark shows word-level method is more accurate:

1. **Add word-level as optional check** alongside current method
2. **A/B test in production** with configurable flag
3. **Collect metrics** on false positives/negatives
4. **Gradually migrate** based on per-wiki performance

### Configuration Options

Could add to `WikiConfiguration`:

```python
superseded_detection_method = models.CharField(
    max_length=20,
    default='similarity',
    choices=[
        ('similarity', 'Similarity-based (current)'),
        ('wordlevel', 'Word-level diff (MediaWiki API)'),
        ('hybrid', 'Hybrid (both must agree)'),
    ],
)
```

## Performance Considerations

### Similarity Method
- ✅ Fast: No external API calls
- ✅ Scales well: Pure Python computation
- ✅ Reliable: No network dependencies

### Word-Level Method
- ⚠️ Slower: Requires MediaWiki API requests
- ⚠️ Rate limits: Must respect API usage policies
- ⚠️ Network dependency: Failures possible
- 💡 **Mitigation**: Cache API responses, use batch requests

### Recommendation

Use similarity method as primary check, word-level as optional validation for high-value articles (e.g., living person biographies).

## Testing Checklist

- [ ] Run benchmark on at least 100 revisions per wiki
- [ ] Test across multiple Wikipedia languages
- [ ] Compare with manual reviewer decisions (ground truth)
- [ ] Measure false positive rate (incorrectly approved)
- [ ] Measure false negative rate (incorrectly blocked)
- [ ] Test edge cases:
  - [ ] Very short additions (<50 chars)
  - [ ] Very long additions (>5000 chars)
  - [ ] Formatting-only changes
  - [ ] Block moves
  - [ ] Template additions
  - [ ] Reference additions

## Related Files

- `app/reviews/autoreview.py`: Current implementation (lines 383-427, 755-813)
- `app/reviews/models.py`: Configuration (lines 110-118)
- `app/reviews/management/commands/benchmark_superseded.py`: This benchmark tool
- Issue: https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/issues/113

## References

- [MediaWiki REST API - Compare Revisions](https://www.mediawiki.org/wiki/API:REST_API/Reference#Compare_revisions)
- [Python difflib.SequenceMatcher](https://docs.python.org/3/library/difflib.html#difflib.SequenceMatcher)
- [Issue #113 - Benchmark superseded_additions](https://github.com/Wikimedia-Suomi/PendingChangesBot-ng/issues/113)
