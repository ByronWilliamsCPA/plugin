---
name: health
description: Weighted code-health dashboard aggregator. Runs the existing quality, coverage, and SonarCloud checks, collects each signal, applies a weighting, and emits one dashboard with an overall grade plus a per-dimension breakdown (types, lint, tests/coverage, dead code, security). Use for an at-a-glance project health score. Triggers on health, health check, quality dashboard, code health, project health score.
user-invocable: true
---

# Health

> **Adapted concept.** Built from the gstack `/health` concept (MIT License),
> retrieved 2026-06-18 via `docs/tool-evals/skills-deep-dive-2026-06.md`. The
> dashboard idea is borrowed; this skill is authored fresh against our toolchain.
> The gstack `{{PREAMBLE}}` template token was stripped (we have no equivalent
> injection point). Adapted to our standards: em-dashes removed; every underlying
> check repointed to a real skill in this repo (`quality`, `test-coverage` /
> `testing`, `sonarcloud`); the skill-vs-agent boundary respected (this skill
> describes a workflow the caller runs, it does not invoke agents, per ADR-004).

## Overview

Health is an aggregator, not a checker. We already run type-checking, linting,
tests, dead-code, and security analysis as separate skills. Each gives a verdict
in its own format, on its own schedule, and nothing ties them together. Health
runs those checks, reads each result, weights the dimensions, and emits a single
dashboard: one overall grade plus a per-dimension breakdown.

It does not replace `quality`, `test-coverage`, `testing`, or `sonarcloud`. It
orchestrates them and summarizes the result. Per ADR-004, a skill does not invoke
agents; what follows is a workflow the caller executes, running each underlying
skill or command in turn and collecting its output.

## When to Use

- You want one number for project health, not five separate reports
- Before a release, to confirm no dimension has quietly degraded
- During a refactor, to watch a single dimension recover over time
- Reporting status to someone who will not read five tool outputs
- Periodic health sweep on a repo you have not touched recently

**When NOT to use:**

- You need to fix a specific failure: run the underlying skill directly
- Only one dimension matters right now (just run `quality` or `sonarcloud`)
- You have not run the underlying checks and cannot run them now: a dashboard
  built on stale or missing data is worse than no dashboard

## Dimensions and Weighting

Each dimension maps to an existing skill or command. The caller runs the source,
then health reads the result.

| Dimension | Source skill / command | Signal collected | Default weight |
| --- | --- | --- | --- |
| Types | `quality` (BasedPyright strict) | Type-error count | 0.20 |
| Lint | `quality` (Ruff format + lint) | Lint + format-diff count | 0.15 |
| Tests / coverage | `testing` then `test-coverage` | Pass rate, line + branch coverage | 0.30 |
| Dead code | `sonarcloud` (unused / unreachable) | Dead-code + duplication findings | 0.10 |
| Security | `sonarcloud` (issues + hotspots) | Open issues, unreviewed hotspots | 0.25 |

Weights sum to 1.00 and are **tunable**: a security-sensitive service may raise
Security to 0.40 and drop Dead code; a prototype may invert that. State the weights
in effect at the top of every dashboard so the grade is reproducible. Do not change
weights silently between runs on the same repo, a moving denominator hides drift.

Per-dimension score is 0 to 100. The overall score is the weighted sum:

```text
overall = sum(dimension_score * weight) over all dimensions with a known result
```

A dimension whose check did not run is **UNKNOWN**, not zero and not pass. See
Pre-Flight: UNKNOWN dimensions are excluded from the weighted sum, the remaining
weights are renormalized, and the dashboard names every excluded dimension. An
UNKNOWN is a hole in the report, never a silent pass.

## Grade Rubric

| Score | Grade | Reading |
| --- | --- | --- |
| 90 to 100 | A | Healthy. No dimension below 80. |
| 80 to 89 | B | Sound. One dimension may be weak; none failing. |
| 70 to 79 | C | Attention needed. A dimension is degrading. |
| 60 to 69 | D | At risk. A dimension is failing or near it. |
| 0 to 59 | F | Unhealthy. One or more dimensions failing outright. |

A high overall grade does not excuse a single failing dimension. If any dimension
scores below 50, cap the overall grade at C regardless of the weighted sum and flag
the dimension by name. One green-looking aggregate must never bury a red component.

## Sample Dashboard

