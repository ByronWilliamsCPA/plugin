---
argument-hint: [--fix]
description: Comprehensive pre-commit validation with formatting, linting, type checking, security scanning, and test execution.
allowed-tools: Bash(uv:*, ruff:*, basedpyright:*, bandit:*, pytest:*), Read
---

# Pre-commit Validation

Comprehensive validation before committing code. Runs all quality checks in sequence.

## Validation Checklist

### 1. Code Formatting (Ruff)

- Check: `uv run ruff format --check src tests`
- Fix: `uv run ruff format src tests`

### 2. Linting (Ruff)

- Check: `uv run ruff check src tests`
- Fix: `uv run ruff check --fix src tests`

### 3. Type Checking (BasedPyright)

- Check: `uv run basedpyright src`
- Report type errors with suggested fixes

### 4. Security Scanning (Bandit)

- Check: `uv run bandit -r src`
- Report security issues with severity

### 5. Dependency Security (pip-audit)

- Check: `uv run pip-audit`
- Report vulnerable packages (exit code 64 = advisory found, 1 = error)

### 6. Test Suite

- Run: `uv run pytest -v --cov=src --cov-report=term-missing --cov-fail-under=80`
- Report failing tests and coverage gaps

### 7. Pre-commit Hooks

- Run: `uv run pre-commit run --all-files`

## Interactive Fix Mode

With `--fix` flag:

1. Auto-apply Ruff formatting
2. Auto-apply Ruff lint fixes
3. Suggest type hint additions
4. Propose security fixes
5. Suggest dependency updates

## Success Criteria

All checks pass → Ready to commit

---

*Consolidated from quality-precommit-validate command and validate-precommit skill.*
