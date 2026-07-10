---
argument-hint: [workflow-name]
description: Creates end-to-end tests for complete workflows, CLI commands, API integrations, and multi-component scenarios. Tests full user journeys from input to verified output.
allowed-tools: Read, Write, Bash(pytest:*)
---

# E2E Tester

Creates end-to-end tests that validate complete user workflows using real dependencies,
real file I/O, and real interfaces — with minimal mocking.

## Core Responsibilities

- **CLI Workflow Testing**: Command invocation to output file/stdout validation
- **API Integration Testing**: Full request/response cycles against real or test servers
- **Pipeline Testing**: Multi-step transformations from input through all stages
- **Data Integrity Testing**: Round-trip and cross-format consistency validation
- **Error Recovery Testing**: How the system behaves during partial failures

## E2E vs Unit Tests

| Aspect | Unit | E2E |
|--------|------|-----|
| Dependencies | Mocked | Real |
| File I/O | `tmp_path` + mocks | `tmp_path` + real files |
| Speed | < 1s | 1–30s |
| Scope | One function | Full workflow |
| Mocking | Extensive | Minimal (external services only) |

## CLI Workflow Testing

Test CLI commands using Click's `CliRunner` or subprocess:

```python
@pytest.mark.e2e
class TestCLIProcessCommand:
    """End-to-end tests for the process CLI command."""

    def test_process_command_json_output_creates_valid_file(self, tmp_path):
        """Test that process command creates valid JSON output file."""
        from click.testing import CliRunner
        from myapp.cli import cli

        input_file = tmp_path / "input.txt"
        input_file.write_text("Hello world content")
        output_file = tmp_path / "output.json"

        runner = CliRunner()
        result = runner.invoke(cli, [
            "process",
            str(input_file),
            "--output", str(output_file),
            "--format", "json",
        ])

        assert result.exit_code == 0
        assert output_file.exists()

        data = json.loads(output_file.read_text())
        assert "content" in data
        assert data["content"] == "Hello world content"

    def test_process_command_missing_input_exits_nonzero(self, tmp_path):
        """Test that missing input file produces non-zero exit code."""
        from click.testing import CliRunner
        from myapp.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["process", str(tmp_path / "nonexistent.txt")])

        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "error" in result.output.lower()
```

## Multi-Step Pipeline Testing

Test complete workflows that chain multiple processing stages:

```python
@pytest.mark.e2e
class TestProcessingPipeline:
    """End-to-end tests for the complete processing pipeline."""

    def test_complete_workflow_produces_expected_output(self, tmp_path):
        """Test complete workflow from raw input to final output."""
        # Arrange — create realistic input
        input_file = tmp_path / "document.txt"
        input_file.write_text("Title: Example\n\nBody content here.")

        # Act — execute complete pipeline
        processor = DocumentProcessor()
        result = processor.process(input_file)
        output_path = tmp_path / "result"
        result.export(output_path, format="json")

        # Assert — verify end-to-end results
        assert result.success is True
        assert (output_path.with_suffix(".json")).exists()

        output = json.loads(output_path.with_suffix(".json").read_text())
        assert output["title"] == "Example"
        assert "Body content here" in output["body"]

    def test_pipeline_preserves_metadata_through_all_stages(self, tmp_path):
        """Test that metadata survives every processing stage."""
        input_file = tmp_path / "doc.txt"
        input_file.write_text("---\ntitle: My Doc\nauthor: Jane\n---\nContent")

        processor = DocumentProcessor()
        result = processor.process(input_file)

        assert result.metadata["title"] == "My Doc"
        assert result.metadata["author"] == "Jane"

        exported = json.loads(result.to_json())
        assert exported["metadata"]["title"] == "My Doc"
        assert exported["metadata"]["author"] == "Jane"
```

## Data Integrity and Round-Trip Testing

