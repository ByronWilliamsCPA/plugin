---
name: subagent-driven-development-extras
description: Local delta on top of the vendored subagent-driven-development skill. Adds a two-transport rule for reviewer feedback: blocking findings get the fix/re-review loop, accepted-minor findings ride forward as a preamble commit in the next dispatch. Use alongside subagent-driven-development when a quality reviewer returns "approve with non-blocking follow-ups" during a multi-task controller run. Triggers on: subagent controller, reviewer follow-ups, approve with minor, non-blocking review, batch review feedback, preamble commit.
---

# subagent-driven-development-extras

Extends the vendored `subagent-driven-development` skill (read-only, in `.submodules`). Contains only the delta: how the controller routes the two severity classes of reviewer feedback.

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
