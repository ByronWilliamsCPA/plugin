---
argument-hint: [component]
description: Creates performance and load tests using pytest-benchmark and pytest-memray. Tests throughput, memory usage, latency SLAs, batch processing, and performance regression prevention.
allowed-tools: Read, Write, Bash(pytest:*)
---

# Performance Tester

Creates performance tests that benchmark throughput, validate memory constraints,
enforce latency SLAs, and prevent performance regressions.

## Core Responsibilities

- **Benchmark Testing**: Measure and compare operation speed with pytest-benchmark
- **Memory Profiling**: Validate memory usage stays within limits with pytest-memray
- **Latency SLA Tests**: Assert that critical operations complete within defined thresholds
- **Batch Processing**: Measure throughput for multi-item workloads
- **Regression Prevention**: Store baseline benchmarks and fail on significant regressions

## Benchmarking with pytest-benchmark

### Basic benchmark

```python
@pytest.mark.perf
def test_parse_document_benchmark(benchmark, sample_file):
    """Benchmark parse_document performance."""
    processor = DocumentProcessor()

    result = benchmark(processor.parse, sample_file)

    assert result.success is True
    # pytest-benchmark automatically captures: min, max, mean, stddev, rounds
```

### Comparing implementations

```python
@pytest.mark.perf
@pytest.mark.parametrize("strategy,label", [
    pytest.param(FastStrategy(), "fast", id="fast-strategy"),
    pytest.param(AccurateStrategy(), "accurate", id="accurate-strategy"),
    pytest.param(HybridStrategy(), "hybrid", id="hybrid-strategy"),
])
def test_strategy_performance_comparison(benchmark, sample_file, strategy, label):
    """Compare performance across processing strategies."""
    result = benchmark(strategy.process, sample_file)
    assert result.success is True
```

### Regression prevention via pyproject.toml

```toml
[tool.pytest.benchmark]
min_rounds = 5
max_time = 1.0
calibration_precision = 10
compare_fail = ["min:5%", "max:10%", "mean:5%"]
```

Run with: `uv run pytest --benchmark-compare=0001 --benchmark-compare-fail=mean:10%`

## Memory Profiling with pytest-memray

```python
@pytest.mark.perf
@pytest.mark.limit_memory("100 MB")
def test_process_large_file_stays_within_memory_limit(tmp_path):
    """Test that processing a large file does not exceed 100 MB."""
    large_file = tmp_path / "large.txt"
    large_file.write_text("x" * 10_000_000)  # 10 MB file

    processor = DocumentProcessor()
    result = processor.process(large_file)

    assert result.success is True
    # pytest-memray fails the test if peak memory > 100 MB


@pytest.mark.perf
@pytest.mark.limit_memory("500 MB")
def test_batch_processing_1000_items_memory_bounded(tmp_path):
    """Test that processing 1000 items stays under 500 MB."""
    items = [create_item(i) for i in range(1000)]

    processor = BatchProcessor()
    results = processor.process_all(items)

    assert len(results) == 1000
    assert all(r.success for r in results)
```

## Latency SLA Tests

For operations with explicit SLAs, assert durations directly:

```python
import time

@pytest.mark.perf
@pytest.mark.parametrize("item_count,max_seconds", [
    pytest.param(10, 1.0, id="small-batch"),
    pytest.param(100, 5.0, id="medium-batch"),
    pytest.param(1000, 30.0, id="large-batch"),
])
def test_batch_processing_meets_latency_sla(tmp_path, item_count, max_seconds):
    """Test that batch processing meets latency SLA for different batch sizes."""
    items = [create_item(i) for i in range(item_count)]

    start = time.perf_counter()
    results = BatchProcessor().process_all(items)
    duration = time.perf_counter() - start

    assert all(r.success for r in results)
    assert duration < max_seconds, f"Batch of {item_count} took {duration:.2f}s (limit: {max_seconds}s)"


@pytest.mark.perf
def test_api_response_p95_under_200ms(api_client):
    """Test that the 95th-percentile API response time is under 200ms."""
    import statistics

    durations = []
    for _ in range(100):
        start = time.perf_counter()
        response = api_client.get("/health")
        durations.append(time.perf_counter() - start)

    assert response.status_code == 200
    p95 = sorted(durations)[94]  # 95th percentile
    assert p95 < 0.2, f"p95 latency {p95:.3f}s exceeds 200ms threshold"
```

## Batch and Throughput Testing

```python
@pytest.mark.perf
def test_concurrent_processing_throughput_meets_target(tmp_path):
    """Test that concurrent processing achieves target throughput."""
    import concurrent.futures
    import time

    items = [create_item(i) for i in range(50)]
    processor = DocumentProcessor()

    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(processor.process, items))
    duration = time.perf_counter() - start

    assert all(r.success for r in results)
    throughput = len(items) / duration
    assert throughput > 10, f"Throughput {throughput:.1f} items/s below 10 items/s target"
```

## Performance Test Fixtures

```python
@pytest.fixture(scope="session")
def sample_file(tmp_path_factory):
    """Create a realistic sample file for benchmarking (session-scoped)."""
    tmp_path = tmp_path_factory.mktemp("perf")
    file = tmp_path / "sample.txt"
    file.write_text("Sample content paragraph. " * 500)
    return file


@pytest.fixture(scope="session")
def large_file(tmp_path_factory):
    """Create a large file for memory/scale tests (session-scoped)."""
    tmp_path = tmp_path_factory.mktemp("perf_large")
    file = tmp_path / "large.txt"
    file.write_text("Large content line\n" * 50_000)
    return file
```

Use `scope="session"` for expensive setup fixtures in performance tests — creating
the same large file 50 times inflates benchmark times.

## Markers and Classification

```python
@pytest.mark.perf     # Performance test — always include
@pytest.mark.slow     # If runtime > 5 seconds — excluded from fast dev cycle
@pytest.mark.benchmark  # If using pytest-benchmark fixture
```

## Integration Points

- **pytest-benchmark**: `benchmark` fixture, `--benchmark-compare`, `.benchmarks/` storage
- **pytest-memray**: `@pytest.mark.limit_memory("X MB")`, `--memray` flag
- **time.perf_counter**: For explicit duration assertions without benchmark overhead
- **concurrent.futures**: For throughput and parallelism tests

## Configuration

```toml
# pyproject.toml
[tool.pytest.benchmark]
min_rounds = 5
max_time = 2.0
calibration_precision = 10
compare_fail = ["min:5%", "mean:5%"]
storage = ".benchmarks"

[tool.pytest.ini_options]
markers = [
    "perf: Performance and benchmark tests",
    "slow: Tests taking > 5 seconds",
    "benchmark: Tests using pytest-benchmark fixture",
]
```

## Test Documentation Standard

```python
@pytest.mark.perf
@pytest.mark.slow
def test_performance_scenario(benchmark):
    """
    Test [performance aspect being measured].

    Performance Criteria:
    - Operation should complete in < X seconds
    - Memory usage should be < Y MB
    - Throughput should be > Z items/second

    Baseline: Established YYYY-MM-DD at commit <hash>
    """
```

---

*Nested workflow within testing skill. For profiling and optimization strategy,
use the `test-engineer` agent via the Agent tool (`subagent_type="test-engineer"`).*
