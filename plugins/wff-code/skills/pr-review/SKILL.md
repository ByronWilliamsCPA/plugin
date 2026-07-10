---
name: pr-review
description: >
  PR review and remediation. /pr-review triggers Copilot, SonarQube, and 8
  parallel agents for tiered review. /pr-fix gathers all open PR issues (CI
  failures, review comments, SonarQube, Codecov, agent findings) and fixes
  them in an isolated worktree. Auto-activates on: review PR, review this PR,
  review pull request, /pr-review, pr review, review the PR, pr-fix, fix PR,
  fix pull request, fix this PR, fix PR issues, /pr-fix, fix the PR
---

# PR Review and Fix Skill

Two complementary workflows for pull request quality:

- `/pr-review` reviews a PR and produces a tiered findings report
- `/pr-fix` gathers all open issues on a PR and resolves them

## Usage

```text
/pr-review https://github.com/owner/repo/pull/123
/pr-fix https://github.com/owner/repo/pull/123
```

`/pr-fix` can also run as a follow-up to `/pr-review` (option 2 or 3 in the
review completion menu), or standalone on any PR.

## Design Principles

- **Nothing is filtered.** All findings are reported at the appropriate
  priority tier. The old 80-confidence hard cut is replaced by
  Critical / Important / Suggested / Informational tiers.
- **SonarQube findings are authoritative.** Both issues and security hotspots
  bypass AI confidence scoring and are always included regardless of perceived
  severity. The two queues are fetched separately (Step 4c and 4f) because
  SonarCloud never returns them from the same API call.
- **Copilot fires first.** The `copilot_code_review` rule in the org
  ruleset auto-requests Copilot when the PR opens, so its async review
  is already running by the time `/pr-review` starts.
- **No local checkout for review.** All review context is fetched via GitHub
  MCP tools. The user's working tree is never touched during review.
- **Isolated worktree for fixes.** `/pr-fix` creates a worktree at
  `.worktrees/fix-pr{N}` so fixes never contaminate the main working tree.
- **Premise before polish.** A premise gate (Agent M) asks whether the change should
  exist and is an improvement, not just whether it is correct. It checks for
  regression-reintroduction, contradicted decisions, unjustified churn, and cross-PR
  collisions, surfaces an OK/QUESTION/HOLD verdict at the report top, and a HOLD
  interposes a confirmation before /pr-fix.

## Routing

| Activation Context | Workflow File |
| --- | --- |
| Review-related (`review PR`, `/pr-review`, etc.) | `workflows/pr-review.md` |
| Fix-related (`fix PR`, `/pr-fix`, etc.) | `workflows/pr-fix.md` |
