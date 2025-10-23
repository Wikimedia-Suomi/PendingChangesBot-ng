# Updated Proposal: CI-First Security Approach

Following @ad-an-26's feedback on supply chain security concerns, I've updated the implementation to use a **CI-first approach** instead of mandatory pre-commit hooks.

## What Changed

**Before**: Pre-commit hooks would run checks automatically on every commit
**After**: All checks run in GitHub Actions CI, optional local tooling available

## New Implementation Approach

### 1. GitHub Actions Workflow (Enforcement)

Created `.github/workflows/type-check-security.yml` that runs three jobs in parallel:

- **Type checking** (mypy) - Catches type errors
- **Security scanning** (Ruff/Bandit) - Finds security issues in code
- **Dependency scanning** (pip-audit) - Detects vulnerable dependencies

All three must pass for PRs to be mergeable. No automatic execution on contributor machines.

### 2. Optional Local Script

Created `scripts/run-checks.sh` that contributors can run manually:

```bash
./scripts/run-checks.sh
```

This gives the same feedback as CI but faster. **Completely optional** - nothing runs automatically.

### 3. Configuration Files

- `pyproject.toml` - Tool configurations (mypy settings, Ruff rules)
- `requirements.txt` - Added mypy, django-stubs, types-*, pip-audit dependencies

### 4. CODEOWNERS Protection (Mentor Action)

Recommend protecting these files to require mentor review:
- `.github/workflows/*`
- `.pre-commit-config.yaml`
- `pyproject.toml`
- `requirements*.txt`
- `scripts/run-checks.sh`

This prevents malicious changes to the security infrastructure itself.

## Rollout Plan

### Phase 1: Soft Launch (This PR)
- Add all configurations
- Create GitHub Actions workflow with `continue-on-error: true`
- Tools run but don't block PRs yet
- Document everything

### Phase 2: Fix Issues (Follow-up PR)
- Fix the 5 mypy type errors found in testing
- Address the SQL injection warning
- Confirm all checks pass on main branch

### Phase 3: Hard Enforcement (Follow-up PR)
- Remove `continue-on-error: true`
- Now checks block failing PRs

### Phase 4: Gradual Tightening (Future)
- Increase mypy strictness over time
- Add more security rules as needed

## Files Created

1. **IMPLEMENTATION_PLAN_CI_FIRST.md** - Complete implementation guide with security considerations
2. **examples/type-check-security.yml** - GitHub Actions workflow (ready to move to `.github/workflows/`)
3. **examples/run-checks.sh** - Optional local script for fast feedback

## Security Benefits of This Approach

✅ All enforcement happens in CI (auditable, reviewed)
✅ No automatic code execution on contributor machines
✅ Critical config files protected via CODEOWNERS
✅ Optional local tooling for faster iteration
✅ Same quality gates, but safer supply chain

## Testing

I've already tested all three tools on the codebase:
- ✅ mypy works (found 5 fixable type errors)
- ✅ Ruff security works (found 1 SQL injection warning to review)
- ✅ pip-audit works (no vulnerabilities in our dependencies)

Full test results in `TEST_RESULTS_FINAL.md`.

## Next Steps

1. Get approval on this CI-first approach
2. I'll open a PR with Phase 1 (soft launch)
3. Follow-up PR to fix the existing issues
4. Final PR to enable hard enforcement

Let me know if you'd like any changes to this approach! Happy to collaborate with @Dhie-boop or anyone else interested.

---

**Question for mentors**: Should I include the optional `run-checks.sh` script in the initial PR, or just document the commands and let contributors decide if they want to create it?
