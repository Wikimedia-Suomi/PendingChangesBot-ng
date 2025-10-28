"""
Demo script to show how the benchmark_superseded_additions command works
This simulates the command execution without needing a full Django setup
"""

print("\n" + "="*60)
print("BENCHMARK SUPERSEDED ADDITIONS - DEMONSTRATION")
print("="*60 + "\n")

print("Command: python manage.py benchmark_superseded_additions --limit 50 --wiki fi\n")

print("STEP 1: Fetching Revisions from Database...")
print("-" * 60)
print("Query: SELECT * FROM pending_revision")
print("       WHERE wiki_code = 'fi'")
print("       AND wikitext != ''")
print("       AND parentid IS NOT NULL")
print("       ORDER BY page, user, timestamp")
print("       LIMIT 50")
print("\nResult: Found 50 revisions to test\n")

print("STEP 2: Testing Each Revision...")
print("-" * 60)
print("For each revision, comparing two methods:\n")
print("  Method 1 (Current): Similarity-based comparison")
print("  Method 2 (Enhanced): MediaWiki REST API diff analysis with:")
print("    • Proper parent → revision → stable comparison")
print("    • Move detection (filters out relocated text)")
print("    • Word-level similarity matching")
print("    • Smart text comparison algorithms\n")

# Simulate testing progress
revisions_tested = [
    {"id": 1234567, "page": "Helsingin yliopisto", "method1": True, "method2": False, "similarity": 85},
    {"id": 1234892, "page": "Suomen historia", "method1": False, "method2": True, "similarity": 60},
    {"id": 1235001, "page": "Oulu", "method1": True, "method2": True, "similarity": 95},
    {"id": 1235123, "page": "Helsinki", "method1": True, "method2": False, "similarity": 92},
    {"id": 1235200, "page": "Tampere", "method1": False, "method2": False, "similarity": 45},
]

for i, rev in enumerate(revisions_tested, 1):
    status = "AGREE" if rev["method1"] == rev["method2"] else "DISAGREE"
    print(f"  [{i:2d}/50] Testing revision {rev['id']} on {rev['page']:<25} [{status}]")

print("\n  ... (testing remaining 45 revisions) ...\n")

print("STEP 3: Results Summary")
print("="*60)
print("""
Total revisions tested: 50
Both methods agree: 47
  - Both say superseded: 15
  - Both say NOT superseded: 32
Discrepancies found: 3

Agreement rate: 94.0%
""")

print("STEP 4: Detailed Discrepancies (Need Human Review)")
print("="*60)

discrepancies = [
    {
        "revision_id": 1234567,
        "page_title": "Helsingin_yliopisto",
        "wiki": "fi",
        "old_method": "SUPERSEDED",
        "new_method": "NOT SUPERSEDED",
        "similarity": 85,
        "message": "Old: 85% similarity / New: User additions still present after move detection"
    },
    {
        "revision_id": 1234892,
        "page_title": "Suomen_historia",
        "wiki": "fi",
        "old_method": "NOT SUPERSEDED",
        "new_method": "SUPERSEDED",
        "similarity": 60,
        "message": "Old: 60% similarity / New: 80% of user additions deleted in stable"
    },
    {
        "revision_id": 1235123,
        "page_title": "Helsinki",
        "wiki": "fi",
        "old_method": "SUPERSEDED",
        "new_method": "NOT SUPERSEDED",
        "similarity": 92,
        "message": "Old: 92% similarity / New: Text was moved, not superseded"
    },
]

for disc in discrepancies:
    print(f"\nRevision: {disc['revision_id']} on {disc['page_title']} ({disc['wiki']})")
    print(f"  Old method: {disc['old_method']}")
    print(f"  New method: {disc['new_method']}")
    print(f"  Analysis: {disc['message']}")
    diff_url = f"https://{disc['wiki']}.wikipedia.org/w/index.php?title={disc['page_title']}&diff={disc['revision_id']}&oldid={disc['revision_id']-5}"
    print(f"  Review URL: {diff_url}")

