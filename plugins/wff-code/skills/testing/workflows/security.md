---
argument-hint: [attack-vector]
description: Generates security-focused tests covering OWASP Top 10: injection attacks, path traversal, DoS prevention, insecure deserialization, and input validation. Uses parametrize for attack vector coverage.
allowed-tools: Read, Write, Bash(pytest:*)
---

# Security Tester

Specialized security testing covering OWASP Top 10 attack vectors, input validation,
file handling security, and DoS prevention.

## Core Responsibilities

- **Input Validation**: Injection attacks (SQL, XSS, command, template, path traversal)
- **File Handling Security**: Malicious files, archive bombs, path traversal
- **DoS Prevention**: Resource exhaustion, infinite loops, large input handling
- **Insecure Deserialization**: Pickle, YAML, JSON safety
- **Access Control**: Authorization bypass, privilege escalation attempts

## Security Testing Approach

### Path Traversal Prevention

```python
@pytest.mark.security
class TestPathTraversalPrevention:
    """Test that path traversal attempts are blocked."""

    @pytest.mark.parametrize("malicious_path", [
        pytest.param("../../../etc/passwd", id="unix-relative"),
        pytest.param("..\\..\\..\\windows\\system32", id="windows-relative"),
        pytest.param("....//....//....//etc/passwd", id="double-dot-slash"),
        pytest.param("%2e%2e%2f%2e%2e%2fetc%2fpasswd", id="url-encoded"),
        pytest.param("..%252f..%252fetc%252fpasswd", id="double-encoded"),
    ])
    def test_process_file_rejects_path_traversal(self, malicious_path):
        """Test that path traversal is prevented in file processing."""
        with pytest.raises((ValueError, PermissionError, OSError)):
            process_file(malicious_path)
```

### SQL Injection Prevention

```python
@pytest.mark.security
class TestSQLInjectionPrevention:
    """Test SQL injection attack prevention."""

    @pytest.mark.parametrize("sql_injection", [
        pytest.param("'; DROP TABLE users; --", id="drop-table"),
        pytest.param("' OR '1'='1", id="always-true"),
        pytest.param("1' UNION SELECT password FROM users--", id="union-select"),
        pytest.param("admin'--", id="comment-bypass"),
        pytest.param("' OR 1=1--", id="or-bypass"),
    ])
    def test_query_prevents_sql_injection(self, sql_injection):
        """Test that SQL injection attempts are safely parameterized."""
        # Should either sanitize, reject, or use parameterized queries
        # The raw injection string should never appear in executed SQL
        result = search_users(query=sql_injection)
        assert isinstance(result, list)  # Returns safely, no crash
```

### XSS Prevention

```python
@pytest.mark.security
@pytest.mark.parametrize("xss_payload", [
    pytest.param("<script>alert('XSS')</script>", id="script-tag"),
    pytest.param("javascript:alert('XSS')", id="javascript-protocol"),
    pytest.param("<img src=x onerror=alert('XSS')>", id="img-onerror"),
    pytest.param("<svg/onload=alert('XSS')>", id="svg-onload"),
    pytest.param("'-alert(1)-'", id="quote-break"),
])
def test_render_output_escapes_xss_payload(xss_payload):
    """Test that XSS payloads are escaped in rendered output."""
    output = render_content({"body": xss_payload})

    assert "<script>" not in output
    assert "javascript:" not in output
    assert "onerror=" not in output
```

### Command Injection Prevention

```python
@pytest.mark.security
@pytest.mark.parametrize("command_injection", [
    pytest.param("; ls -la", id="semicolon"),
    pytest.param("| cat /etc/passwd", id="pipe"),
    pytest.param("&& rm -rf /", id="and-and"),
    pytest.param("`cat /etc/passwd`", id="backtick"),
    pytest.param("$(cat /etc/passwd)", id="dollar-paren"),
])
def test_filename_input_prevents_command_injection(command_injection):
    """Test that command injection via filename is prevented."""
    filename = f"document{command_injection}.txt"

    with pytest.raises((ValueError, OSError)):
        process_filename(filename)
```

### File Handling Security

