---
name: retro
description: Produces an engineering analytics retro from local git history: commit cadence, per-author contribution, churn hotspots, PR cycle time, Conventional Commit type distribution, and trend deltas vs a prior window. Use when you want a development retrospective, velocity or churn report, or git history analytics. Triggers on retro, engineering analytics, git history analytics, velocity report, churn report.
user-invocable: true
---

# Retro

> **Adapted concept.** Built from the gstack `/retro` concept (MIT License),
> retrieved 2026-06-18 via `docs/tool-evals/skills-deep-dive-2026-06.md`. The
> upstream `{{PREAMBLE}}` template token was stripped; this skill is authored
> fresh against our toolchain. Adapted to our standards: em-dashes removed;
> the commit-type breakdown is pinned to our Conventional Commits branch-type
> table (`.claude/rules/git-workflow.md`); metrics are framed as signals, not
> targets, per Goodhart's law.

## Overview

`retro` mines the local git log to produce a readable engineering retrospective.
It computes development analytics over a date window: commit cadence and velocity,
per-author contribution, churn hotspots (the files changed most), PR cycle time
where the history makes it derivable, the distribution of Conventional Commit
types, and trend deltas against a prior window of equal length. The output is a
report you can drop into `docs/` or surface inline.

Everything comes from `git` already on disk. No remote calls, no external service.

## When to Use

- Closing a sprint, milestone, or release and you want a data-backed retro
- You suspect a churn hotspot (a file everyone keeps touching) and want to confirm
- You want to see how the commit-type mix shifted (more `fix:` than `feat:`?)
- Comparing this window's cadence against the prior one to spot a slowdown
- Preparing notes for a team retro and want signals, not anecdotes

**When NOT to use:** ranking people. Per-author counts describe where work landed,
not who is "productive." See the Pre-Flight step and the rationalization table.

## Pre-Flight

Before computing anything, confirm two things with the user:

1. **The window.** Default to the last 14 days if unstated. Confirm the start and
   end dates so every command below uses the same `--since`/`--until`. The prior
   window for trend deltas is the equal-length span immediately before it.