```text
PROJECT HEALTH: my-service                            2026-06-19
Weights: types 0.20  lint 0.15  tests 0.30  dead 0.10  security 0.25
------------------------------------------------------------------
OVERALL: 82 / 100  (B)   [capped at C: security dimension < 50]
------------------------------------------------------------------
Dimension        Score  Weight  Signal
Types              95    0.20   0 type errors (BasedPyright strict)
Lint               90    0.15   3 lint findings, 0 format diffs
Tests / coverage   88    0.30   214 pass / 0 fail, 86% line, 74% branch
Dead code          70    0.10   4 unused symbols, 2.1% duplication
Security           45    0.25   2 open issues, 5 unreviewed hotspots
------------------------------------------------------------------
EXCLUDED (UNKNOWN): none
------------------------------------------------------------------
Effective grade: C  (security below 50 caps the B)
Next action: triage the 5 unreviewed hotspots via `sonarcloud`
```

When a check did not run, the dashboard says so explicitly:

```text
EXCLUDED (UNKNOWN): Tests / coverage (suite not run this session)
Renormalized weights over 4 known dimensions: types 0.25 lint 0.19
  dead 0.13 security 0.31
NOTE: overall grade reflects 4 of 5 dimensions. Run `testing` for a full score.
```

## Pre-Flight

Before computing any grade, confirm each dimension's underlying check actually ran
in this session and produced a result you can read.

1. For each dimension, locate the source check's output (`quality`, `testing` +
   `test-coverage`, `sonarcloud`). If it ran, record the signal.
2. If a check did not run, could not run, or errored, mark that dimension
   **UNKNOWN**. Never infer a pass from absence. A check that was skipped because
   "it usually passes" is UNKNOWN, not 100.
3. Exclude UNKNOWN dimensions from the weighted sum, renormalize the remaining
   weights, and list every excluded dimension in the dashboard.
4. Confirm the weights in effect and print them at the top. If the caller asked
   for non-default weights, use those and say so.

Only after Pre-Flight passes do you compute and present the grade.

## Common Rationalizations

| Rationalization | Reality |
| --- | --- |
| "CI is green, the aggregate is healthy, skip it" | Green CI means the gates that exist passed. It says nothing about coverage trend, hotspot backlog, or dead code that no gate blocks on. The dashboard surfaces what CI does not gate. |
| "The test suite usually passes, count it as 100" | A check you did not run is UNKNOWN. Counting an unrun check as pass is the exact failure this skill exists to prevent. |
| "Security findings are mostly false positives, score it high" | Triage them via `sonarcloud` and let the score reflect the triaged result. Inflating the score by hand makes the dashboard fiction. |
| "Overall is a B, ship it" | Check whether any single dimension is below 50. One failing component caps the grade at C; the weighted sum can hide it. |
| "I'll tweak the weights so it reads better" | Weights are a policy decision stated up front, not a dial to reach a target grade. Changing weights to move the number is grade laundering. |
| "Re-running everything is slow, reuse last week's numbers" | Stale signals produce a confident-looking but wrong grade. Mark anything you did not run this session as UNKNOWN. |

## Red Flags

- Reporting an overall grade while any dimension is UNKNOWN but uncounted
- Treating a skipped or errored check as a pass
- A B or A grade printed while a dimension scores below 50
- Weights that do not sum to 1.00, or weights changed silently between runs
- A dashboard with no weights line and no date (not reproducible)
- Inventing a dimension score without the underlying check's output in hand
- Running `health` as a substitute for fixing a known failure in `quality` or
  `sonarcloud` (it reports, it does not remediate)

## Interaction with Other Skills

- **`quality`**: source for the Types and Lint dimensions. Run it first.
- **`testing` and `test-coverage`**: source for the Tests / coverage dimension.
- **`sonarcloud`**: source for the Dead code and Security dimensions.
- **`phase-gate`**: a phase gate is a pass/fail boundary; health is a graded
  snapshot. Use health to see the trend, the gate to decide phase closure.

## Verification

After producing a dashboard:

- [ ] Every dimension shows a real signal from a check run this session, or UNKNOWN
- [ ] No UNKNOWN dimension was counted as a pass
- [ ] Weights are printed, sum to 1.00, and were not changed to hit a target
- [ ] Any dimension below 50 caps the overall grade at C and is named
- [ ] The dashboard carries a date and the repo name (reproducible)
- [ ] A next action points at the source skill for the weakest dimension
