---
name: test-coverage
description: >
  Analyze test coverage gaps, generate missing tests, enforce coverage
  thresholds, and audit Codecov configuration. Supports pytest (Python)
  and Vitest (JS/TS). Runs coverage measurement, identifies uncovered
  functions ranked by criticality, generates idiomatic tests via iterative
  refinement, validates quality through a reviewer subagent, and verifies
  Codecov flags/components/Test Analytics align with testing standards.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - Task
---

# Test Coverage Agent

## Invocation Modes

This skill supports three modes based on the arguments provided:

### Mode 1: Analyze (default)

When invoked with no arguments or `analyze`:

1. Auto-detect framework by checking pyproject.toml, pytest.ini, package.json
2. Run `pytest --cov=src --cov-report=json:coverage.json --cov-branch -q`
3. Parse coverage.json using the bundled parser script
4. Identify files below the project threshold (default: 80%)
5. For each under-covered file, identify uncovered functions via AST analysis
6. Rank gaps by: (a) zero-coverage functions first, (b) lowest coverage %,
   (c) most recently modified (git log), (d) highest cyclomatic complexity
7. Present a structured coverage report with actionable recommendations

### Mode 2: Generate

When invoked with `generate` or `generate <file_path>`:

1. Run Mode 1 analysis if no current coverage.json exists
2. For single-file targets, use annotate format for LLM-friendly context:
   `pytest --cov=<source_module> --cov-report=annotate:cov_annotate --cov-branch`
   Lines prefixed with `!` in the annotated output are uncovered.
3. For each target file (or specified file):
   **Pre-analysis read step:** Before identifying gaps, read (1) the production code to understand all branches and edge cases, and (2) the test file in full to understand what is already covered. Do not infer coverage from the requester's description -- build the gap list from direct observation of both files. This prevents flagging gaps that are already covered and missing gaps that are genuinely present.
   a. Read the source file and any existing test file
   b. Spawn the test-writer subagent with source, uncovered lines, and
      existing test patterns as context
   c. Writer generates tests following project conventions from CLAUDE.md
   d. Run generated tests: `pytest <test_file> --cov=<source> -v`
   e. If tests fail, feed errors back to writer (up to 3 iterations)
   f. Once passing, spawn test-reviewer subagent for quality check.
      Require the reviewer to return only a JSON object matching this schema:
      `{"verdict": "APPROVE"|"NEEDS_WORK", "issues": [str]}`
      Schema notation: `|` separates allowed values; `[str]` means an array
      of strings. The reviewer must emit a concrete JSON instance, not the
      schema notation itself.
      Example APPROVE response:    `{"verdict": "APPROVE", "issues": []}`
      Example NEEDS_WORK response: `{"verdict": "NEEDS_WORK", "issues": ["add test for empty input"]}`
      The `issues` list is required when verdict is `NEEDS_WORK` (each entry
      is a specific, actionable instruction for the writer); empty list on
      `APPROVE`. A response without this structure should be treated as
      `NEEDS_WORK` with a single issue: "reviewer returned unparseable output."
   g. If reviewer returns NEEDS_WORK, pass the `issues` list verbatim to
      the writer as the revision brief (up to 2 rounds)
   h. If reviewer returns APPROVE, commit the test file
4. Re-run full coverage and present before/after comparison

### Mode 3: Enforce

When invoked with `enforce` or as part of a hook:

1. Run `pytest --cov=src --cov-report=json --cov-branch --cov-fail-under=80`
2. Parse results and check against per-file thresholds if configured.

   **Granularity disclaimer (Obs 469):** by default this skill enforces only the
   aggregate project gate (80% line / 70% branch) plus critical-module targets. There is
   NO default per-file, per-function, or per-branch floor. A high aggregate can mask
   individual files sitting far below it (observed: files at 29-49% while the project
   passed at 90%+). Per-file enforcement is opt-in via the `per_file_floor` key in
   `[tool.test-coverage-agent]` (see Configuration); when it is unset, do not claim or
   assume a per-file floor exists. If a user expects a per-file minimum, point them at
   that key rather than inferring protection the aggregate gate does not provide.
3. Apply quality gates (entry/exit criteria per ISO 25010):
   - Entry: all dependencies installed, database migrations current
   - Exit: coverage thresholds met, no CRITICAL security findings,
     type checking passes, SAST scan clean
4. Report pass/fail status with specific files that need attention
5. Exit with non-zero status if thresholds are not met

### Mode 4: Security Audit

When invoked with `security` or `security <path>`:

1. Run the OWASP dispatcher (owasp-dispatch agent) to detect
   applicable Top 10 lists based on codebase signals
2. For each applicable specialist, run review-code mode
3. For each applicable specialist, run review-tests mode
4. For CRITICAL/HIGH findings without test coverage, run generate mode
5. Present unified security report with findings by OWASP category

