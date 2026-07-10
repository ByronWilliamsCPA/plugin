---
name: debug-tests
description: >
  Debug failing tests with root-cause-first analysis. Auto-activates on: failing test,
  test failure, debug test, test error, pytest error, test broken, tests failing
argument-hint: "[test-path]"
allowed-tools:
  - Read
  - Bash
  - Grep
  - Glob
  - Edit
---

# Debug Tests Skill

Debug test failures using root-cause-first analysis. Investigates structural causes
before touching application code.

## Invocation

```text
/debug-tests [test-path]
```

**Example**: `/debug-tests tests/unit/test_auth.py`

If no path is provided, run the full suite to identify failures first.

## Workflow

### Step 1 — Reproduce

```bash
pytest $ARGUMENTS -v --tb=long 2>&1 | head -100
```

Capture the full error output before drawing conclusions.

### Step 2 — Classify Root Cause

Investigate in this order (do not skip ahead to application logic):

1. **Fixtures & configuration** — conftest.py issues, missing seed data, incorrect
   factory defaults, fixture scope problems
2. **Environment mismatches** — SQLite vs Postgres differences (JSONB, UUID, pool_size),
   missing env vars, Python version incompatibility
3. **Dependency drift** — a locked dependency changed behavior, version constraint mismatch,
   breaking change in an updated library
4. **Test isolation** — shared state between tests, ordering dependencies, missing teardown,
   leaked side effects
5. **Application logic** — only investigate here after ruling out 1–4

### Step 3 — Fix and Verify

- Apply the minimal fix targeting the classified root cause
- Re-run the failing test in isolation:
  ```bash
  pytest path/to/test_file.py::test_name -v
  ```
- Run the full suite to check for side effects:
  ```bash
  uv run pytest --tb=short
  ```

### Step 4 — Document

Include the root cause category in the commit message:

```text
fix(tests): repair auth fixture after session scope change

Root cause: Category 1 (fixture scope), conftest session fixture
was sharing state across test classes.
```

## Environment Setup for Iterative Runs (uv projects)

`uv run pytest` re-syncs the environment to the DEFAULT dependency set on every invocation,
uninstalling extras from `[project.optional-dependencies]` each time. In a debug loop this
silently drops test deps (hypothesis, pytest-cov) or app deps (fastapi) between runs, and
collection then fails with `ModuleNotFoundError` that looks like Category 3 drift but is just
env churn. Stable repeated runs require pinning the env once and opting out of per-call sync,
not re-passing `--extra` flags each time:

```bash
uv sync --all-extras                      # sync once
uv run --no-sync python -m pytest ...      # repeat without re-syncing
```

Prefer `python -m pytest` over the `pytest` console script, and scrub `PYTHONPATH`
(`env -u PYTHONPATH ...`) so system site-packages (e.g. `/usr/lib/python3/dist-packages` on
WSL, which can shadow the venv with an old Pydantic or pytest) do not win over the venv.

## Common Rationalizations

The shortcuts that make a red test green without fixing anything. Each one defers the
failure instead of resolving it.

| Rationalization | Reality |
| --- | --- |
| "The test is flaky, just re-run it" | Flakiness is a root cause (shared state, timing, ordering), not noise. Classify it (Category 4). |
| "Add a sleep and it passes" | A sleep masks an async or ordering bug; it fails again under load or on a faster runner. |
| "Bump the timeout" | A rising timeout is a symptom. Find what got slower instead of widening the window. |
| "Mock it so the test goes green" | A mock that hides the failure also hides the regression the test existed to catch. |
| "It only fails in CI" | CI is the honest environment. The difference (env, ordering, parallelism) is the bug (Category 2). |