```python
@pytest.mark.e2e
def test_export_import_round_trip_preserves_data(tmp_path):
    """Test that data survives export/import round-trip without loss."""
    # Create and process document
    original = create_document(title="Round-trip test", content="Body text", tags=["a", "b"])

    # Export to JSON
    export_path = tmp_path / "export.json"
    original.save(export_path)

    # Import back
    loaded = Document.load(export_path)

    # Verify complete data integrity
    assert loaded.title == original.title
    assert loaded.content == original.content
    assert loaded.tags == original.tags
    assert loaded.created_at == original.created_at


@pytest.mark.e2e
@pytest.mark.parametrize("fmt", ["json", "yaml", "toml"])
def test_export_all_formats_produces_valid_parseable_output(tmp_path, fmt):
    """Test that export succeeds and produces parseable output for all formats."""
    doc = create_document(title="Test", content="Body")
    output_file = tmp_path / f"output.{fmt}"

    doc.export(output_file, format=fmt)

    assert output_file.exists()
    assert output_file.stat().st_size > 0
    # Verify it parses without error
    parsed = parse_file(output_file, fmt)
    assert parsed["title"] == "Test"
```

## API Integration Testing

```python
@pytest.mark.e2e
class TestAPIIntegration:
    """End-to-end tests against a real or test API server."""

    def test_create_then_retrieve_resource_returns_same_data(self, api_client):
        """Test that created resources can be retrieved with correct data."""
        # Create
        created = api_client.post("/items", json={"name": "Test Item", "value": 42})
        assert created.status_code == 201
        item_id = created.json()["id"]

        # Retrieve
        retrieved = api_client.get(f"/items/{item_id}")
        assert retrieved.status_code == 200
        assert retrieved.json()["name"] == "Test Item"
        assert retrieved.json()["value"] == 42

    def test_delete_resource_then_retrieve_returns_404(self, api_client):
        """Test that deleted resources return 404 on subsequent retrieval."""
        created = api_client.post("/items", json={"name": "To Delete"})
        item_id = created.json()["id"]

        delete_response = api_client.delete(f"/items/{item_id}")
        assert delete_response.status_code == 204

        get_response = api_client.get(f"/items/{item_id}")
        assert get_response.status_code == 404
```

## Error Recovery Testing

```python
@pytest.mark.e2e
def test_pipeline_handles_corrupt_input_gracefully(tmp_path):
    """Test that corrupt input produces a controlled error, not a crash."""
    corrupt_file = tmp_path / "corrupt.bin"
    corrupt_file.write_bytes(b"\x00\xFF\xFE\xFD\xFC")

    processor = DocumentProcessor()
    result = processor.process(corrupt_file)

    # Should not raise; should return structured error
    assert result.success is False
    assert result.error_message is not None
    assert "corrupt" in result.error_message.lower() or "invalid" in result.error_message.lower()


@pytest.mark.e2e
def test_pipeline_partial_failure_rolls_back_side_effects(tmp_path):
    """Test that a failure mid-pipeline does not leave partial output files."""
    input_file = tmp_path / "input.txt"
    input_file.write_text("content")
    output_file = tmp_path / "output.json"

    # Simulate a failure after the first stage
    with patch("myapp.stage2.process", side_effect=RuntimeError("stage2 failed")):
        with pytest.raises(RuntimeError):
            process_pipeline(input_file, output_file)

    # No partial output should exist
    assert not output_file.exists()
```

## E2E Fixtures

```python
@pytest.fixture(scope="session")
def api_client():
    """Create a test API client against a real test server."""
    from myapp.server import create_app
    from starlette.testclient import TestClient

    app = create_app(database_url="sqlite:///test.db")
    with TestClient(app) as client:
        yield client


@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace directory with standard structure."""
    (tmp_path / "input").mkdir()
    (tmp_path / "output").mkdir()
    (tmp_path / "config").mkdir()
    return tmp_path
```

## E2E Test Characteristics

**Use real dependencies**:
- Real file I/O with `tmp_path`
- Real HTTP clients (not httpx mocks)
- Complete execution paths

**Mark and document correctly**:
```python
@pytest.mark.e2e
@pytest.mark.slow  # if > 5 seconds
def test_complete_workflow_name(tmp_path):
    """Test [complete workflow description from user perspective]."""
    # Arrange: Create realistic inputs
    # Act: Execute complete workflow
    # Assert: Verify results at each stage + final output
```

**Parametrize format/config variants**:
```python
@pytest.mark.e2e
@pytest.mark.parametrize("config", [
    pytest.param({"mode": "fast"}, id="fast-mode"),
    pytest.param({"mode": "thorough"}, id="thorough-mode"),
])
def test_process_with_config_variant_produces_output(tmp_path, config):
    ...
```

---

*Nested workflow within testing skill. For comprehensive E2E strategy and test-engineer
delegation, use the `test-engineer` agent via the Agent tool (`subagent_type="test-engineer"`).*
