# Pytest Patterns and Best Practices

Common pytest patterns for high-quality test suites in Python projects.

## Test Naming Convention (mandatory)

Every test function name MUST follow: `test_<unit>_<scenario>_<expected_outcome>`

```python
# Correct — three underscore-separated segments minimum
def test_parse_front_matter_missing_delimiter_returns_none():
def test_validate_email_none_input_returns_false():
def test_fetch_with_retry_max_retries_exceeded_raises_http_error():

# Wrong — vague or single-segment
def test_parser():
def test_function_works():
def test_case_1():
```

## AAA Pattern (Arrange-Act-Assert)

The fundamental test structure:

```python
def test_user_creation_valid_input_returns_user():
    # Arrange
    username = "testuser"
    email = "test@example.com"

    # Act
    user = create_user(username, email)

    # Assert
    assert user.username == username
    assert user.email == email
    assert user.is_active is True
```

## Parametrize Pattern

### Named params (mandatory)

Always use `pytest.param(..., id="readable-id")` so failures identify which scenario broke:

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

### Multiple parameters

```python
@pytest.mark.parametrize("width,height,expected_area", [
    pytest.param(5, 10, 50, id="normal-rectangle"),
    pytest.param(0, 5, 0, id="zero-width"),
    pytest.param(3, 3, 9, id="square"),
])
def test_rectangle_area_dimensions_return_expected(width, height, expected_area):
    assert Rectangle(width, height).area() == expected_area
```

### Combining parametrize decorators

```python
@pytest.mark.parametrize("fmt", ["json", "xml", "csv"])
@pytest.mark.parametrize("compress", [True, False])
def test_export_format_compress_combination_succeeds(fmt, compress):
    result = export_data(format=fmt, compression=compress)
    assert result is not None
```

## Fixture Patterns

### Function-scoped fixtures (default)

```python
@pytest.fixture
def sample_user():
    return User(username="testuser", email="test@example.com")

def test_user_email_contains_at_sign(sample_user):
    assert "@" in sample_user.email
```

### Module-scoped fixtures for expensive setup

```python
@pytest.fixture(scope="module")
def database_connection():
    conn = create_db_connection()
    yield conn
    conn.close()
```

### tmp_path for file operations

Always use the built-in `tmp_path` fixture rather than hardcoded paths or manual `tempfile` calls:

```python
def test_file_creation_writes_content(tmp_path):
    file_path = tmp_path / "test_file.txt"
    file_path.write_text("test content")

    assert file_path.exists()
    assert file_path.read_text() == "test content"
```

### Factory fixtures

```python
@pytest.fixture
def user_factory():
    users = []

    def _create(username="test", email=None):
        user = User(username=username, email=email or f"{username}@example.com")
        users.append(user)
        return user

    yield _create

    for user in users:
        user.delete()

def test_multiple_users_have_distinct_usernames(user_factory):
    user1 = user_factory("alice")
    user2 = user_factory("bob")
    assert user1.username != user2.username
```

## Mocking Patterns

### Always use spec= (mandatory)

`MagicMock()` without `spec=` silently accepts any attribute — a class of bug that spec'd
mocks catch immediately. Always provide `spec=` or use `autospec=True`:

```python
from unittest.mock import MagicMock, AsyncMock, patch

# Correct — spec enforces the interface
mock_client = MagicMock(spec=requests.Session)
mock_db = MagicMock(spec=DatabaseConnection)

# Wrong — accepts any attribute, hides typos
mock_client = MagicMock()
```

### Patching with autospec

```python
def test_api_call_sends_correct_payload(mocker):
    mock_get = mocker.patch("requests.get", autospec=True)
    mock_get.return_value.json.return_value = {"status": "ok"}

    result = fetch_data_from_api()

    assert result["status"] == "ok"
    mock_get.assert_called_once()
```

### AsyncMock for coroutines

When mocking an `async def` function or a method that returns a coroutine, use `AsyncMock`
(not `MagicMock`). `MagicMock` for async code means `await mock()` returns another
`MagicMock` instead of executing the coroutine — the test passes but the assertion is wrong:

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_fetch_retries_on_503_then_succeeds():
    mock_response_fail = MagicMock()
    mock_response_fail.status_code = 503

    mock_response_ok = MagicMock()
    mock_response_ok.status_code = 200
    mock_response_ok.json.return_value = {"data": "value"}

    mock_client = MagicMock(spec=httpx.AsyncClient)
    # get is an async method — use AsyncMock
    mock_client.get = AsyncMock(side_effect=[mock_response_fail, mock_response_ok])

    result = await fetch_with_retry(mock_client, "https://example.com")

    assert result == {"data": "value"}
    assert mock_client.get.await_count == 2  # not .call_count
