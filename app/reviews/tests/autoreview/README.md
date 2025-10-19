# Autoreview Tests

This directory contains organized test files for individual autoreview checks, split from the original monolithic `test_autoreview.py` file.

## Structure

Each check has its own dedicated test file:

- **`test_invalid_isbn.py`** - Tests for ISBN validation and detection
  - ISBN-10 and ISBN-13 checksum validation  
  - ISBN detection in wikitext
  - Invalid ISBN flagging

- **`test_user_block.py`** - Tests for blocked user checks
  - Verifies blocked users are not auto-approved
  - Tests user block detection after edits

- **`test_ores_scores.py`** - Tests for ORES score checks
  - Damaging score threshold checks
  - Goodfaith score threshold checks
  - ORES API error handling
  - Score caching verification

- **`test_superseded_additions.py`** - Tests for superseded additions detection
  - Wikitext normalization
  - Addition extraction from diffs
  - Superseded content detection

## Running Tests

### Run all autoreview tests:
```bash
python manage.py test reviews.tests.autoreview
```

### Run a specific test file:
```bash
python manage.py test reviews.tests.autoreview.test_invalid_isbn
python manage.py test reviews.tests.autoreview.test_user_block
python manage.py test reviews.tests.autoreview.test_ores_scores
python manage.py test reviews.tests.autoreview.test_superseded_additions
```

### Run a specific test class:
```bash
python manage.py test reviews.tests.autoreview.test_invalid_isbn.ISBNValidationTests
```

### Run a specific test method:
```bash
python manage.py test reviews.tests.autoreview.test_invalid_isbn.ISBNValidationTests.test_valid_isbn_10_with_numeric_check_digit
```

## Benefits of This Structure

1. **No more merge conflicts** - Multiple contributors can work on different check tests simultaneously
2. **Easier navigation** - Find tests for specific checks quickly
3. **Faster test execution** - Run only the tests you need
4. **Better organization** - Tests grouped by feature/check
5. **Easier maintenance** - Smaller files are easier to understand and modify

## Adding New Test Files

When adding a new autoreview check, create a corresponding test file following this pattern:

1. Create `test_<check_name>.py` in this directory
2. Import the check function from `reviews.autoreview.checks.<check_name>`
3. Create a test class: `class <CheckName>Tests(TestCase):`
4. Add test methods following Django's naming convention: `def test_<what_it_tests>(self):`

## Related

- Check implementations: `app/reviews/autoreview/checks/`
- Utility functions: `app/reviews/autoreview/utils/`
- Original monolithic test file: `app/reviews/tests/test_autoreview.py` (kept for backward compatibility)

