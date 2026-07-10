---
description: Code quality checks — Ruff format + lint and BasedPyright type checking. Triggers on "quality, lint, format".
tools: ["Read", "Bash", "Grep", "Glob"]
---

# Code Quality Skill

Code quality validation, formatting, linting, and pre-commit checks.

## Invocation

```text
/quality [scope]
```

**Scope** (optional): `all` (default), `format`, `lint`, `types`

## Activation

Auto-activates on keywords: quality, lint, format

## Workflows

### Formatting
- **workflows/format.md**: Code formatting with Ruff

### Linting
- **workflows/lint.md**: Linting checks with Ruff
- **workflows/naming.md**: Naming convention validation

### Pre-commit
- **workflows/precommit.md**: Pre-commit hook validation

## Commands

### Check (non-destructive)

```bash
# Format check only
uv run ruff format --check .

# Lint check
uv run ruff check .

# Type check
uv run basedpyright src/

# All checks via pre-commit
uv run pre-commit run --all-files
```

### Fix Issues

```bash
# Auto-fix formatting
uv run ruff format .

# Auto-fix lint issues
uv run ruff check --fix .
```

## Quality Standards

### Python Standards
- **Line Length**: 88 characters (Ruff format default)
- **Type Checking**: BasedPyright strict mode
- **Linting**: Ruff with PyStrict-aligned rules

### Rule Categories
- **BLE**: Blind except detection
- **EM**: Error message best practices
- **SLF**: Private member access violations
- **INP**: Require `__init__.py` in packages
- **T10**: No debugger statements
- **G**: Logging format strings

### Per-File Ignores
Tests and scripts have relaxed rules for pragmatic development.

## Quality Tool Behavior Notes

**qlty nesting-level and loop constructs (Obs 80):** qlty's nesting-level counter includes `for` and `while` loops in the count, not just `if`/`else` branching. A function with three nested `for` loops puts any statement in the innermost body at nesting level 4, which triggers the "Deeply nested control flow (level=4)" smell regardless of how many conditionals are present.

To resolve a nesting-4 smell on a triple loop, extract the body of the innermost loop to a helper function -- not just the innermost `if`. A minimal `if` at the innermost level is still at level 4 and will still be flagged.

**qlty runs its own ruff independently of pyproject.toml (Obs 103):** qlty has its own tool-runner layer that invokes ruff with its own configuration, independent of project-level config files (`pyproject.toml`, `.ruff.toml`). Exclusions defined in `pyproject.toml` ruff `exclude` do NOT carry over to qlty. When adding service directories or generated-code directories to `pyproject.toml` ruff exclusions, always check whether `.qlty/qlty.toml` also needs a matching `[[exclude]]` entry.

## Gate Prep and Diagnostic Locality

**Verify the venv interpreter before running type/test gates (Obs 189):** In a uv project, uv can silently provision a newer Python than the project pins (e.g. a 3.14 venv for a `pythonVersion = 3.12` project), and a dev dependency with no wheel for that version fails to build, leaving typed exports unresolved. basedpyright then emits errors across the whole codebase, including files the change never touched. Before running gates, assert the venv interpreter matches the project's pinned version (`.python-version`, `[tool.basedpyright] pythonVersion`, `requires-python`). The discriminator between a code defect and an environment problem is locality: real defects cluster in the diff; environment problems spray across untouched files. When a gate reports errors in files outside the current diff, suspect the environment first (wrong interpreter, partial sync, failed optional-dep build); diff a single untouched file against the base branch to confirm before editing any source. Common fix: `uv venv --python <pinned> --clear` then `uv sync --all-extras`.

## Lint Remediation Patterns

**Reuse private helpers via public re-export, not private-member access (Obs 383):** When a reusable engine is buried as underscore-prefixed helpers in a module that already passes ruff/pyright, do NOT (a) access the privates from outside (trips SLF001), (b) suppress the linter, or (c) rename the internals in the passing module (regression risk). Add a thin public surface at the end of the producer module:

```python
# Public re-exports for cross-module reuse
candidate_params = _candidate_params
load_cma = _load_cma
```

Consumers call the public names; the producer stays clean. For INP001 on a deliberately flat `scripts/` PYTHONPATH-run directory, the correct expression of intent is a scoped, inline-commented per-file-ignore, not an `__init__.py` that would break the run pattern. Package-shape rules are about declared intent: declare it rather than contorting the layout.

**S1244 float-equality with a sign-bound operand (Obs 389):** For `x == 0.0` against a zero or threshold sentinel where the operand has a known sign bound, rewrite using the bound, not a negation chain:

- non-negative operand: `x <= 0.0` (preserves "exactly zero" semantics)
- non-positive operand: `x >= 0.0`

Do NOT rewrite as `not (x > 0.0)`; that trips S1940 (use opposite operator). Document the sign-bound assumption in a comment so the equivalence is auditable. The CLAUDE.md ban on `# noqa` means the semantic rewrite is required, not optional.