```

### Patching asyncio.sleep in async tests

```python
@pytest.mark.asyncio
async def test_retry_applies_exponential_backoff():
    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(side_effect=httpx.HTTPStatusError("503", ...))

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_with_retry(mock_client, "https://example.com", max_retries=2)

    # Verify sleep was awaited, not just called
    assert mock_sleep.await_count == 2
```

## Exception Testing

### Basic exception testing

```python
def test_invalid_input_raises_value_error():
    with pytest.raises(ValueError):
        process_data(None)
```

### Matching exception message

```python
def test_negative_age_raises_value_error_with_message():
    with pytest.raises(ValueError, match="must be positive"):
        create_user(age=-5)
```

### Asserting exception details

```python
def test_missing_required_field_raises_validation_error():
    with pytest.raises(ValidationError) as exc_info:
        validate_email("invalid-email")

    assert "email" in str(exc_info.value).lower()
```

## Async Testing Patterns

```python
@pytest.mark.asyncio
async def test_async_function_returns_expected_result():
    result = await async_operation()
    assert result is not None

@pytest.mark.asyncio
async def test_async_with_fixture(async_database):
    result = await async_database.query("SELECT 1")
    assert result is not None
```

Never use `asyncio.run()` inside a test function — let pytest-asyncio manage the event loop.

## Assertion Quality

Meaningful assertions check a specific value, not just existence or truthiness:

```python
# Correct — checks actual value
assert validate_email("user@example.com") is True
assert response.status_code == 200
assert len(items) == 3
assert error_message == "Email is required"

# Wrong — does not validate correctness
assert result                     # passes for any truthy value
assert result is not None         # passes even if result is wrong
assert True                       # never fails, tests nothing
```

## Edge Cases — Always Cover All Four

For every function that accepts user-facing input:
1. `None` input (if type signature allows it)
2. Empty string or empty collection
3. Boundary values (max/min allowed lengths or counts)
4. Invalid type or clearly malformed input

## Marker Patterns

```python
@pytest.mark.unit         # Fast, isolated, no I/O
@pytest.mark.integration  # Cross-component, real DB/API
@pytest.mark.e2e          # Full system, real file I/O
@pytest.mark.slow         # > 5 seconds — excluded from fast dev cycle
@pytest.mark.security     # Security validation
@pytest.mark.perf         # Performance benchmarks
```

### Conditional skipping

```python
@pytest.mark.skipif(sys.platform == "win32", reason="Unix only test")
def test_unix_specific_behavior():
    assert os.path.exists("/etc")
```

## Test Class Organization

```python
class TestUserAuthentication:
    """Group authentication-related tests."""

    def test_valid_credentials_return_authenticated_user(self):
        user = login("user", "correct_password")
        assert user.is_authenticated is True

    def test_wrong_password_raises_authentication_error(self):
        with pytest.raises(AuthenticationError):
            login("user", "wrong_password")

    def test_locked_account_raises_account_locked(self):
        with pytest.raises(AccountLocked):
            login("locked_user", "any_password")
```

## Property-Based Testing

```python
from hypothesis import given, strategies as st

@given(st.integers(), st.integers())
def test_addition_is_commutative(a, b):
    assert a + b == b + a

@given(st.lists(st.integers()))
def test_reversing_twice_returns_original_list(lst):
    assert list(reversed(list(reversed(lst)))) == lst
```

## Coverage Optimization

```python
# Test the happy path
def test_process_data_valid_input_returns_success():
    result = process_data(valid_input)
    assert result.success is True

# Test the error path explicitly
def test_process_data_invalid_input_returns_failure_message():
    result = process_data(invalid_input)
    assert result.success is False
    assert "invalid" in result.error_message.lower()

# Boundary values
@pytest.mark.parametrize("value,expected", [
    pytest.param(-1, False, id="below-minimum"),
    pytest.param(0, True, id="minimum-boundary"),
    pytest.param(50, True, id="midrange"),
    pytest.param(100, True, id="maximum-boundary"),
    pytest.param(101, False, id="above-maximum"),
])
def test_value_in_range_boundaries_return_expected(value, expected):
    assert is_valid_percentage(value) == expected
```

---

*For pytest command reference, see pytest-commands.md*
