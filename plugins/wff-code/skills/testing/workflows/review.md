---
argument-hint: [test-directory or test-file]
description: Reviews pytest test quality against a 6-item checklist: parametrize duplication, unspec'd mocks, weak assertions, missing edge cases, naming convention, and no-exception-only tests.
allowed-tools: Read, Bash(pytest:*, coverage:*), Grep
---

# Test Reviewer

Expert test quality reviewer for pytest-based suites. Delivers actionable, function-level
feedback against a standardized 6-item checklist.

## Review Checklist

For every test file or suite, check all six items. Every finding must cite the specific
test function name and provide a concrete fix.

### 1. Parametrize duplication

Flag any group of test functions that share the same body structure and differ only in
inputs/outputs. These should be collapsed into a single `@pytest.mark.parametrize`.

```python
# Anti-pattern
def test_add_positive():
    assert add(1, 2) == 3

def test_add_positive_again():
    assert add(3, 4) == 7

def test_add_positive_third():
    assert add(10, 20) == 30

# Fix
@pytest.mark.parametrize("a,b,expected", [
    pytest.param(1, 2, 3, id="small-positive"),
    pytest.param(3, 4, 7, id="medium-positive"),
    pytest.param(10, 20, 30, id="large-positive"),
])
def test_add_positive_inputs_return_sum(a, b, expected):
    assert add(a, b) == expected
```

### 2. Unspec'd mock objects

Flag any `MagicMock()` created without `spec=` or `autospec=True`. Without spec,
mocks silently accept any attribute access — tests pass even when the production
interface changes.

```python
# Anti-pattern
mock_client = MagicMock()
mock_db = Mock()

# Fix
mock_client = MagicMock(spec=requests.Session)
mock_db = MagicMock(spec=DatabaseConnection)
# Or using mocker:
mock_db = mocker.patch("module.DatabaseConnection", autospec=True)
```

Also flag `MagicMock` used to mock an `async def` function. Those require `AsyncMock`:

```python
# Anti-pattern (get is async, MagicMock causes await to return a MagicMock)
mock_client.get = MagicMock(return_value=mock_response)

# Fix
mock_client.get = AsyncMock(return_value=mock_response)
# and check .await_count, not .call_count
```

### 3. Weak assertions

Flag any test that uses `assert True`, `assert result`, `assert result is not None`,
or only wraps a call in `try/except` without asserting on the return value.

```python
# Anti-pattern
def test_multiply_returns_value():
    result = multiply(3, 4)
    assert result is not None  # passes for any non-None, including wrong values

def test_multiply_zero():
    assert True  # never fails, tests nothing

# Fix
def test_multiply_positive_inputs_return_product():
    assert multiply(3, 4) == 12

def test_multiply_by_zero_returns_zero():
    assert multiply(3, 0) == 0
```

### 4. Missing edge cases

For every function under test, verify there are tests for:
1. `None` input (if the type signature allows it)
2. Empty string or empty collection
3. Boundary values (maximum/minimum allowed lengths or counts)
4. Invalid type or clearly malformed input

```python
# Missing coverage — only tests happy path
def test_get_user_valid_id_returns_user():
    result = get_user(1)
    assert result.id == 1

# Add these
def test_get_user_none_id_raises_type_error():
    with pytest.raises(TypeError):
        get_user(None)

def test_get_user_negative_id_raises_value_error():
    with pytest.raises(ValueError):
        get_user(-1)

def test_get_user_nonexistent_id_returns_none():
    assert get_user(999999) is None
```

### 5. Naming convention violations

Flag any test function name that does not follow `test_<unit>_<scenario>_<expected_outcome>`.

```python
# Anti-pattern
def test_user():
def test_it_works():
def test_case_1():

# Fix
def test_get_user_valid_id_returns_user_object():
def test_validate_email_malformed_address_returns_false():
def test_parse_config_missing_key_raises_key_error():
```

**Negative test description accuracy:** For tests that verify error or failure paths, the `_<scenario>_<expected_outcome>` components must describe the actual validation rule that fires, not just the input shape. "Invalid text type" is wrong if the framework coerces the type and the failure is a different constraint (e.g., `min_length`). A wrong description creates a false mental model that persists until someone reads the raw error response.

When reviewing negative tests, read the validation code (not just the test input) to verify the name matches the actual error path.

```python
# Anti-pattern: name implies type error, but Pydantic v2 coerces int → str
# and actual failure is min_length, not type mismatch
def test_detect_invalid_text_type_returns_422():
    response = client.post("/detect", json={"text": 12345})
    assert response.status_code == 422

# Fix option A: name reflects actual cause
def test_detect_text_too_short_returns_422():
    response = client.post("/detect", json={"text": "short"})
    assert response.status_code == 422

# Fix option B: split into two tests that each prove one thing
def test_detect_integer_input_coerced_to_string():
    # Send integer equivalent of >50 chars to prove coercion succeeds
    response = client.post("/detect", json={"text": 99999999999999999999999999999999999999999999999999999})
    assert response.status_code == 200  # coercion worked, length OK

def test_detect_text_below_min_length_returns_422():
    response = client.post("/detect", json={"text": "too short"})
    assert response.status_code == 422
```

### 6. No-exception-only tests

Flag any test that only verifies no exception is raised, without asserting anything about
the return value or side effects.

```python
# Anti-pattern
def test_add_does_not_raise():
    try:
        result = add(1, 2)
    except Exception:
        pytest.fail("Unexpected exception")

# Fix
def test_add_positive_inputs_returns_sum():
    assert add(1, 2) == 3
```

## Review Workflow

1. **Read the test file(s)** — full scan before writing any feedback
2. **Run coverage** — identify which source lines are untested
3. **Apply the 6-item checklist** — document every violation with function name
4. **Check markers** — are tests correctly classified (unit/integration/e2e/slow)?
5. **Check isolation** — any tests that depend on each other or shared mutable state?
6. **Produce the report**

```bash
# Run coverage before reviewing
uv run pytest --cov=src --cov-report=term-missing tests/

# Check for specific anti-patterns
grep -n "MagicMock()" tests/
grep -n "assert True" tests/
grep -n "is not None" tests/
```

## Review Report Format

```markdown
# Test Review: [Module/File]

## Summary
- Checklist pass rate: X/6 items clean
- Tests reviewed: N
- Issues found: M

## Issues

### 1. Parametrize duplication — `test_add_positive`, `test_add_positive_again`, `test_add_positive_third`
[Description of the issue and the fix]

### 2. Unspec'd mock — `test_get_user_returns_result`
[Description and fix]

...

## Coverage Gaps
- `src/module.py:42-45` — error path not tested
- `src/module.py:67` — boundary condition missing

## Recommendations (priority order)
1. [Most critical]
2. [Second priority]
3. [Third priority]
```

## Integration Points

- **pytest-cov** — coverage measurement: `--cov=src --cov-report=term-missing`
- **Grep** — pattern scan for anti-patterns before reading test bodies
- **conftest.py** — verify fixtures are shared rather than duplicated

## Output Standards

Every finding must include:
1. The exact test function name(s) involved
2. What the anti-pattern is and why it's a problem
3. A concrete before/after code fix

Vague feedback like "improve assertions" or "add more tests" is not acceptable.
Cite a function, explain the issue, show the fix.

---

*Nested workflow within testing skill. For comprehensive test quality audit with
coverage enforcement, use the `/test-coverage` skill.*
