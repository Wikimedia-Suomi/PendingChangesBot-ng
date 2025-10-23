#!/bin/bash
# Test script to validate security and type checking setup
# Run this after implementing the configuration changes

set -e

echo "========================================="
echo "Testing Security and Type Checking Setup"
echo "========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print status
print_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ $2 passed${NC}"
    else
        echo -e "${RED}✗ $2 failed${NC}"
    fi
}

echo "1. Testing Ruff with security rules..."
echo "---------------------------------------"
ruff check --select S app/ 2>&1 && ruff_status=0 || ruff_status=$?
print_status $ruff_status "Ruff security scan"
echo ""

echo "2. Testing mypy type checking..."
echo "---------------------------------------"
mypy app/reviews --config-file=pyproject.toml 2>&1 && mypy_status=0 || mypy_status=$?
print_status $mypy_status "mypy type checking"
echo ""

echo "3. Testing pip-audit dependency scan..."
echo "---------------------------------------"
pip-audit --desc 2>&1 && audit_status=0 || audit_status=$?
print_status $audit_status "pip-audit scan"
echo ""

echo "4. Testing pre-commit hooks..."
echo "---------------------------------------"
pre-commit run --all-files 2>&1 && precommit_status=0 || precommit_status=$?
print_status $precommit_status "pre-commit hooks"
echo ""

# Summary
echo "========================================="
echo "Summary"
echo "========================================="

total_failed=0
[ $ruff_status -ne 0 ] && ((total_failed++))
[ $mypy_status -ne 0 ] && ((total_failed++))
[ $audit_status -ne 0 ] && ((total_failed++))
[ $precommit_status -ne 0 ] && ((total_failed++))

if [ $total_failed -eq 0 ]; then
    echo -e "${GREEN}All checks passed!${NC}"
    exit 0
else
    echo -e "${YELLOW}$total_failed check(s) failed${NC}"
    echo ""
    echo "Next steps:"
    [ $ruff_status -ne 0 ] && echo "  - Review Ruff security warnings"
    [ $mypy_status -ne 0 ] && echo "  - Fix mypy type errors"
    [ $audit_status -ne 0 ] && echo "  - Review pip-audit vulnerabilities"
    [ $precommit_status -ne 0 ] && echo "  - Fix pre-commit hook failures"
    exit 1
fi
