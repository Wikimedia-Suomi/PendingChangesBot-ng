# Add type checking and security scanning (mypy + Bandit + pip-audit)

## Summary
Hi Zache, so I've been looking at the codebase and noticed we're using type annotations everywhere (`from __future__ import annotations`) but we don't actually validate them. I think adding mypy would be super useful - it'd catch type mismatches during development instead of finding out about them in production.

Also, I tested a few security scanning tools and found some stuff that should probably get fixed. Nothing's broken right now, but there are some dependency vulnerabilities that we should address.

## Why bother with this?
- We've got type hints all over the place, might as well make them actually useful
- Catching bugs before they hit production > finding them in production
- Works with our existing pre-commit hooks pretty easily
- @zache asked for examples of how to harden legacy Python projects - this could be a good reference for other Wikimedia stuff

## Tools I'm proposing

### mypy - Type checking
This validates the type hints we already have. Pretty standard tool, works well with Django through django-stubs.

What it'll do:
- Catches type errors before the code runs
- Makes IDEs way smarter about autocomplete
- Prevents those annoying "expected str, got None" crashes
- Honestly just makes the codebase easier to work with

### Bandit security rules (via Ruff)
Scans for common security issues like SQL injection, hardcoded secrets, unsafe deserialization, etc.

Best part: Ruff (which we're already using) has Bandit built in! Just need to enable the `S` ruleset. Zero extra dependencies.

### pip-audit - Dependency vulnerability scanning
Checks if any of our dependencies have known CVEs.

Why this instead of Safety? Safety needs a paid license for commercial use, pip-audit doesn't. It's maintained by legit orgs (PyPA & Trail of Bits) and uses Python's official vulnerability database.

## Implementation plan

### Step 1: Add mypy

Install it:
```bash
pip install mypy django-stubs types-requests types-beautifulsoup4
```

Add to `requirements.txt`:
```
mypy>=1.8.0
django-stubs>=4.2.0
types-requests>=2.31.0
types-beautifulsoup4>=4.12.0
```

Config for `pyproject.toml`:
```toml
[tool.mypy]
python_version = "3.9"
plugins = ["mypy_django_plugin.main"]
warn_return_any = true
warn_unused_configs = true
warn_unused_ignores = true
disallow_untyped_defs = false  # keeping this lenient for now, can tighten later
disallow_incomplete_defs = false
show_error_codes = true
no_implicit_optional = true
check_untyped_defs = true

exclude = [
    "migrations/",
    "user-config\\.py",
]

[[tool.mypy.overrides]]
module = ["pywikibot.*", "mwparserfromhell.*"]
ignore_missing_imports = true

[tool.django-stubs]
django_settings_module = "reviewer.settings"
```

Pre-commit hook:
```yaml
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
        additional_dependencies: [django-stubs, types-requests, types-beautifulsoup4]
        args: [--config-file=pyproject.toml]
        exclude: ^(migrations/|user-config\.py)
```

### Step 2: Enable Bandit (via Ruff)

Just update pyproject.toml:
```toml
[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "F",   # pyflakes
    "W",   # pycodestyle warnings
    "I",   # isort
    "UP",  # pyupgrade
    "S",   # bandit security rules <- add this
]

# if we get false positives in tests:
# [tool.ruff.lint.per-file-ignores]
# "*/tests/*" = ["S101"]  # allow assert in tests
```

That's it! No new dependencies since Ruff already has Bandit rules.

### Step 3: Add pip-audit

Install:
```bash
pip install pip-audit
```

Add to requirements.txt:
```
pip-audit>=2.7.0
```

Pre-commit hook (optional - might be slow):
```yaml
  - repo: https://github.com/pypa/pip-audit
    rev: v2.7.0
    hooks:
      - id: pip-audit
        args: [--desc, --skip-editable]
```

GitHub Actions workflow (`.github/workflows/security.yml`):
```yaml
name: Security Audit

on: [push, pull_request]

jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run pip-audit
        run: pip-audit --desc
```

## How to test this

**mypy**:
```bash
cd app && mypy reviews
```
Fix any errors that look legit. Start with lenient settings, gradually make it stricter.

**Ruff security**:
```bash
ruff check --select S app/
```
Fix real issues, ignore false positives with `# noqa: S608` comments (with explanation of why it's safe).

**pip-audit**:
```bash
pip-audit
```
Upgrade vulnerable packages or document why we're not upgrading (if there's no fix available yet).

## Success criteria
- [ ] mypy runs on all Python files (except migrations and user-config.py)
- [ ] Ruff security rules enabled and passing
- [ ] pip-audit added to CI/CD
- [ ] No critical security vulnerabilities in dependencies
- [ ] Documentation updated with how to use these tools

## Questions
1. Start strict with mypy or gradually increase strictness?
2. Should pip-audit run on every commit or just CI/CD? (it can be kinda slow)
3. Any security rules we should ignore for this project specifically?

## Notes
- Starting mypy lenient on purpose - don't want to overwhelm with errors on the first run
- Ruff's Bandit implementation is actually faster than standalone Bandit
- pip-audit is free for commercial use (unlike Safety which requires a paid license)
- Can do this in phases or all at once, whatever makes sense

## Resources
- https://mypy.readthedocs.io/
- https://github.com/typeddjango/django-stubs
- https://docs.astral.sh/ruff/rules/#flake8-bandit-s
- https://github.com/pypa/pip-audit

## Context
@zache asked about tools for hardening legacy Python projects - figured this would be a good example implementation that could be reused elsewhere.

---

Happy to implement this or work with anyone who wants to collaborate!
