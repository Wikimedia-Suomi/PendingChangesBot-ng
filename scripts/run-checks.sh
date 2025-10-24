#!/bin/bash
# Optional script to run all CI checks locally before pushing
# This mirrors exactly what GitHub Actions will run
#
# Usage: ./scripts/run-checks.sh
#
# Note: This is completely optional. All checks run automatically in CI.
#       This just gives you faster feedback during development.

set -e  # Exit on first error

echo "======================================================================"
echo "  Running Type Checking & Security Scans"
echo "======================================================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track if any check fails
FAILED=0

# ============================================================================
# 1. Type Checking (mypy)
# ============================================================================
echo "🔍 Running type checking (mypy)..."
if cd app && python -m mypy reviews --config-file=../pyproject.toml && cd ..; then
    echo -e "${GREEN}✅ Type checking passed${NC}"
else
    echo -e "${RED}❌ Type checking failed${NC}"
    FAILED=1
fi
echo ""

# ============================================================================
# 2. Security Scanning (Ruff with Bandit rules)
# ============================================================================
echo "🔒 Running security scan (Ruff/Bandit)..."
if python -m ruff check --select S app/; then
    echo -e "${GREEN}✅ Security scan passed${NC}"
else
    echo -e "${RED}❌ Security issues found${NC}"
    FAILED=1
fi
echo ""

# ============================================================================
# 3. Dependency Scanning (pip-audit)
# ============================================================================
echo "📦 Checking for vulnerable dependencies (pip-audit)..."
if python -m pip_audit -r requirements.txt --desc; then
    echo -e "${GREEN}✅ No vulnerable dependencies found${NC}"
else
    echo -e "${RED}❌ Vulnerable dependencies detected${NC}"
    FAILED=1
fi
echo ""

# ============================================================================
# Summary
# ============================================================================
echo "======================================================================"
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ All checks passed! Your code is ready to push.${NC}"
    echo "======================================================================"
    exit 0
else
    echo -e "${RED}❌ Some checks failed. Please fix the issues above.${NC}"
    echo "======================================================================"
    exit 1
fi