```python
@pytest.mark.security
def test_parser_handles_malformed_input_safely(tmp_path):
    """Test that malformed binary input doesn't crash the parser."""
    malformed = tmp_path / "malformed.bin"
    malformed.write_bytes(b"\x00\xFF\xFE\xFD\xFC\x00\x00")

    parser = FileParser()
    result = parser.parse(malformed)

    # Must not crash; should return structured error
    assert result.success is False
    assert result.error_message is not None


@pytest.mark.security
def test_archive_extraction_rejects_path_traversal_entries(tmp_path):
    """Test that archives with path traversal entries are rejected."""
    # Create an archive with a traversal entry
    malicious_archive = create_archive_with_traversal_entry(tmp_path)

    with pytest.raises((ValueError, OSError), match="path traversal|outside|not allowed"):
        extract_archive(malicious_archive, destination=tmp_path / "output")
```

### DoS Prevention

```python
@pytest.mark.security
@pytest.mark.timeout(5)  # Fail fast if processing hangs
def test_large_input_does_not_hang_or_exhaust_memory(tmp_path):
    """Test that very large input is rejected or handled within resource limits."""
    huge_file = tmp_path / "huge.txt"
    huge_file.write_text("x" * 100_000_000)  # 100 MB

    processor = DocumentProcessor(max_size_bytes=10_000_000)

    with pytest.raises((ValueError, OSError), match="too large|size limit|exceeds"):
        processor.process(huge_file)


@pytest.mark.security
@pytest.mark.timeout(5)
@pytest.mark.parametrize("deeply_nested", [
    pytest.param({"a": {"b": {"c": {"d": {"e": {}}}}}}, id="5-deep"),
    pytest.param(create_deeply_nested_dict(depth=1000), id="1000-deep"),
])
def test_deeply_nested_input_does_not_cause_stack_overflow(deeply_nested):
    """Test that deeply nested structures are handled without recursion errors."""
    # Should either process safely or reject with a controlled error
    try:
        result = parse_nested(deeply_nested)
        assert result is not None
    except (ValueError, RecursionError):
        pass  # Controlled rejection is acceptable
    except Exception as e:
        pytest.fail(f"Unexpected exception type: {type(e).__name__}: {e}")
```

### Insecure Deserialization

```python
@pytest.mark.security
def test_yaml_load_uses_safe_loader():
    """Test that YAML loading uses SafeLoader, not the unsafe Loader."""
    # yaml.load with unsafe Loader can execute arbitrary Python
    malicious_yaml = "!!python/object/apply:os.system ['echo hacked']"

    # Should raise or return safely — must not execute the command
    with pytest.raises(Exception):
        load_config_yaml(malicious_yaml)


@pytest.mark.security
def test_json_load_does_not_execute_code():
    """Test that JSON loading from user input is safe."""
    # JSON is inherently safe but validate the load path doesn't use eval()
    user_json = '{"key": "value"}'
    result = parse_user_input_json(user_json)
    assert result == {"key": "value"}
```

## OWASP Top 10 Coverage Checklist

When generating security tests, ensure coverage for:

1. **Injection** — SQL, NoSQL, XSS, command, template, path traversal
2. **Broken Access Control** — Path traversal, unauthorized resource access
3. **Cryptographic Failures** — Sensitive data in logs, plaintext secrets
4. **Insecure Design** — Missing input size limits, unbounded resource allocation
5. **Security Misconfiguration** — Default credentials, debug mode in prod
6. **Vulnerable Components** — Covered by `pip-audit` / `safety`, not test code
7. **Auth/Session** — Token exposure, session fixation (if app has auth)
8. **Software Integrity** — Insecure deserialization (Pickle, unsafe YAML)
9. **Logging/Monitoring** — Security events logged, not suppressed
10. **SSRF** — If app makes outbound HTTP requests based on user input

## Workflow

1. **Identify attack surface** — file inputs, user strings, API parameters, config files
2. **Select attack vectors** — use parametrize for injection family coverage
3. **Write security tests** — `@pytest.mark.security`, expected exception or safe return
4. **Verify no false security** — ensure the test actually exercises the protection
5. **Add `@pytest.mark.timeout`** — prevent DoS tests from hanging CI

## Integration Points

- **pytest-timeout** — `@pytest.mark.timeout(5)` to cap DoS test duration
- **bandit** — static security analysis: `uv run bandit -r src/`
- **pip-audit** — dependency vulnerability scan: `uv run pip-audit`
- **@pytest.mark.security** — mark classification for selective execution

---

*Nested workflow within testing skill. For comprehensive security audit and OWASP
assessment, use the `security-auditor` agent.*
