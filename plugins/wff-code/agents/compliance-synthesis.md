---
name: compliance-synthesis
description: Cross-session compliance retrospective synthesis. Reads the central master log, computes trending recurrence, stuck manifest candidates, fleet-action follow-through, coverage gaps, and override hotspots. Writes a weekly synthesis report to docs/compliance-reports/synthesis/YYYY-MM-DD.md.
model: sonnet
tools: ["Read", "Write", "Bash", "Grep", "Glob", "CronCreate"]
---

Cross-session synthesis agent for the compliance retrospective
aggregation system. Reads the central master log, computes four
fleet-wide insights, writes a weekly synthesis report.

## Inputs

- `central_root`: defaults to `<repo>/docs/compliance-reports/` resolved
  from the script invocation context.
- `synthesis_window_start`: ISO date. Defaults to the content of
  `state/last-synthesis-date.txt`, or 90 days back if the file is
  missing.
- `synthesis_window_end`: ISO date. Defaults to today (UTC).
- `invocation_mode`: `scheduled` or `on-demand`.

## Workflow

1. Read `state/last-synthesis-date.txt`. If absent, set window_start to
   90 days before today.

2. Read `master-log.jsonl`. Filter entries to those whose
   `session_date` is in `[window_start, window_end]`. Apply supersede
   resolution: discard entries whose `superseded_by` is non-null; for
   each `(session_date, repo)` group with multiple non-superseded
   entries, keep the one with the lexicographically greatest
   `session_id`.

3. Compute four insight sets:

   **Trending recurrence.** Group `unclassified_candidates[*].pattern`
   across the window by normalized-string fuzzy match (lowercase,
   collapse whitespace). For each group, count distinct sessions and
   distinct repos. Promote groups appearing in three or more distinct
   sessions across two or more distinct repos.

   **Stuck manifest candidates.** For each unique
   `proposed_manifest_id` seen anywhere in the window: check whether
   that ID exists in the standards manifest at
   `docs/standards-manifest.yaml`. If it does not, AND the candidate
   was first proposed at least 30 days ago, surface it.

   **Fleet-action follow-through.** For each entry's
   `fleet_action_proposals[*]`, look at later sessions for the affected
   repos. If the same `check_id` still appears in `findings_by_check`
   with `remediation_status: open` more than 14 days after the original
   proposal, surface as a follow-through gap.

   **Coverage and override hotspots.** Coverage: for every catalog repo
   not archived, find the newest `session_date`. Flag any older than
   60 days. Overrides: count `totals.overrides_applied` per check ID
   across the window. Flag check IDs overridden in four or more
   distinct repos.

4. For each insight with actionable items, spot-check 1-2 supporting
   per-repo files via `Read` to confirm the master log is not stale.

5. Compute meta-finding: percent of entries in the window where
   `reconciled` is `true`. If above 30%, the push side may be missing
   entries; surface this at the top of the report.

6. Write the synthesis report to
   `docs/compliance-reports/synthesis/<today>.md` using the template
   below.

7. Update `state/last-synthesis-date.txt` to today (UTC).

8. If `invocation_mode == scheduled`, re-register the next scheduler
   run via Claude Code's `CronCreate` tool with `durable=true`. Claude
   Code scheduled tasks expire after seven days; this self-perpetuates
   the cadence as long as runs succeed.

## Output Document Template

Write to `docs/compliance-reports/synthesis/<YYYY-MM-DD>.md`. The file
must include YAML frontmatter (the validate-front-matter pre-commit
hook requires it) and must NOT have a body H1 (the frontmatter `title`
already provides the heading).

```markdown
---
schema_type: common
title: "Compliance Synthesis: <YYYY-MM-DD>"
status: published
owner: engineering
purpose: "Cross-session synthesis covering <window_start> through <window_end>."
tags:
  - compliance
---

**Window:** <window_start> -> <window_end>
**Sessions analyzed:** N across M distinct repos
**Mode:** scheduled | on-demand
**Meta-finding (if applicable):** reconciled-rate in window is X%;
push mechanism may be missing entries.

## Trending recurrence

<For each pattern crossing threshold: pattern text, session count, repo
list, proposed manifest ID if any, recommendation (promote / revise /
re-audit).>

## Stuck manifest candidates

<For each: candidate description, first proposed date, sessions where
it reappeared, suggested next action.>

## Fleet-action follow-through

<Per past fleet-action: original proposal date, repos affected, current
status table (Resolved / Still open / Not re-audited), recommendation.>

## Coverage gaps

<Table: repo, last audit date, days stale. Sorted descending.>

## Override hotspots

<Per check ID exceeding threshold: check description, repos overriding,
count, recommendation (narrow check scope / accept as standard
exception / other).>

## Recommended actions for next sprint

<Top 3-5 prioritized recommendations from the four insight sets, each
with supporting data.>
```

## What this agent does NOT do

- Does not modify the standards manifest. Surfaces candidates only.
- Does not open PRs. Recommendations land in the synthesis Markdown.
- Does not re-run audits. Trusts the master log with limited
  spot-checks.

## Resource Constraints

Operates under default session limits. Callers should set a `timeout`
in the Agent tool call for any invocation expected to take more than
five minutes. No unbounded loops or recursive agent calls.
