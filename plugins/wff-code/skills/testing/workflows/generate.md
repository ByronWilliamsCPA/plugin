---
argument-hint: [module-path]
description: Generates comprehensive pytest test suites covering unit, integration, and async code. Enforces named parametrize, spec'd mocks, AsyncMock for coroutines, and full edge-case coverage.
allowed-tools: Read, Write, Bash(pytest:*), Task
---

# Test Generator

Generates high-quality pytest tests for any Python codebase. Creates unit, integration,
async, and property-based tests following strict quality standards.

## Quality Standard (non-negotiable)

Every generated test file MUST satisfy all of the following before being written:

### 1. Naming — `test_<unit>_<scenario>_<expected_outcome>`

```python
# Correct
def test_parse_front_matter_missing_delimiter_returns_none():
def test_fetch_with_retry_max_retries_exceeded_raises_http_error():
def test_validate_email_none_input_returns_false():

# Wrong
def test_parser():
def test_function_works():
def test_case_1():
```

### 2. Parametrize by default with named ids

When two or more tests share the same logic and differ only in inputs/outputs, use
`@pytest.mark.parametrize` with `pytest.param(..., id="readable-id")` on every entry:

```python
@pytest.mark.parametrize("address,expected", [
    pytest.param("user@example.com", True, id="valid-standard"),
    pytest.param("user+tag@sub.example.com", True, id="valid-plus-subdomain"),
    pytest.param("", False, id="empty-string"),
    pytest.param(None, False, id="none-value"),
    pytest.param("@nodomain", False, id="missing-local-part"),
    pytest.param("a" * 65 + "@example.com", False, id="local-part-too-long"),
])
def test_validate_email_inputs_return_expected(address, expected):
    assert validate_email(address) == expected
```

### 3. Edge cases — all four, always

For every function accepting user-facing input:
1. `None` input (if type signature allows it)
2. Empty string or empty collection
3. Boundary values (maximum/minimum allowed lengths or counts)
4. Invalid type or clearly malformed input

### 4. Mocks MUST use `spec=` or `autospec=True`

`MagicMock()` without spec silently accepts any attribute — bugs hide until production.

```python
# Correct
mock_client = MagicMock(spec=requests.Session)
mock_db = MagicMock(spec=DatabaseConnection)

# Wrong — accepts .any_attribute_you_typo without error
mock_client = MagicMock()
```

### 5. AsyncMock for coroutines

When mocking any `async def` function or method, use `AsyncMock` (not `MagicMock`).
Using `MagicMock` for async code causes `await mock()` to return another `MagicMock`
instead of a coroutine — the test passes but the assertion is semantically wrong.

Also check `.await_count` (not `.call_count`) for async calls.

```python
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_fetch_with_retry_success_returns_json():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"key": "value"}

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_response)

    result = await fetch_with_retry(mock_client, "https://example.com")

    assert result == {"key": "value"}
    assert mock_client.get.await_count == 1


@pytest.mark.asyncio
async def test_fetch_with_retry_applies_backoff_between_retries():
    mock_response_fail = MagicMock()
    mock_response_fail.status_code = 503

    mock_response_ok = MagicMock()
    mock_response_ok.status_code = 200
    mock_response_ok.json.return_value = {"key": "value"}

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(
        side_effect=[mock_response_fail, mock_response_ok]
    )

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await fetch_with_retry(mock_client, "https://example.com")

    assert result == {"key": "value"}
    assert mock_client.get.await_count == 2
    assert mock_sleep.await_count == 1  # one sleep between retries
```

### 6. Meaningful assertions

Every test must assert a specific value, not just existence or truthiness:

```python
# Correct
assert validate_email("user@example.com") is True
assert response.status_code == 200
assert user.name == "Alice"

# Wrong
assert result              # passes for any truthy value
assert result is not None  # passes even if result is wrong
assert True                # never fails, tests nothing
```

