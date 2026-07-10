---
argument-hint: [path]
description: Validate Python naming conventions (PEP 8) for modules, classes, functions, and variables.
allowed-tools: Read, Grep, Bash(uv:*, ruff:*)
---

# Naming Convention Validation

Validate code follows PEP 8 naming conventions.

## Python Conventions

- **Modules**: `snake_case.py`
- **Classes**: `PascalCase`
- **Functions/Methods**: `snake_case`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private members**: `_leading_underscore`
- **Variables**: `snake_case`

## Automated Enforcement (Ruff N-rules)

Ruff enforces naming conventions automatically via its `pep8-naming` rule set (prefix `N`).
Run with:

```bash
uv run ruff check --select N path/
```

Key rules enforced:

- `N801` — class names should use CapWords (PascalCase)
- `N802` — function names should be lowercase
- `N803` — argument names should be lowercase
- `N804` — first argument of a classmethod should be `cls`
- `N805` — first argument of a method should be `self`
- `N806` — variable in function should be lowercase
- `N811`–`N817` — invalid constant/alias import casing
- `N818` — exception names should end in `Error`
- `N999` — module name does not follow naming conventions

Enable in `pyproject.toml` by adding `"N"` to `lint.select`.

## Validation Process

1. Run `uv run ruff check --select N path/` for automated detection
2. Review any violations Ruff cannot auto-fix (most N-rules require manual rename)
3. Report remaining violations with suggested fixes

## Output

Reports violations with:

- File and line number
- Current name
- Expected convention
- Suggested fix

---

*Consolidated from quality-naming-conventions command and validate-naming skill.*
