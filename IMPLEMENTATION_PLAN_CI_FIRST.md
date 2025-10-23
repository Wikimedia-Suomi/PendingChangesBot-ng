# Implementation Plan: Type Checking & Security Scanning (CI-First Approach)

**Updated**: October 11, 2025
**Approach**: CI-enforced with optional local tooling (no mandatory pre-commit hooks)

## Overview

This implementation adds mypy type checking, Ruff security scanning, and pip-audit dependency scanning to the project using a **CI-first security model**. All checks run in GitHub Actions and block PRs on failure. Contributors can optionally run checks locally for faster feedback, but nothing executes automatically on their machines.

## Security Considerations

Following mentor feedback on issue #62, this approach avoids mandatory pre-commit hooks to prevent supply chain attacks via malicious hook modifications. All enforcement happens in CI where changes are reviewed before merge.

---

## Phase 1: Add Tool Configurations (No Execution Yet)

### 1.1 Update `pyproject.toml` with mypy config

Add this section to `pyproject.toml`:

```toml
# ============================================================================
# MYPY TYPE CHECKING
# ============================================================================
[tool.mypy]
python_version = "3.9"
plugins = ["mypy_django_plugin.main"]

# What to complain about
warn_return_any = true
warn_unused_configs = true
warn_unused_ignores = true
show_error_codes = true
pretty = true

# Starting lenient - can tighten later
disallow_untyped_defs = false
disallow_incomplete_defs = false
disallow_untyped_calls = false
check_untyped_defs = true
no_implicit_optional = true
strict_optional = true

# Other useful checks
warn_redundant_casts = true
warn_unreachable = true

# Skip these
exclude = [
    "migrations/",
    "user-config\\.py",
    "__pycache__",
    "build/",
    "dist/",
]

# Third-party libraries without type stubs
[[tool.mypy.overrides]]
module = [
    "pywikibot.*",
    "mwparserfromhell.*",
]
ignore_missing_imports = true

# Django configuration
[tool.django-stubs]
django_settings_module = "reviewer.settings"
strict_settings = false
```

### 1.2 Enable Ruff security rules in `pyproject.toml`

Update the existing `[tool.ruff.lint]` section:

```toml
[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "F",   # pyflakes
    "W",   # pycodestyle warnings
    "I",   # isort (import sorting)
    "UP",  # pyupgrade (enforce modern Python syntax)
    "S",   # bandit security rules <- ADD THIS
]

ignore = [
    "E203",
    "UP007",  # Use X | Y for type annotations (needs Python 3.10+, we're on 3.9)
]

# Allow test files to use asserts and test patterns
[tool.ruff.lint.per-file-ignores]
"*/tests/*" = ["S101", "S105", "S106"]
```

### 1.3 Add dependencies to `requirements.txt`

```txt
# Type checking
mypy>=1.8.0
django-stubs>=4.2.0
types-requests>=2.31.0
types-beautifulsoup4>=4.12.0

# Security scanning (pip-audit)
pip-audit>=2.7.0
```

**Note**: Ruff already includes Bandit rules, no extra dependency needed.

---

## Phase 2: Create GitHub Actions Workflow

Create `.github/workflows/type-check-security.yml`:

This workflow runs on every push and PR. It runs three jobs in parallel:
1. **Type checking** (mypy)
2. **Code security** (Ruff with Bandit rules)
3. **Dependency security** (pip-audit)

All three must pass for the PR to be mergeable.

---

## Phase 3: Fix Existing Issues

Before enabling the CI checks, we need to fix issues found during testing:

### 3.1 Fix mypy type errors (5 total)

1. **app/reviews/services.py:223** - Fix `superset_data` type annotation
2. **app/reviews/autoreview.py:453** - Add return type annotation for `config.redirect_aliases`
3. **app/reviews/autoreview.py:471** - Add return type annotation
4. **app/reviews/tests/test_services.py:21** - Add `response: dict[str, Any]` annotation
5. **app/reviews/tests/test_autoreview.py:55** - Change `{}` to `[]` for list argument

### 3.2 Review Ruff security warning

**app/reviews/services.py:89** - S608 SQL injection warning on f-string with `{limit}`

Options:
- Add `# noqa: S608` with comment if we confirm `limit` is safe (not user input)
- Refactor to use parameterized query (cleaner approach)

---

## Phase 4: Optional Local Script

Create `scripts/run-checks.sh` (completely optional for contributors):

