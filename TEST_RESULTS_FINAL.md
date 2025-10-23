# Test Results - Security & Type Checking Tools

**Date**: October 11, 2025
**Tested on**: PendingChangesBot-ng main branch

## TL;DR
All three tools work great! Found some stuff to fix:
- Ruff security: 1 potential SQL injection (prob false positive)
- mypy: 5 type errors (all easy fixes)
- pip-audit: ✅ No vulnerabilities in our dependencies!

---

## What I tested

| Tool | Status | Found |
|------|--------|-------|
| Ruff Security (Bandit) | ✅ Works | 1 issue |
| mypy Type Checking | ✅ Works | 5 errors |
| pip-audit Dependencies | ✅ Works | No vulnerabilities |

---

## 1. Ruff Security Rules

Added `"S"` to the lint rules in pyproject.toml and ran it on the codebase.

**Found**: 1 security warning
```
S608: Possible SQL injection
File: app\reviews\services.py, line 89

The f-string has {limit} in it, which Bandit doesn't like. But looking at the code,
`limit` comes from our own code (not user input), so this is probably fine.

Options:
- Add `# noqa: S608` with a comment explaining why it's safe
- Refactor to use parameterized queries (cleaner but more work)
```

**Command I used**:
```bash
python -m ruff check --select S app/reviews/
```

---

## 2. mypy Type Checking

Configured mypy with Django support and ran it. Started with lenient settings so we're not drowning in errors.

**Found**: 5 type errors (all fixable without breaking anything)

1. **services.py:223** - Type mismatch in assignment
   - `superset_data` field has wrong type annotation
   - Easy fix: update the type hint

2. **autoreview.py:453** - Function returns Any
   - `config.redirect_aliases` isn't properly typed
   - Easy fix: add return type annotation

3. **autoreview.py:471** - Function returns Any
   - Similar to above
   - Easy fix: add return type annotation

4. **tests/test_services.py:21** - Missing type annotation
   - Just needs `response: dict[str, Any]`
   - Easy fix: one line

5. **tests/test_autoreview.py:55** - Wrong argument type
   - Passing `{}` (dict) when function expects `[]` (list)
   - Easy fix: change `{}` to `[]`

**Command I used**:
```bash
cd app && python -m mypy reviews --config-file=../pyproject.toml
```

---

## 3. pip-audit - Dependency Vulnerabilities

**Found**: No vulnerabilities! 🎉

Ran pip-audit against our actual project dependencies (Django, pywikibot, mwparserfromhell, requests, ruff, pre-commit, beautifulsoup4, lxml) and everything came back clean.

**CORRECTION**: In my initial testing, I made a mistake and ran pip-audit without the `-r requirements.txt` flag, which caused it to scan my entire Python environment instead of just the project's dependencies. That's why I initially reported vulnerabilities in fastapi, python-jose, etc. - those packages aren't even in this project! Thanks to @Harshita for catching this.

**Command I used** (corrected):
```bash
python -m pip_audit -r requirements.txt --desc
```

The tool itself works perfectly fine - I just used it wrong the first time. This is still a valuable tool to add to the project for ongoing dependency monitoring.

---

## Configuration changes I made for testing

Added to `pyproject.toml`:
- Enabled `"S"` rule in Ruff
- Added per-file ignores for test files
- Complete mypy config section with Django plugin

Everything's backed up (*.backup files) so we can roll back if needed.

---

## What should we do next?

### Right now:
1. Fix those mypy errors (they're all pretty straightforward)
2. Review that SQL injection warning

### Soon:
- Add these tools to pre-commit hooks
- Set up CI/CD to run security scans automatically
- Maybe gradually tighten mypy strictness

### Later:
- Add more type hints to currently untyped functions
- Run pip-audit regularly to catch new vulnerabilities as dependencies get updated
- Consider adding security scanning to PR checks

---

## Commands for quick reference

```bash
# Check security issues in code
python -m ruff check --select S app/

# Check type errors
cd app && python -m mypy reviews --config-file=../pyproject.toml

# Check vulnerable dependencies (scan just the project's requirements)
python -m pip_audit -r requirements.txt --desc

# Run all three
python -m ruff check --select S app/ && \
cd app && python -m mypy reviews --config-file=../pyproject.toml && \
cd .. && python -m pip_audit -r requirements.txt
```

---

## Bottom line

These tools actually work and found real issues! The 5 mypy type errors are worth fixing to catch bugs earlier. Security scanning is basically free since Ruff already has it built in. Our dependencies are clean right now, but pip-audit will be useful for ongoing monitoring.

Recommend going forward with this - the setup is pretty minimal and the benefits are legit.
