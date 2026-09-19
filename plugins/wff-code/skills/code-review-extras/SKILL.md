---
name: code-review-extras
description: Local delta on top of the vendored code-review skill. Adds a reference-graph pre-read pass (imported? config read?), a whole-file residuals scan for rule-remediation PRs, cross-referencing ADR factual claims against authoritative code comments, aggregation/invariant/guard-widening review heuristics, and scoped-claim and provenance checks for citations, guards, and migration scope. Use alongside code-review when reviewing a component or model pipeline, a SonarCloud or single-rule remediation PR, an ADR that documents a technical constraint, a grouping/dedup or invariant change, or a diagram/doc citation in a stacked PR. Triggers on: code review, model review, is this component wired, remediation PR residuals, ADR factual accuracy, defined but unreferenced, documented but unread, tiebreaker added, shared-predicate guard, migration scope.
---

# code-review-extras

Extends the vendored `code-review` skill (read-only, in `.submodules`). Contains only the delta: cheap grep-based passes that outperform a prose read, and recurring accuracy and design-review checks.

## Pre-read pass: verify wiring and config-liveness with grep before reading model code

Documentation and prose about what code does must be verified against what code actually references; the import/read graph is the fastest, highest-signal first pass. Before rating or reading any component in depth, grep the driver/entry-point scripts to confirm:

- the component is imported by something that produces the deliverable (`grep -rn "from <module>" scripts/`); and
- each parameter the component documents is actually read at runtime (`grep` for each documented parameter across the `.py` files).

A component excellent in isolation but unimported is a zero in the deliverable; a documented-but-unread config block is a claimed control with no effect. Treat "defined but unreferenced" and "documented but unread" as distinct, nameable defect classes. Both surfaced from seconds of grep and would have been missed by a model-by-model read, because each file looks correct in isolation; only the reference graph shows whether it is connected and whether its config is live.

A plain grep over-counts "is this read anywhere": comments, docstrings, and same-named parameters on unrelated functions all register as false hits (a grep-based sweep returned 0/69 "unread," an AST attribute-scan on the same question dropped it to 6, one a real production defect). When the grep count matters for the verdict, confirm with an AST attribute/name scan or an empirical check (add a probe, run it), not a raw grep count.

Additional pre-read checks worth running alongside the wiring pass:

- When a diagram or doc cites a specific file or symbol and the branch under review is stacked on unmerged work, verify the citation against the PR's base (`git ls-tree origin/<base>` or `gh api .../pulls/N/files`), not the working tree; a file can exist locally while being absent from the PR's actual base.
- When a change adds a data structure that carries the same kind of gated value an existing drift or validation guard protects, confirm in the same review that the guard is extended to walk the new path, not only the original one (a new `overrides:` block can introduce a second source of gated codes the existing drift test never walks).
- When a subagent or teammate reports a documented invariant as WRONG, re-read the cited source yourself and check whether the report silently tested a stricter proposition than the doc actually claimed (a shared-helper claim of "same refusal logic" was reported wrong against a stricter, unclaimed test of "temporally simultaneous") before relaying the verdict.
- When a finding contradicts a computed value that matches a golden or regression value verified against an external authority, reclassify it from "defect" to "confirm intent with the domain owner" rather than flagging it as a critical bug outright.
- When scoping a "migrate all sites using role/pattern X" task, discriminate the distinct intents behind that role or pattern first and hand the implementer an explicit include/exclude list; a raw grep count (e.g. "29/59 sites use role=X") conflates unrelated uses (an ARIA role standing in for a component boundary) and sweeps in sites out of scope.

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

## Aggregation, invariant, and guard-widening defects

Five recurring defect shapes in grouping, invariant, and guard code, each cheaper to catch by pattern than by re-deriving from scratch:

- When a grouping or dedup operation needs a tiebreaker among its survivors, treat that as evidence the grouping key is too narrow, not that the ranking needs tuning: a `(verdict, severity)` tiebreaker was needed only because the original key discarded real information the tiebreaker then had to reconstruct.
- A new constructor or setter invariant needs a repo-wide grep for construction sites and literal values, not just the test suites the change targeted; one such invariant passed every targeted-suite test but broke on a full-suite run against an unrelated off-taxonomy literal.
- Two guards conditioned on the same variable are one guard wearing two hats: flag shared-predicate "defense in depth" explicitly, since a startup guard and a downstream "independently reviewed" stamp both keying off one `environment` predicate meant one absence silently defeated both.
- When a diff widens the population a system handles (a new runner, a new tenant, a new record type), audit existing boolean conditions whose name describes a narrower proposition than what the code now depends on: `process.env.CI` quietly stopped meaning "Linux" once a Windows runner was added, and a platform-suffixed snapshot path kept the condition evaluating cleanly while the invariant behind it had already lapsed.
- A guard of the form "capability X is configured" that tests credential presence rather than capability availability silently decays at any vendor's published end-of-life; a safety guard that tested `openai_api_key or perspective_api_key` presence as proof of capability is this shape and needs a capability-level check instead.
