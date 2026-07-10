---
name: testing
description: >
  Automated test generation, review, and execution for pytest-based projects.
  Use when users want to write new tests, run the test suite, set up test
  infrastructure (fixtures, conftest, markers), review test quality, add
  integration/e2e/property-based/mutation testing, or run pytest with specific
  options. Covers test creation, execution, and review workflows — NOT coverage
  gap analysis (use test-coverage), NOT debugging a specific failing test
  (use debug-tests), NOT linting/formatting (use quality).
---

# Testing Skill

Automated test generation, review, and execution for pytest-based projects.

## Invocation

```text
/testing [action] [scope]
```

**Actions** (optional): `run` (default), `generate`, `review`, `coverage analyze`,
`coverage generate`, `coverage enforce`, `security`

**Scopes** (optional): `all` (default), `unit`, `integration`, `e2e`

## Workflows

### Test Generation
- **workflows/generate.md**: Generate test cases — naming, parametrize, spec=, AsyncMock, edge cases

### Test Review
- **workflows/review.md**: Review existing tests — 6-item quality checklist with concrete fixes

### Specialized Testing
- **workflows/e2e.md**: End-to-end testing — CLI, API integration, pipeline, data integrity
- **workflows/security.md**: Security testing — OWASP Top 10, injection, path traversal, DoS
- **workflows/performance.md**: Performance testing — benchmarks, memory limits, latency SLAs

## Context Files

- **context/pytest-commands.md**: Common pytest commands and configuration
- **context/pytest-patterns.md**: Patterns reference — naming, parametrize, spec=, AsyncMock, fixtures

## Context Loading Guide

Based on the user's request, proactively note these requirements before generating:

| Request type | Pre-generate checklist |
|-------------|----------------------|
| Async functions | Remind: AsyncMock for coroutines, `@pytest.mark.asyncio`, `.await_count` not `.call_count`; `spec=` must target the actual injected dependency (e.g. `spec=FragranceService` if routes receive a service via `Depends`, not always `spec=AsyncSession`) |
| File I/O | First check whether the module actually performs file I/O; if yes: `tmp_path` fixture, no hardcoded paths; if no file I/O: omit `tmp_path` — do not add it mechanically |
| HTTP clients | Remind: `spec=httpx.AsyncClient`, AsyncMock for `.get`/`.post` methods |
| Pydantic models | Remind: parametrize valid + missing-required + wrong-type scenarios |
| Review request | Reference: 6-item checklist in workflows/review.md by number |

## Commands

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/claude_config --cov-report=html --cov-report=term-missing

# Run by scope
uv run pytest tests/unit/ -v --tb=short
uv run pytest tests/integration/ -v --tb=short -m "integration"
uv run pytest tests/e2e/ -v --tb=short -m "e2e"

# Run specific test categories (markers)
uv run pytest -m "not slow"
uv run pytest -m "unit"

# Run with verbose output
uv run pytest -v --tb=short

# Run mutation testing
uv run mutmut run --paths-to-mutate=src/

# Run property-based tests
uv run pytest --hypothesis-show-statistics
```

## Coverage Standards (v2.0)

- **Line Coverage**: 80% minimum
- **Branch Coverage**: 70% minimum
- **Critical Modules**: 90% minimum
- **Patch Coverage**: 90% minimum (new/changed code)
- **Coverage Report**: HTML and terminal output

## Advanced Workflows

For automated coverage gap analysis, test generation, and enforcement,
use the **test-coverage** skill (`/test-coverage`). It orchestrates
the test-writer and test-reviewer subagents with an iterative
generate->run->fix->review loop.

## Test Organization

```text
tests/
├── unit/           # Unit tests (fast, isolated)
├── integration/    # Integration tests (may use external services)
├── e2e/           # End-to-end tests (full system)
├── security/      # Security-focused tests
├── performance/   # Performance and load tests
└── conftest.py    # Shared fixtures
```

## Testing Patterns

### AAA Pattern (Arrange-Act-Assert)
```python
def test_example():
    # Arrange
    input_data = create_test_data()

    # Act
    result = function_under_test(input_data)

    # Assert
    assert result == expected_output
```

### Fixtures
```python
@pytest.fixture
def sample_data():
    return {"key": "value"}

def test_with_fixture(sample_data):
    assert sample_data["key"] == "value"
