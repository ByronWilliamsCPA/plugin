---
name: subagent-driven-development-extras
description: Local delta on top of the vendored subagent-driven-development skill. Adds a two-transport rule for reviewer feedback: blocking findings get the fix/re-review loop, accepted-minor findings ride forward as a preamble commit in the next dispatch. Also covers auditing a reviewer's real verification scope, resolving cross-task facts a task-scoped reviewer cannot see, recovering killed or cut-off subagent work from git state, and anchoring the final whole-branch review's merge base on origin/main in a shared clone. Use alongside subagent-driven-development when a quality reviewer returns "approve with non-blocking follow-ups" during a multi-task controller run, when a reviewer's warning item might be a cross-task fact, when an implementer was killed or cut off mid-task, or before generating the final whole-branch review package. Triggers on: subagent controller, reviewer follow-ups, approve with minor, non-blocking review, batch review feedback, preamble commit, verification scope, cross-task fact, killed subagent, cut-off implementer, merge-base, stale main.
---

# subagent-driven-development-extras

Extends the vendored `subagent-driven-development` skill (read-only, in `.submodules`). Contains only the delta: how the controller routes the two severity classes of reviewer feedback, how far a reviewer's "PASS" actually reaches, how to resolve a reviewer's cross-task warning items, how to recover from a killed or cut-off implementer, and how to anchor the final review's merge base in this shared clone.

## Two severity classes deserve two transport mechanisms

Quality reviewers frequently return "approve with minor follow-ups": non-blocking test gaps, docstring additions, constant placement. Dispatching a dedicated fix-and-re-review cycle for each such batch doubles the subagent count for trivial changes. Instead:

- Blocking findings (request-changes verdicts) keep the closed loop the skill mandates: same-implementer fix plus re-review.
- Accepted, non-blocking suggestions ride forward as an explicit "COMMIT 1: review follow-ups" preamble in the NEXT task's implementer prompt.

This keeps commits separated and the follow-ups traceable to their originating review, while reserving the fix/re-review loop for findings that actually block. Blocking findings need the closed loop; accepted-minor findings only need a guaranteed landing slot, and batching them into the next dispatch preserves quality at roughly half the subagent overhead.

## Quality reviewer checks the severity model in operator docs

When a task produces an operator guide that describes security-tool output, add a documentation-accuracy check to the quality reviewer prompt: does the guide name the correct severity model for each scanner? CVSS applies only to CVE-backed SCA (dependency) findings. SAST, IaC, and agent scanning use rule-based or otherwise tool-specific models, not CVSS. Naming the wrong model (for example, describing Snyk Code SAST severity as "CVSS-scored") sends operators looking for numeric bands that do not exist, at exactly the moment they are triaging findings.

This is a quality-review concern, distinct from spec review: the spec reviewer verifies the section exists; the quality reviewer verifies that what it says is accurate.

## Verify a non-main PR base is on origin before creating the PR

In the branch-finish step, `gh pr create --base <branch>` resolves the base SHA from the remote, so a base that exists only locally fails with the misleading "Base sha can't be blank." Apply the `git ls-remote --heads origin <base>` pre-check from finishing-a-development-branch-extras before targeting any non-main base.

## Audit what a reviewer's "PASS" could not have caught

The parent skill's Constructing Reviewer Prompts section treats a clean spec-and-quality verdict as clearance to mark a task complete. Before trusting that verdict, or any test or lint rule reporting PASS, ask what it could not have caught: does the test exercise both branches of the decision, or only the one taken? Does the review look at the trigger condition, or only the handler body it invokes? Does a fix round's own output get checked for the same defect class it was dispatched to remove? A rationale comment that names one hazard is itself evidence the symmetric hazard was never examined. Treat "green" as scope-limited until the mechanism's blind spot is named, not as proof the underlying behavior is correct.

## A reviewer's warning item may be a cross-task fact it cannot see

The parent skill's Handling Reviewer Warning Items section already tells the controller to resolve each "cannot verify from diff" item itself, since the controller holds context the task-scoped reviewer lacks. Extend that resolution step with a specific check: before dismissing or accepting a warning item, ask whether it is actually a cross-task fact the reviewer structurally cannot see, either already handled by a sibling task, or a real gap that is only visible from the controller's cross-task position. Never pre-verify a finding yourself and then send it to the reviewer for confirmation; that ordering destroys the independence the review step exists to provide. A reviewer's finding is scoped to its task's diff, and the controller's job is to supply the cross-task context the reviewer's scope cannot reach.

## Recover killed or cut-off subagent work from git state, not the subagent's last message

The parent skill's Durable Progress section already warns that conversation memory does not survive compaction and directs the controller to the ledger and `git log`. The same distrust applies to an implementer that was killed or cut off mid-task by an external limit: do not trust its last message before deciding whether to re-dispatch, resume, or discard. Check `git status`, `git log`, and the report file directly. Work left behind by a killed or cut-off implementer may already be committed and complete, not junk to discard. Pair this with a dispatch-time requirement: every implementer dispatch should be required to prove its worktree by returning the output of `pwd` and `git rev-parse --show-toplevel`, rather than merely naming the path it claims to be working in.

## Anchor the final whole-branch review's MERGE_BASE on origin/main, not local main

The parent skill's Constructing Reviewer Prompts section instructs the controller to generate the final review package with `scripts/review-package MERGE_BASE HEAD`, where "MERGE_BASE = the commit the branch started from, e.g. `git merge-base main HEAD`." That example is a correction target in this shared, concurrently-modified clone: local `main` is routinely stale relative to the remote, because other sessions push to it without this session's knowledge. A stale local `main` produces a wrong merge base and a corrupted final-review diff, silently, since the command still succeeds.

Where the parent skill's example anchors on local `main`, anchor on `origin/main` instead, and fetch it first:

```bash
git fetch origin main
git merge-base origin/main HEAD
```

Run the fetch immediately before computing MERGE_BASE for the final review package, not at session start, since local refs can drift again between session start and the final review. If a progress ledger exists and records the branch's starting commit, cross-check the computed MERGE_BASE against that recorded value before trusting it.
