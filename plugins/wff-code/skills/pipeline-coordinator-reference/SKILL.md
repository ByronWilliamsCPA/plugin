---
name: pipeline-coordinator-reference
description: Non-user-invokable reference showing the Command -> Agent -> Skill coordinator pattern with explicit Data Contract blocks between pipeline stages. Uses test-coverage pipeline as the concrete example.
user-invocable: false
---

# Pipeline Coordinator Reference

## Overview

A coordinator pipeline chains multiple specialized agents in sequence. Each agent does
one thing well, hands a typed output to the next stage, and the coordinator stitches
them together. This is distinct from parallel dispatch (where agents work concurrently
on independent problems): here, each stage depends on the output of the previous stage.

The key discipline is the **Data Contract** between stages. Coordinators that omit
explicit contracts accumulate silent failures: the second agent silently works on
stale context, wrong file paths, or missing fields. Every stage transition must carry
a machine-readable schema the consuming agent can validate against.

This document uses a four-stage test-coverage pipeline as the concrete example.

## When to Use

Use the coordinator pattern when:

- Each stage needs output from the previous stage before it can begin
- The problem decomposes naturally into exploration, analysis, generation, and summary
- Agents have different specializations (explore vs. write vs. summarize)
- The total work exceeds what a single agent can do reliably in one pass

Use simpler alternatives when:

- All tasks are independent: use the parallel dispatch pattern instead
  (`.claude/skills/dispatching-parallel-agents/SKILL.md`)
- The task fits in a single well-scoped agent prompt with no chaining needed
- There are only two stages: a single subagent call with a return contract is enough

Decision guide:

```text
Is there a natural sequence of dependencies?
  No  -> Use dispatching-parallel-agents or a single agent
  Yes -> How many stages?
           1-2  -> Single subagent with a return contract
           3+   -> Coordinator pipeline (this pattern)
```

## The Pattern

The test-coverage pipeline has four stages:

1. Explore: find untested files and measure coverage gaps
2. Gap Analysis: rank gaps by risk and priority
3. Test Writer: generate tests for the highest-priority files
4. Summary: report what was written and the estimated coverage delta

The coordinator owns stage transitions. It dispatches each agent, waits for output,
validates the contract, and passes the result to the next stage.

---

### Stage 1: Explore

**Agent dispatched:** An explore subagent with read-only filesystem access.

**Context provided to the agent:**

- Repository root path
- Language and test framework (for example, Python with pytest)
- Coverage threshold defined in the project (for example, 80% line coverage)
- Location of any existing coverage reports (for example, `.coverage`, `htmlcov/`)

**Agent task:**

> You are an explore agent. Your job is to identify Python files that lack adequate
> test coverage.
>
> 1. Run `uv run pytest --cov=src --cov-report=json --quiet` to generate a coverage
>    report. If a `.coverage` or `coverage.json` file already exists and is less than
>    one hour old, use it directly.
> 2. Parse the JSON coverage report and collect every file where line coverage is below
>    {THRESHOLD}%.
> 3. For each under-covered file, record: the file path relative to repo root, current
>    line coverage percentage, number of uncovered lines, and the line ranges that are
>    not covered.
> 4. Return ONLY the JSON object described in the Data Contract below. Do not add prose
>    or explanation.

**What the explore agent returns:** A JSON object conforming to the contract below.

---

### Data Contract: Stage 1 -> Stage 2

The explore agent returns this JSON structure. The gap-analysis agent must receive
exactly this shape; the coordinator validates required fields before passing it on.

```jsonc
{
  // Schema version. Bump when fields are added or removed.
  "schema_version": "1.0",

  // ISO-8601 timestamp when the coverage data was collected.
  "collected_at": "2026-04-13T10:00:00Z",

  // Absolute path to the repository root.
  "repo_root": "/home/user/project",

  // The coverage threshold that triggered inclusion (percentage, integer).
  "threshold_pct": 80,

  // Array of files below threshold. May be empty if all files pass.
  "gaps": [
    {
      // Path relative to repo_root.
      "file": "src/billing/invoices.py",

      // Current line coverage as a percentage (float, 0-100).
      "coverage_pct": 42.3,

      // Number of lines not covered by any test.
      "uncovered_lines": 87,

      // Line ranges not covered, as [start, end] pairs (inclusive).
      "uncovered_ranges": [[12, 30], [55, 98], [140, 166]]
    }
    // ... one entry per under-covered file
  ],

  // Any errors encountered (for example, files that could not be parsed).
  "errors": []
}
```

**Validation rules the coordinator must enforce before Stage 2:**

- `schema_version` is present and equals `"1.0"`
- `repo_root` is a non-empty string
- `threshold_pct` is a number between 0 and 100
- `gaps` is an array (may be empty)
- `errors` is empty (a non-empty `errors` array means the coverage run failed; abort with the errors list)
- Each gap entry has `file`, `coverage_pct`, and `uncovered_lines`
- If `gaps` is empty, skip Stages 2 and 3; go directly to Stage 4 with a trivial summary

