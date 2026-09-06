---
name: code-review-extras
description: Local delta on top of the vendored code-review skill. Adds a reference-graph pre-read pass (imported? config read?), a whole-file residuals scan for rule-remediation PRs, and cross-referencing ADR factual claims against authoritative code comments. Use alongside code-review when reviewing a component or model pipeline, a SonarCloud or single-rule remediation PR, or an ADR that documents a technical constraint. Triggers on: code review, model review, is this component wired, remediation PR residuals, ADR factual accuracy, defined but unreferenced, documented but unread.
---

# code-review-extras

Extends the vendored `code-review` skill (read-only, in `.submodules`). Contains only the delta: cheap grep-based passes that outperform a prose read, and two recurring accuracy checks.

## Pre-read pass: verify wiring and config-liveness with grep before reading model code

Documentation and prose about what code does must be verified against what code actually references; the import/read graph is the fastest, highest-signal first pass. Before rating or reading any component in depth, grep the driver/entry-point scripts to confirm:

- the component is imported by something that produces the deliverable (`grep -rn "from <module>" scripts/`); and
- each parameter the component documents is actually read at runtime (`grep` for each documented parameter across the `.py` files).

A component excellent in isolation but unimported is a zero in the deliverable; a documented-but-unread config block is a claimed control with no effect. Treat "defined but unreferenced" and "documented but unread" as distinct, nameable defect classes. Both surfaced from seconds of grep and would have been missed by a model-by-model read, because each file looks correct in isolation; only the reference graph shows whether it is connected and whether its config is live.

## Rule-remediation PRs: scan all files for residuals, not just the targeted scope

A remediation PR that fixes most of a rule's findings will still show residual alerts on merge, because the scanner analyzes all new code in the PR, not just your scope. For each rule being fixed, scan ALL files (not just the targeted set), classify each remaining instance as "pre-existing and out of scope" vs "missed in scope," and call them out explicitly in the PR body. This prevents false-alarm triage after merge, e.g. a duplicate workflow-level permissions block or an `${{ inputs.* }}` reference inside a `run:` block that predates the PR but will still be flagged.

## Contradictory linters on one construct: localize behind one typed helper, do not oscillate

When two configured linters give opposite directives on the same token, editing that token in
place cannot satisfy both: each single-rule fix re-violates the other. Recognize the conflict
as structural, not a "pick the right rule" decision, and resolve it with indirection. Extract
the construct into one named helper that contains the contested literal exactly once, then turn
every call site into a plain call. Worked example: ruff TC006 requires `cast()` type
expressions quoted (`cast("dict[str, object]", x)`); SonarCloud S1192 flags any string literal
repeated 3+ times. Four quoted casts trip S1192; a quoted alias re-trips S1192 on the alias;
an unquoted alias trips TC006. The escape is a single helper:

```python
def _as_map(v: object) -> dict[str, object]:
    return cast("dict[str, object]", v)
```

The quoted cast appears once (TC006 satisfied, S1192 needs 3+ to fire) and every call site
becomes `_as_map(x)`. Each linter sees the construct once, in the form it wants.

## ADRs: cross-reference factual claims against authoritative code comments

An ADR that reaches the correct conclusion via incorrect reasoning is still a documentation liability: future authors learn the wrong mental model even when the decision is right. When reviewing an ADR that documents a technical constraint, cross-reference its factual claims against existing authoritative comments in the affected code, not just the conclusion. An ADR stated an OIDC `repository` claim resolves to the calling repo while the authoritative workflow comment said it resolves to the `.github` repo; both reached the same decision via contradictory reasoning. Verify the rationale against the code, not only the verdict.