2. **Framing.** State plainly that these are **signals, not targets**. The moment a
   metric becomes a goal it stops measuring anything (Goodhart's law). Per-author
   velocity in particular is a conversation starter, not a performance score. If the
   user wants it used as a target, surface the risk before proceeding.

## What the Report Computes

Each metric below pairs with the concrete git command that produces it. Substitute
`$SINCE` and `$UNTIL` with the confirmed window.

### Commit cadence and velocity

Commits per day across the window, and the raw total.

```bash
git log --since="$SINCE" --until="$UNTIL" --date=short --pretty=format:'%ad' \
  | sort | uniq -c
git log --since="$SINCE" --until="$UNTIL" --oneline | wc -l
```

### Per-author contribution

Commit counts by author. Read this as distribution of where work landed, not a
leaderboard.

```bash
git shortlog -sn --since="$SINCE" --until="$UNTIL"
```

### Churn hotspots

The files touched in the most commits over the window. A file near the top of this
list is a candidate for refactoring, missing tests, or unclear ownership.

```bash
git log --since="$SINCE" --until="$UNTIL" --name-only --pretty=format: \
  | grep -v '^$' | sort | uniq -c | sort -rn | head -20
```

Pair with added/removed line totals for magnitude:

```bash
git log --since="$SINCE" --until="$UNTIL" --numstat --pretty=format: \
  | awk 'NF==3 {add+=$1; del+=$2} END {print "added", add, "removed", del}'
```

### PR cycle time (where derivable)

When merge commits carry the branch lifetime, cycle time is the span from a branch's
first commit to its merge. This is approximate and only works for a merge-commit
history (not squash-only).

```bash
git log --since="$SINCE" --until="$UNTIL" --merges \
  --pretty=format:'%h %ci %s'
```

For each merge, diff its merge date against the first commit on the merged branch.
If the history is squash-only, note that cycle time is not derivable from git alone
and say so in the report rather than inventing a number.

### Commit-type distribution

Our repo uses Conventional Commits (see the branch-type table in
`.claude/rules/git-workflow.md`: `feat`, `fix`, `docs`, `refactor`, `perf`, `test`,
`chore`). The type prefix on each subject line gives a real signal of where effort
went.

```bash
git log --since="$SINCE" --until="$UNTIL" --pretty=format:'%s' \
  | grep -oE '^(feat|fix|docs|refactor|perf|test|chore|build|ci|style)' \
  | sort | uniq -c | sort -rn
```

A window that is mostly `fix:` after a release tells a different story than one
that is mostly `feat:`.

### Trend deltas vs the prior window

Re-run the cadence, type-distribution, and churn commands against the equal-length
prior window, then report the delta (this window minus prior). Frame as direction,
not verdict: "commits down 18% from prior window" is a prompt to ask why, not a
failing grade.

```bash
# Prior window of equal length; substitute the computed prior bounds.
git log --since="$PRIOR_SINCE" --until="$PRIOR_UNTIL" --oneline | wc -l
```

## Sample Report Skeleton

```text
# Engineering Retro: $SINCE to $UNTIL

Window: 14 days | Prior window: <prior dates> | Signals, not targets.

## Cadence
- Total commits: 84 (prior: 102, -18%)
- Busiest day: 2026-06-12 (11 commits)
- Median commits/active-day: 6

## Contribution (where work landed)
- a.dev: 41 commits
- b.dev: 30 commits
- c.dev: 13 commits

## Commit-type mix
- feat: 38%  fix: 27%  refactor: 14%  test: 11%  docs: 6%  chore: 4%
- Shift vs prior: fix up 9 pts, feat down 7 pts

## Churn hotspots
1. src/auth/session.py        14 commits   (+402 / -310)
2. src/api/routes.py           9 commits   (+118 / -64)
3. docs/architecture/adr/...   7 commits   (+90 / -12)

## PR cycle time (approximate, merge-commit history)
- Median branch lifetime: 1.8 days
- Longest: feat/oauth-google, 6 days

## Observations
- session.py is a churn hotspot two windows running: candidate for a refactor.
- fix-heavy mix follows the v1.4 release; expected post-release stabilization.
```

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "Velocity is vanity, skip it" | Cadence trend is a real signal of flow and disruption. The failure is treating it as a target, not measuring it. Report it, frame it. |
| "More commits means more productive" | Commit count tracks granularity, not value. One author squashing and one committing per line are not comparable. |
| "Per-author counts rank the team" | They rank where work landed, which is shaped by tasking, on-call, and review load. Using them as a performance metric is Goodhart bait: people will game the number, not the work. |
| "The churn hotspot is just an active file" | Sometimes. But a file at the top two windows running is more often an unclear boundary or a test gap. Investigate before dismissing. |
| "Squash history, so just estimate cycle time" | An invented number is worse than an absent one. State that git alone cannot derive it and point at the PR platform. |
| "The delta is negative, so the team underperformed" | A delta is a question, not a verdict. Holidays, a hard bug, or a single large PR all move it. Ask why before judging. |

## Red Flags

- Presenting per-author commit counts as a performance ranking or productivity score
- Reporting a cycle-time number on a squash-only history without flagging it as approximate
- Computing the trend delta against a prior window of a different length
- Letting any metric become a target the team is then asked to hit (Goodhart)
- Running the metrics before the window is confirmed, so prior-window math is wrong
- Treating a churn hotspot as noise without checking whether it recurs across windows

## Verification

After producing the retro:

- [ ] The window was confirmed with the user before any command ran
- [ ] Every command used the same `$SINCE`/`$UNTIL`; the prior window is equal length
- [ ] The report frames metrics as signals, with the Goodhart caveat on per-author data
- [ ] Cycle time is either derived from merge commits or explicitly marked not derivable
- [ ] Commit-type buckets match our Conventional Commits set