If any required field is missing and no skip condition applies, the coordinator must stop the pipeline and report the failure to the user with: the stage number (Stage 1), the missing field name, and the raw output from the failing stage.

---

### Stage 2: Gap Analysis

**Agent dispatched:** A general-purpose analysis agent (no specialized tools required).

**Context provided to the agent:**

- The full JSON output from Stage 1 (the explore contract above)
- A risk rubric: the coordinator passes criteria for what makes a file high-risk
  (for example, files in `billing/`, `auth/`, `payments/` score higher)
- The maximum number of files to hand to the test-writer (default: 3)

**Agent task:**

> You are a gap-analysis agent. You receive a JSON coverage report and must prioritize
> which files to test first.
>
> Risk scoring rules:
> - +3 points if the file path contains any of: billing, auth, payment, security
> - +2 points if uncovered_lines > 50
> - +1 point if coverage_pct < 30
> - +1 point if the file has more than 3 uncovered ranges
>
> For each file in `gaps`, compute a risk score, then return the top {MAX_FILES} files
> sorted by score descending. Return ONLY the JSON object described in the Data Contract
> below. Do not add prose or explanation.

**What the gap-analysis agent returns:** A JSON object conforming to the contract below.

---

### Data Contract: Stage 2 -> Stage 3

```jsonc
{
  "schema_version": "1.0",

  // ISO-8601 timestamp for this analysis.
  "analyzed_at": "2026-04-13T10:01:00Z",

  // Carried forward unchanged from Stage 1 output.
  "repo_root": "/home/user/project",

  // Files selected for test generation, ordered by priority (highest first).
  "targets": [
    {
      // Path relative to repo_root (carried forward from Stage 1).
      "file": "src/billing/invoices.py",

      // Risk score computed in Stage 2.
      "risk_score": 6,

      // Coverage data carried forward from the Stage 1 contract.
      "coverage_pct": 42.3,
      "uncovered_lines": 87,
      "uncovered_ranges": [[12, 30], [55, 98], [140, 166]],

      // One-sentence rationale for inclusion.
      "rationale": "Billing module with 87 uncovered lines and score of 6."
    }
    // ... up to MAX_FILES entries
  ],

  // Files that were below threshold but not selected (for audit purposes).
  "deferred": [
    {
      "file": "src/utils/formatting.py",
      "risk_score": 1,
      "reason": "Low risk; utility-only code."
    }
  ]
}
```

**Validation rules the coordinator must enforce before Stage 3:**

- `targets` is a non-empty array (if empty, skip Stage 3; go to Stage 4 with a note)
- Each target has `file`, `risk_score`, and `uncovered_ranges`
- `targets` length does not exceed `MAX_FILES`

If any required field is missing and no skip condition applies, the coordinator must stop the pipeline and report the failure to the user with: the stage number (Stage 2), the missing field name, and the raw output from the failing stage.

---

### Stage 3: Test Writer

**Agent dispatched:** A test-writer agent with file read and write access.

**Context provided to the agent:**

- The full JSON output from Stage 2 (the gap-analysis contract above)
- Absolute path to `repo_root` (so it can construct full file paths)
- Project conventions: test directory, naming pattern, framework, fixture locations
- Instruction to NOT modify production code

**Agent task:**

> You are a test-writer agent. For each file in `targets`, generate pytest tests that
> cover the uncovered line ranges listed in `uncovered_ranges`.
>
> For each target file:
> 1. Read the source file at `{repo_root}/{file}`.
> 2. Read any existing test file for this module if one exists.
> 3. Write new tests that exercise the uncovered ranges. Focus on behavior, not line
>    counts. Use existing fixtures where available.
> 4. Write the tests to `{repo_root}/tests/{module_path}/test_{basename}.py` (or
>    append to the existing test file if one exists).
> 5. Do NOT modify production source files.
> 6. After writing, run `uv run pytest {test_file} -q` to confirm the tests pass.
>    If a test fails, fix it before reporting.
>
> Return ONLY the JSON object described in the Data Contract below.

**What the test-writer agent returns:** A JSON object conforming to the contract below.

---

### Data Contract: Stage 3 -> Stage 4

```jsonc
{
  "schema_version": "1.0",

  // ISO-8601 timestamp when test writing finished.
  "written_at": "2026-04-13T10:05:00Z",

  // One entry per target from Stage 2.
  "results": [
    {
      // Source file that was tested (relative to repo_root).
      "file": "src/billing/invoices.py",

      // Path of the test file written or updated (relative to repo_root).
      "test_file": "tests/billing/test_invoices.py",

      // Number of new test functions added.
      "tests_added": 5,

      // Names of each test function written.
      "test_names": [
        "test_invoice_total_rounds_to_two_decimals",
        "test_invoice_raises_on_negative_amount",
        "test_apply_discount_zero_edge_case",
        "test_apply_discount_over_100_raises",
        "test_mark_paid_sets_paid_at_timestamp"
      ],

      // Whether `pytest {test_file} -q` passed after writing.
      "passing": true,

      // If passing is false, the pytest error output (truncated to 500 chars).
      "error": null
    }
  ],

  // Files from Stage 2 targets that the agent could not write tests for.
  "skipped": [
    {
      "file": "src/billing/legacy_xml.py",
      "reason": "File uses deprecated C extension; cannot import in test environment."
    }
  ]
}
```