### Mode 5: Codecov Audit

When invoked with `codecov` or `audit-codecov`:

1. Check for `codecov.yaml` or `codecov.yml` at repository root
2. If not found, report as FAIL and recommend creating one per §16
3. If found, validate against Testing Standards §16 checklist:

   **Flag Validation:**
   a. List all directories under `tests/` (unit, integration, e2e, etc.)
   b. For each test directory, check that a matching flag exists in YAML
   c. For each flag, check that `coverage.status.project.<flag>` exists
      with a target matching §16.2 thresholds
   d. Check CI workflow files (`.github/workflows/*.yml`) for `-F <flag>`
      upload arguments -- each flag must have a matching CI upload

   **Component Validation:**
   e. List all directories under `src/`
   f. For each source directory, check that a matching component exists
   g. Check that `component_management.default_rules.statuses` sets
      project=80% and patch=90%
   h. Read `pyproject.toml` `[tool.test-coverage-agent].critical_modules`
   i. For each critical module, verify the component has a 90% override

   **Test Analytics Validation:**
   j. Check CI workflows for `codecov/test-results-action@v5` usage
   k. Check that pytest produces JUnit XML (`--junitxml` in CI commands)

   **Status Configuration:**
   l. Verify `coverage.status.patch.default.target` is 90%
   m. Check for `coverage.status.changes` (at least informational)
   n. Verify `github_checks.annotations: true`
   o. Verify `comment.show_carryforward_flags: true`

4. Present findings as a structured report:

   ```text
   ## Codecov Audit Report

   ### Flags
   ✅ unit: flag defined, status check at 85%, CI uploads with -F unit
   ❌ integration: flag defined but NO status check — add target 75%
   ❌ e2e: test directory exists but NO flag defined

   ### Components
   ✅ core: component defined, default rules apply (80%/90%)
   ❌ auth: critical module but component target is default 80% — override to 90%
   ✅ utils: component defined, default rules apply

   ### Test Analytics
   ❌ No test-results-action found in CI — add JUnit XML upload

   ### Status Checks
   ✅ Patch target: 90%
   ❌ Changes status: not configured — add informational check

   ### Summary: 5/9 checks passing
   ```

5. If `--fix` argument provided, generate a corrected `codecov.yaml`
   with all missing flags, components, targets, and Test Analytics config

## Configuration

The skill reads thresholds and preferences from pyproject.toml:

```toml
[tool.test-coverage-agent]
default_threshold = 80
patch_threshold = 90        # for new/changed code
critical_modules = ["auth", "payment", "data_processing"]
critical_threshold = 90
per_file_floor = 50         # optional; fails Enforce on any measured file below this.
                            # Unset by default: aggregate gate alone can mask
                            # low-coverage files (Obs 469).
exclude_patterns = ["*/migrations/*", "*/conftest.py"]
test_command = "pytest"
max_generation_iterations = 3
max_review_iterations = 2
```

## filterwarnings=error Is a Latent-Bug Detector (Obs 467)

When bringing a suite to `filterwarnings = ["error"]` conformance, treat it as a bug
detector, not just a style gate. Promoting warnings to errors converts silent latent
defects into visible failures: a previously-silent `ResourceWarning` (e.g. an
`HTTPError` caught but never closed, leaking a tempfile-backed stream that warns only at
GC) becomes a hard failure that pytest's unraisable plugin attributes to whichever test
was running. Fix these at the source (`e.close()` on the error branch), not with a
blanket ignore. Apply the policy incrementally and expect it to surface real
resource/Deprecation issues. Reserve a targeted, message-scoped, colon-free regex ignore
with documented rationale only for genuinely-expected warnings (e.g. a numerical-fallback
warning); never a blanket category ignore.

## Output Format

Coverage reports use this structure:

- Project summary: overall line%, branch%, file count
- Files below threshold: sorted worst-first with missing line ranges
- Uncovered functions: name, file, line range, current coverage %
- Recommendations: prioritized list of what to test next
- Before/after comparison (when generating)

## Coverage Scope Disclaimers

When analyzing or reporting coverage for a PR or task:

- Always qualify coverage claims with the measurement scope. "100% coverage" means 100% of the configured `coverage.run.source` directories. Scripts, migrations, fixtures, and other directories outside that scope are excluded from measurement by design.
- When a PR moves code from an excluded directory (e.g., `scripts/`) into the measured scope (e.g., `src/`), flag that the moved code may have zero coverage under the new path even if the PR claims full coverage. The coverage tool's changed-files scoping does not automatically add the moved file to the measured set.
- For refactoring PRs that extract helpers into new files, verify whether the new file path falls within the configured coverage source. A helper extracted to `scripts/helpers.py` has no coverage measurement even if it has 0% coverage. State this explicitly: "Coverage: N% of src/ package; scripts/ excluded from measurement by configuration."

$ARGUMENTS