```

## Pitfalls and Edge Cases

Real-world failure patterns collected from production sessions.

### Grep full test corpus for changed message strings (Obs 29)

When a function is renamed or its output message format changes, grep ALL test files (not just co-located unit tests) for the old message string or function name before declaring tests green. Integration and e2e test files that encode the old string fail at the run-all stage, not during targeted runs.

```bash
grep -r "old_message_string" tests/
```

Run this before declaring a rename complete.

### HTTP library and mock library must be matched (Obs 30)

`responses` only mocks the `requests` library; `respx` mocks `httpx`; `aioresponses` mocks `aiohttp`. A mismatch (e.g., `httpx` implementation + `@responses.activate` mock) causes tests to appear to test something while making real network calls or raising connection errors.

Always verify the mocking library supports the HTTP library in the implementation before writing tests.

Canonical pairings:

| HTTP library | Mock library |
|---|---|
| `requests` | `responses` |
| `httpx` | `respx` |
| `aiohttp` | `aioresponses` |

### Dead parameters signal incomplete refactor (Obs 83)

When refactoring inlines a parameter from a concrete caller into a generic helper, verify every parameter in the new helper's signature is actually used in the body. Write a test that passes two different values for each parameter and asserts the parameter has a detectable effect on output. A parameter that accepts a value but never references it is a refactoring smell.

### Fake SHA constants need pragma allowlist (Obs 89)

40-character hex strings used as test fixture SHAs (e.g., fake GitHub Action commit SHAs) are flagged as "Hex High Entropy String" false positives by entropy-based secret scanners. Add `# pragma: allowlist secret` to every line where a 40-char hex constant is assigned as a test fixture:

```python
FAKE_COMMIT_SHA = "a" * 40  # pragma: allowlist secret
```

### SPDX tokens in REUSE-gated repos (Obs 130)

A test that asserts on license-header content (e.g., grepping for SPDX license tag literals) will fail REUSE compliance because REUSE parses license tags from anywhere in a file -- including inside fenced code blocks and string literals -- and treats the token as the file's own declaration.

Build the token via string concatenation so the contiguous SPDX license-identifier tag sequence never appears in source:

```python
# Good: concatenate to avoid a contiguous SPDX tag literal
SPDX_MIT = "SPDX-License-Identifier" + ": MIT"
assert SPDX_MIT in header
```

Note: wrapping code with `REUSE-IgnoreStart` / `REUSE-IgnoreEnd` HTML comment markers is the other documented approach, but support varies by REUSE tool version. String concatenation is more reliable across versions.

### Reproduce lint/type findings through the real gate, not a path-scoped run (Obs 478)

A linter or type-checker invoked with explicit file paths on the command line can surface diagnostics the project's actual gate never reports, because the project config restricts its `include` scope (e.g. basedpyright `include = ["src", "scripts"]` with pre-commit `pass_filenames: false`, so tests are deliberately untyped). A path-scoped run can also flag known framework-reflection false positives (a `reportUnusedFunction` on a pytest autouse fixture).

Before treating such a diagnostic as a blocker: (1) confirm it is not pre-existing (diff against HEAD), and (2) reproduce it through the project's real gate invocation (the config-driven `include`/`exclude` and the pre-commit/CI entry point), not an ad-hoc file-path run. A tool's command-line scope is not the project's gate scope; only diagnostics the gate-as-configured emits are gate failures.

### Testing CLI main() that reads module-level path constants (Obs 481)

Two traps appear when a thin CLI driver's `main()` or helpers read module-level path constants:

1. **Path-family coupling.** A `main()` that prints `OUTPUT.relative_to(REPO)` couples every path constant to `REPO`. Monkeypatching only the output path leaves siblings (`PARQUET`, `TARGETS`) pointing at the real repo while `REPO` moves, so their `relative_to()` raises `ValueError`. Relocate the whole path family (root plus all derived paths) into the tmp tree together, not just one.
2. **Bound-default gotcha.** `def load(x=MODULE_CONST)` evaluates the default once at import, so monkeypatching the module attribute does NOT change the function's bound default; `main()` calls `load()` and still reads the real file. Stub the function itself (or pass the path explicitly) rather than reassigning the module constant.

Monkeypatching a module attribute only affects name lookups that happen at call time. Default-argument values and already-derived sibling constants are resolved earlier and ignore the patch. Test seams must target the binding actually evaluated when the code under test runs.

### Banned characters in guard tests: encode, do not spell (Obs 429)

When a project bans a character or token (e.g. the no-em-dash hook) and a test must assert against it, a guard test that embeds the forbidden token as a source literal becomes a violation of the rule it checks. Reference the token by codepoint escape or a constructed value so the file carries no literal byte while the runtime assertion is unchanged:

```python
EM_DASH = "\u2014"  # reference by codepoint escape, never the literal
assert EM_DASH not in rendered_markdown
```

Scan test files for banned literals alongside prose and code.