```bash
#!/bin/bash
# Optional script to run all CI checks locally
# This mirrors what runs in GitHub Actions

set -e

echo "🔍 Running type checking..."
cd app && python -m mypy reviews --config-file=../pyproject.toml && cd ..

echo "🔒 Running security checks..."
python -m ruff check --select S app/

echo "📦 Checking dependencies..."
python -m pip_audit -r requirements.txt --desc

echo "✅ All checks passed!"
```

Make it executable: `chmod +x scripts/run-checks.sh`

Document in README that this is optional but available.

---

## Phase 5: Documentation

### 5.1 Update README.md

Add a "Code Quality & Security" section:

```markdown
## Code Quality & Security

This project uses automated checks to catch bugs and security issues:

- **mypy**: Type checking to catch type errors before runtime
- **Ruff (Bandit rules)**: Security scanning for common vulnerabilities
- **pip-audit**: Dependency vulnerability scanning

### Running Checks Locally (Optional)

All checks run automatically in CI, but you can run them locally for faster feedback:

**Option 1: Run all checks at once**
```bash
./scripts/run-checks.sh
```

**Option 2: Run individually**
```bash
# Type checking
cd app && python -m mypy reviews --config-file=../pyproject.toml

# Security scanning
python -m ruff check --select S app/

# Dependency scanning
python -m pip_audit -r requirements.txt
```

The CI will run these same checks on every PR.
```

### 5.2 Add CONTRIBUTING.md section (if it exists)

Document that all PRs must pass CI checks, and provide the local commands.

---

## Phase 6: CODEOWNERS Protection (Mentor Task)

The following files should require mentor approval via CODEOWNERS:

```
# Critical configuration files - require mentor review
.github/workflows/*           @mentor-team
.pre-commit-config.yaml       @mentor-team
pyproject.toml                @mentor-team
requirements*.txt             @mentor-team
scripts/run-checks.sh         @mentor-team
```

This prevents malicious changes to the security tooling itself.

---

## Rollout Plan

### Step 1: Configuration Only (This PR)
- Add tool configs to `pyproject.toml`
- Add dependencies to `requirements.txt`
- Create GitHub Actions workflow (initially set to `continue-on-error: true` for soft launch)
- Document usage in README

**Goal**: Tools are configured but don't block PRs yet.

### Step 2: Fix Existing Issues (Follow-up PR)
- Fix the 5 mypy errors found in testing
- Address the SQL injection warning
- Run all checks and confirm they pass

**Goal**: Codebase is clean according to the new tools.

### Step 3: Enforce in CI (Follow-up PR)
- Remove `continue-on-error: true` from workflow
- Now checks block PRs if they fail

**Goal**: All future code must pass the checks.

### Step 4: Gradual Strictness Increase (Future)
- Tighten mypy settings (`disallow_untyped_defs = true`, etc.)
- Add more Ruff rules as needed
- Run pip-audit on schedule (weekly) to catch new CVEs

---

## Success Criteria

- [ ] All three tools (mypy, Ruff security, pip-audit) configured in `pyproject.toml`
- [ ] Dependencies added to `requirements.txt`
- [ ] GitHub Actions workflow created and running on all PRs
- [ ] No mandatory pre-commit hooks (all enforcement via CI)
- [ ] Optional local script available for contributors
- [ ] Documentation updated with usage instructions
- [ ] Existing type errors fixed
- [ ] Security warning addressed
- [ ] CI checks passing on main branch

---

## Testing Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Test mypy
cd app && python -m mypy reviews --config-file=../pyproject.toml

# Test Ruff security
python -m ruff check --select S app/

# Test pip-audit
python -m pip_audit -r requirements.txt --desc

# Run all (if script exists)
./scripts/run-checks.sh
```

---

## Security Benefits

1. **Type safety**: Catch type errors before they cause runtime crashes
2. **Code security**: Detect SQL injection, hardcoded secrets, unsafe deserialization, etc.
3. **Dependency security**: Get alerted when dependencies have known CVEs
4. **No local execution risk**: All enforcement in CI, nothing auto-runs on contributor machines
5. **Auditable**: All changes to security tooling go through mentor review (CODEOWNERS)

---

## Resources

- [mypy documentation](https://mypy.readthedocs.io/)
- [django-stubs](https://github.com/typeddjango/django-stubs)
- [Ruff Bandit rules](https://docs.astral.sh/ruff/rules/#flake8-bandit-s)
- [pip-audit](https://github.com/pypa/pip-audit)
- [Python Packaging Advisory Database](https://github.com/pypa/advisory-database)