print("\n" + "="*60)
print("TESTING WITH BLOCK-BASED COMPARISON")
print("="*60)

print("\nCommand: python manage.py benchmark_superseded_additions --limit 50 --use-blocks\n")

print("Grouping consecutive edits by same editor...")
print("-" * 60)
print("""
Found 50 revisions → Grouped into 23 edit blocks:
  • Block 1: User 'Editor_A' - 3 consecutive edits on page 'Helsinki'
  • Block 2: User 'Editor_B' - 5 consecutive edits on page 'Turku'
  • Block 3: User 'Editor_A' - 2 consecutive edits on page 'Oulu'
  ... and 20 more blocks
""")

print("Testing 23 edit blocks...")
print("-" * 60)

block_results = [
    {"id": "Block 1", "revs": "1234567, 1234568, 1234569", "page": "Helsinki", "agree": True},
    {"id": "Block 2", "revs": "1234890-1234895", "page": "Turku", "agree": True},
    {"id": "Block 3", "revs": "1235001, 1235002", "page": "Oulu", "agree": False},
]

for i, block in enumerate(block_results, 1):
    status = "AGREE" if block["agree"] else "DISAGREE"
    print(f"  [{i:2d}/23] Testing {block['id']} ({block['revs']}) on {block['page']:<20} [{status}]")

print("\n  ... (testing remaining 20 blocks) ...\n")

print("Block-Based Results:")
print("="*60)
print("""
Total blocks tested: 23
Both methods agree: 21
  - Both say superseded: 8
  - Both say NOT superseded: 13
Discrepancies found: 2

Agreement rate: 91.3%
""")

print("="*60)
print("BENCHMARK COMPLETE!")
print("="*60)

print("\n\nNEW FEATURES IN ENHANCED VERSION:")
print("-" * 60)
print("""
✅ MOVE DETECTION
   • Identifies text that was moved vs newly added
   • Prevents false positives from relocated content
   • Uses proximity and similarity analysis

✅ BLOCK-BASED COMPARISON
   • Groups consecutive edits by same editor
   • Tests cumulative changes as single unit
   • Better reflects real editing patterns
   • Use --use-blocks flag to enable

✅ IMPROVED DIFF LOGIC
   • Proper parent → revision comparison to find additions
   • Then revision → stable to check if still present
   • Accurate detection of what user actually added

✅ SMART TEXT MATCHING
   • Word-level similarity calculation
   • 70% threshold for matches (configurable)
   • Handles text transformations better
   • More accurate than simple substring matching
""")

print("\nWHAT THIS BENCHMARK SHOWS:")
print("-" * 60)
print("""
1. Tests multiple Wikipedia revisions from the database
2. Compares TWO different detection methods on same data
3. Uses enhanced REST API analysis with move detection
4. Supports both individual and block-based testing
5. Identifies cases where methods disagree
6. Provides review URLs for manual verification
7. Calculates accuracy statistics

This helps the Wikimedia team:
  * Evaluate detection accuracy with higher confidence
  * Find edge cases that need algorithm improvement
  * Distinguish between moved and superseded text
  * Test both individual edits and edit sequences
  * Validate changes to detection logic
  * Make data-driven decisions about auto-approval
""")

print("\nCOMMAND OPTIONS:")
print("-" * 60)
print("""
--limit N      Test N revisions (default: 50)
--wiki CODE    Test specific wiki (e.g., 'fi' for Finnish Wikipedia)
--page-id ID   Test specific page by ID
--use-blocks   Group consecutive edits by same editor (NEW!)

Usage Examples:
  # Basic benchmark
  python manage.py benchmark_superseded_additions
  
  # Test more revisions
  python manage.py benchmark_superseded_additions --limit 100
  
  # Test specific wiki
  python manage.py benchmark_superseded_additions --wiki fi
  
  # Test with block-based comparison (NEW!)
  python manage.py benchmark_superseded_additions --use-blocks
  
  # Combined options
  python manage.py benchmark_superseded_additions --limit 100 --wiki fi --use-blocks
""")

print("="*60)
print("END OF DEMONSTRATION")
print("="*60 + "\n")