**Validation rules the coordinator must enforce before Stage 4:**

- `results` is an array (may be empty if all targets were skipped)
- Each result with `passing: false` is flagged in the Stage 4 summary
- The coordinator does NOT retry failed tests; it passes the failure forward for the human to review

---

### Stage 4: Summary

**Agent dispatched:** A general-purpose summary agent (no filesystem access needed).

**Context provided to the agent:**

- JSON output from Stage 1 (original gaps)
- JSON output from Stage 2 (selected targets)
- JSON output from Stage 3 (test results)
- The coverage threshold used

**Agent task:**

> You are a summary agent. Produce a concise markdown report from the three JSON
> inputs provided.
>
> Include:
> 1. How many files were below threshold before this run.
> 2. How many files were targeted for new tests.
> 3. For each tested file: name, tests added, and whether tests are passing.
> 4. Any skipped or failed files with their reasons.
> 5. A one-paragraph overall assessment of coverage progress.
>
> Format as markdown. Use plain language. Do not include raw JSON in the output.

**What Stage 4 produces:** A markdown summary delivered directly to the coordinator,
which returns it as the final output to the user. There is no further data contract
because this is the terminal stage.

---

## Coordinator Prompt Template

Use this template to wire the four stages together. Replace placeholders in
`{BRACES}` with actual values for each run.

```markdown
You are coordinating a four-stage test-coverage pipeline. Work through each stage in
order. Do not begin a stage until the previous stage is complete. After each stage,
validate the output against the stated schema before proceeding.

## Configuration

- repo_root: {ABSOLUTE_PATH_TO_REPO}
- language: Python
- test_framework: pytest
- coverage_threshold: {THRESHOLD_PCT}%
- max_targets: {MAX_FILES}
- high_risk_path_segments: {COMMA_SEPARATED_LIST}

## Stage 1: Explore

Dispatch a subagent with read access to {ABSOLUTE_PATH_TO_REPO}. Provide the
configuration above. Instruct the agent to return the Stage 1 JSON contract.

Validate: schema_version == "1.0", gaps is an array.
If gaps is empty: skip to Stage 4 with message "All files meet the coverage threshold."

## Stage 2: Gap Analysis

Pass the validated Stage 1 JSON to a general-purpose subagent.
Provide the risk rubric and max_targets from configuration.
Instruct the agent to return the Stage 2 JSON contract.

Validate: targets is a non-empty array, each entry has file and uncovered_ranges.
If targets is empty: skip to Stage 4 with message "No high-risk gaps found."

## Stage 3: Test Writer

Pass the validated Stage 2 JSON to a subagent with file read/write access.
Pass: repo_root from Stage 1, targets from Stage 2.
Provide test directory conventions.
Instruct the agent to return the Stage 3 JSON contract.

Validate: results is an array. Flag any entries where passing == false.

## Stage 4: Summary

Pass the JSON outputs from Stages 1, 2, and 3 to a general-purpose subagent.
Instruct the agent to return a markdown summary as described in Stage 4.

Return the summary as your final output.
```

## Common Mistakes

**Skipping the Data Contract:**
Without an explicit schema, the consuming agent guesses at field names. A field named
`coverage` in Stage 1 becomes `pct` in Stage 2 and `line_coverage` in Stage 3. The
coordinator cannot detect the drift and produces a silent failure.

**Passing full conversation history to each subagent:**
Each subagent should receive only the contract output from the previous stage plus
the configuration it needs. Passing the full coordinator history bloats context and
causes the agent to pick up stale instructions or prior errors.

**Not validating between stages:**
A coordinator that skips validation passes malformed data downstream. By the time
the failure surfaces in Stage 3 or 4, the root cause is buried three layers back.
Always check required fields before advancing.

**Retrying failures inside the pipeline:**
If Stage 3 produces a failing test, the coordinator should note it and continue.
Retrying inside the pipeline creates infinite loops and burns context. Surface the
failure to the human in Stage 4.

**Using a coordinator for independent tasks:**
If the explore stage could run in parallel with another unrelated task, use the
parallel dispatch pattern instead. Coordinators impose sequential cost; only pay
it when each stage truly depends on the previous output.

**Letting stage prompts drift from the contract:**
When you update the Stage 2 output schema, update the Stage 3 prompt that reads it.
Contract and prompt must stay in sync; they are two halves of the same interface.

## Sources

- Best-practice review (2026-04-11):
  `docs/development/best-practice-review/synthesis-report.md` (rows 83, 163)
- Parallel dispatch reference: `.claude/skills/dispatching-parallel-agents/SKILL.md`
- Test-coverage skill: `.claude/skills/test-coverage/SKILL.md`