### 7. Async tests use `@pytest.mark.asyncio`

Never use `asyncio.run()` inside a test. Let pytest-asyncio manage the event loop:

```python
@pytest.mark.asyncio
async def test_async_function_returns_expected_result():
    result = await async_operation()
    assert result == expected_value
```

## Workflow

1. **Read the module** — understand public API, type signatures, error conditions
2. **Identify scenarios** — happy path, error cases, edge cases, boundaries
3. **Check for async** — any `async def` functions require AsyncMock and `@pytest.mark.asyncio`
4. **Plan parametrize groups** — identify tests that share logic but differ in data
5. **Write tests** — naming → AAA → parametrize → mocks → assertions
6. **Verify completeness** — all four edge cases covered, no weak assertions

## Test Organization

```text
tests/
├── unit/           # Pure function tests (fast, isolated, no I/O)
├── integration/    # Cross-component tests (may use real DB/filesystem)
├── e2e/           # Full-system workflows (slow, real I/O)
├── security/      # OWASP/injection tests
├── performance/   # Benchmarks and load tests
└── conftest.py    # Shared fixtures
```

Use appropriate pytest markers:

```python
@pytest.mark.unit         # Fast, isolated
@pytest.mark.integration  # Cross-component
@pytest.mark.e2e          # Full system
@pytest.mark.slow         # > 5 seconds
@pytest.mark.security     # Security validation
@pytest.mark.perf         # Performance benchmark
```

## Fixtures

Prefer the built-in `tmp_path` fixture for file operations:

```python
@pytest.fixture
def markdown_file(tmp_path):
    """Create a temporary Markdown file with front matter for testing."""
    path = tmp_path / "test.md"
    path.write_text("---\ntitle: Hello\nauthor: Test\n---\nBody content")
    return path

def test_extract_title_valid_file_returns_title(markdown_file):
    assert extract_title(markdown_file) == "Hello"


def test_parse_front_matter_valid_file_returns_metadata_and_content(tmp_path):
    # Arrange
    md_file = tmp_path / "doc.md"
    md_file.write_text("---\ntitle: Test\n---\nContent here")

    # Act
    meta, content = parse_front_matter(md_file)

    # Assert
    assert meta == {"title": "Test"}
    assert content == "Content here"
```

Factory fixtures for repeated object creation:

```python
@pytest.fixture
def user_factory():
    created = []

    def _make(username="test", email=None, **kwargs):
        user = User(username=username, email=email or f"{username}@example.com", **kwargs)
        created.append(user)
        return user

    yield _make

    for user in created:
        user.delete()
```

## Property-Based Testing

Use hypothesis for functions with broad input domains:

```python
from hypothesis import given, strategies as st

@given(st.integers(), st.integers())
def test_addition_is_commutative(a, b):
    assert add(a, b) == add(b, a)

@given(st.text(min_size=1, max_size=254))
def test_validate_email_never_raises_on_string_input(s):
    result = validate_email(s)
    assert isinstance(result, bool)
```

## Coverage Requirements

- **Unit tests**: 90%+ for the module under test
- **Error paths**: every exception path tested
- **Edge cases**: None, empty, boundary, malformed
- **Integration tests**: all public interface paths

## Integration Points

- **pytest** — primary framework with asyncio support
- **pytest-asyncio** — `@pytest.mark.asyncio` for async tests
- **pytest-mock** — `mocker.patch`, `mocker.patch.object`
- **hypothesis** — `@given` for property-based tests
- **pytest-cov** — `--cov=src --cov-report=term-missing`

## Agent Delegation

For complex test generation requiring comprehensive strategy across multiple modules,
use the `test-writer` agent (or `test-engineer` for multi-tier architecture planning):

```yaml
Task: Generate tests for [module]
Agent: test-writer
```

---

*Nested workflow within testing skill. For coverage gap analysis and iterative
generate→run→fix→review loop, use the `/test-coverage` skill.*
