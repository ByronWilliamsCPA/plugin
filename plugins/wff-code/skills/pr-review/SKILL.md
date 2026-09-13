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

## File layout

Each workflow file is a spine: it keeps every `## Step N` heading and, under
each, a short statement of what that step consumes, produces, and decides. The
long-form procedure for the larger steps lives in `context/`, reached by a
`**Full procedure:**` pointer in the stub.

**Loading rule. This is a cost control, and it is the whole point of the
split.** The orchestrator reads the spine and nothing else by default. Every
`**Full procedure:**` pointer names its reader:

- *pass the path* means the step is executed by a dispatched agent. Put the
  path in the dispatch brief and let the agent open it. The orchestrator must
  not read the file itself: that pays for the same tokens twice, once in the
  orchestrator's context and once in the agent's, and buys nothing, because the
  agent is the one running the procedure.
- *read before executing* means the orchestrator runs this step itself. It
  opens the file when it reaches that step, not at the top of the run.

Both workflows are a fixed linear sequence of `## Step N` headings; every step
is reached on every invocation even though some steps complete as a no-op at
runtime (Step 5's Agents E-H and L activate only when Step 3's classification
calls for them; pr-fix's Step 9 watch loop only starts if Step 8's push is
approved). Reaching a step is not the same as its context file being needed:
eagerly opening all ten context files up front costs *more* than the single
undivided file did before the split (roughly 25k tokens against the old 17k).
Honouring the pointers puts about 10k in the orchestrator and pushes the
remaining 12k into agents that were being dispatched anyway. Opening a context
file for a step you are about to delegate, or one whose runtime conditions
will skip it, is the specific mistake that turns this refactor into a
regression.

Step numbering is the addressing scheme for both workflows and is load-bearing:
roughly 125 internal references point at those headings. Never renumber,
re-letter, or merge a step, and never move a `Step` heading out of its spine.
Move bodies, not anchors.

| Context file | Backs | Read by |
| --- | --- | --- |
| `context/github-api-idioms.md` | Both workflows. GitHub API behaviours that have each caused a real defect. | whoever writes the call, orchestrator or agent |
| `context/pr-metadata.md` | pr-review Steps 2, 2d, 2e, 2f | orchestrator |
| `context/change-classification.md` | pr-review Step 3 | the Haiku agent, by path |
| `context/quality-gates.md` | pr-review Step 4 | orchestrator |
| `context/review-agents.md` | pr-review Step 5, the agent roster | orchestrator, directly. It opens with orchestrator-run procedure (large-PR strategy, the file-context fetch, dispatch discipline) that must execute before any agent exists to dispatch, and the orchestrator is also the one extracting each `### Agent X:` block below to build that agent's dispatch prompt. Only the extracted block reaches the agent; no agent opens this file itself. |
| `context/finding-validation.md` | pr-review Steps 6 and 7b | Step 6 half: the Haiku agents, by path. Step 7b half: orchestrator |
| `context/issue-gathering.md` | pr-fix Step 1 | orchestrator |
| `context/fix-execution.md` | pr-fix Step 4 | orchestrator |
| `context/fix-verification.md` | pr-fix Step 5 | orchestrator |
| `context/watch-refix-loop.md` | pr-fix Step 9 | orchestrator |

Read `context/github-api-idioms.md` before writing any code that touches
reviewer identity, `mergeStateStatus`, renamed files, scanner exit codes, or an
MCP-backed quality gate. Every rule in it is there because the obvious
implementation shipped and silently did the wrong thing.
