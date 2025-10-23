# Security and Type Checking Setup Examples

This directory contains configuration examples for adding mypy type checking and security vulnerability scanning to the PendingChangesBot-ng project.

## Quick Start

### Option 1: Manual Integration (Recommended for Learning)

1. **Review each example file** to understand what's being added
2. **Merge configurations** into your existing files:
   - `pyproject.toml.example` → `../pyproject.toml`
   - `.pre-commit-config.yaml.example` → `../.pre-commit-config.yaml`
   - `requirements.txt.example` → `../requirements.txt`
   - `github-workflow-security.yml` → `../.github/workflows/security.yml`

3. **Install new dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Update pre-commit hooks**:
   ```bash
   pre-commit install
   pre-commit autoupdate
   ```

5. **Test the setup**:
   ```bash
   bash examples/test-security-setup.sh
   ```

### Option 2: Quick Apply (Bash Script)

```bash
# Coming soon: automated setup script
```

## File Descriptions

### Configuration Files

| File | Purpose | Merge Into |
|------|---------|------------|
| `pyproject.toml.example` | mypy and enhanced Ruff config | `../pyproject.toml` |
| `.pre-commit-config.yaml.example` | Pre-commit hooks for mypy and pip-audit | `../.pre-commit-config.yaml` |
| `requirements.txt.example` | New dependencies | `../requirements.txt` |
| `github-workflow-security.yml` | CI/CD security workflow | `../.github/workflows/security.yml` |

### Documentation

| File | Purpose |
|------|---------|
| `ISSUE_TYPE_CHECKING_SECURITY.md` | Full GitHub issue with implementation details |
| `test-security-setup.sh` | Validation script to test the setup |
| `README.md` | This file |

## Testing Individual Tools

### Test mypy (Type Checking)
```bash
# Check reviews app
mypy app/reviews --config-file=pyproject.toml

# Check specific file
mypy app/reviews/autoreview.py
```

### Test Ruff Security Rules
```bash
# Check all Python files
ruff check --select S app/

# Check specific file
ruff check --select S app/reviews/autoreview.py

# Fix auto-fixable issues
ruff check --select S --fix app/
```

### Test pip-audit (Dependency Scan)
```bash
# Basic scan
pip-audit

# Verbose with descriptions
pip-audit --desc

# Output to JSON
pip-audit --format json -o audit-report.json

# Attempt automatic fixes
pip-audit --fix
```

## Common Issues and Solutions

### mypy: Missing Type Stubs

**Problem**: `error: Skipping analyzing "pywikibot": module is installed, but missing library stubs`

**Solution**: Add to `pyproject.toml`:
```toml
[[tool.mypy.overrides]]
module = ["pywikibot.*", "mwparserfromhell.*"]
ignore_missing_imports = true
```

### Ruff: Too Many Security Warnings

**Problem**: Security rules flag legitimate code (e.g., `assert` in tests)

**Solution**: Add per-file ignores in `pyproject.toml`:
```toml
[tool.ruff.lint.per-file-ignores]
"*/tests/*" = ["S101"]  # Allow assert in tests
```

### pip-audit: Known Vulnerability in Dependency

**Problem**: A dependency has a known vulnerability

**Solutions**:
1. **Upgrade**: `pip install --upgrade <package>`
2. **Check fix**: `pip-audit --fix` (automatic)
3. **Document**: If no fix available, document in issue/README
4. **Ignore temporarily**: Use `pip-audit --ignore-vuln <VULN-ID>`

### Pre-commit: Hook is Slow

**Problem**: `pip-audit` hook slows down every commit

**Solution**: Run only in CI/CD:
```yaml
- id: pip-audit
  stages: [manual]  # Don't run on every commit
```

Then run manually: `pre-commit run pip-audit --all-files`

## Gradual Adoption Strategy

### Week 1: Foundation
- Install dependencies
- Add configurations
- Run initial scans
- Document current state

### Week 2-3: Fix Critical Issues
- Fix critical mypy type errors
- Address high-severity security issues
- Fix blocking dependency vulnerabilities

### Week 4+: Increase Strictness
- Enable stricter mypy settings:
  ```toml
  disallow_untyped_defs = true
  disallow_incomplete_defs = true
  ```
- Add type hints to untyped functions
- Regular security scans

## Integration with CI/CD

The GitHub Actions workflow (`github-workflow-security.yml`) runs three jobs in parallel:

1. **Dependency Scan** - pip-audit checks for vulnerable packages
2. **Code Security Scan** - Ruff checks code for security anti-patterns
3. **Type Check** - mypy validates type annotations

### Workflow Triggers
- Push to `main` or `develop`
- Pull requests
- Weekly scheduled run (Mondays at 9am UTC)

## Resources

### Official Documentation
- [mypy docs](https://mypy.readthedocs.io/)
- [django-stubs](https://github.com/typeddjango/django-stubs)
- [Ruff security rules](https://docs.astral.sh/ruff/rules/#flake8-bandit-s)
- [pip-audit](https://github.com/pypa/pip-audit)

### Tutorials
- [Real Python: Type Checking](https://realpython.com/python-type-checking/)
- [Using mypy with Django](https://sobolevn.me/2019/08/typechecking-django-and-drf)
- [Python Security Best Practices](https://snyk.io/blog/python-security-best-practices-cheat-sheet/)

## Questions?

For questions about this setup:
1. Check the main issue: `../ISSUE_TYPE_CHECKING_SECURITY.md`
2. Ask in the project Slack channel
3. Reference the official documentation linked above

---

**Note**: These examples are reference implementations. Always review and understand configuration changes before applying them to production code.
