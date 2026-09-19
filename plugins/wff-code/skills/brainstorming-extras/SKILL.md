---
name: brainstorming-extras
description: >
  Local delta on top of the vendored brainstorming skill. Adds scope-drift
  handling when a user appends free-text requirements to a structured answer, and
  a batched-decision pattern for owner-gated choices that block the critical path.
  Use alongside brainstorming during the clarifying-questions phase and whenever
  several decisions are the user's to make and gate downstream work. Triggers on:
  brainstorming clarifying questions, scope drift, free-text aside, re-confirm
  scope, batched decisions, owner-gated decision, recommended defaults, unblock
  critical path.
user-invocable: true
---

# brainstorming-extras

Extends the vendored `brainstorming` skill (read-only, symlinked into
`.submodules`). Contains only the delta. Load alongside `brainstorming`.

## A selected option plus a free-text aside is two signals (obs 333)

During the clarifying-questions phase, users often select a structured option AND
append substantial new requirements in free text ("go with more teams", "the
library should be evaluated as well", "prepare handoff docs for parallel teams").
The aside frequently carries the higher-value constraint and can materially
reshape the deliverable established by an earlier answer. The skill's
"one question at a time" guidance handles the happy path but does not cover the
case where the answer to question N silently redefines the scope set at N-1.

When a user answers a structured question with free-text additions:

1. Treat the additions as new requirements, not commentary.
2. Reflect them back in one line.
3. Re-confirm the working scope before continuing.

Cheap insurance against optimizing a deliverable the user has already moved past.

## Check the docs governance contract before drafting, not after a failed commit (obs 781, 813, 815, 939)

The vendored skill's "write design doc" step is read-only about the target
repo's own documentation contract. Before writing the design doc, grep for
the repo's frontmatter validator (`validate-front-matter` or equivalent) and
its controlled tag/schema vocabulary, and check `docs/_data/` or the
validator script for required fields. Immediately before the commit step,
run `git status`/`git branch --show-current` to confirm a clean, expected
branch state; do not assume the branch the session started on is still
current.

## Batch owner-gated decisions with recommended defaults (obs 413)

Decision latency compounds when blocking choices are surfaced one at a time. When
several decisions are genuinely the user's to make and each gates downstream work
(the spine and any parallel lanes), do not ask serially and do not proceed on
silent assumptions. Instead:

- Collect the decisions and present them as a single structured batch question.
- For each item, offer a recommended option (listed first, marked recommended)
  with a one-line tradeoff/rationale.
- Let the decision-maker ratify several at once.

This converts a series of round-trips into one, preserves the decision-maker's
authority, and lets work proceed on explicit choices. Reserve it for decisions
that are truly the user's and that change downstream actions.

## Security-posture approvals need an explicit second look (obs 1731)

When a design change touches a security posture (auth, access scope,
secrets handling) and the approval turn coincides with any system-level or
tool-result signal that could contradict it, do not treat silence-plus-
approval as settled. Surface the apparent contradiction and get an explicit
confirmation naming the security consequence.

## Check every "defer to later phase" decision against currently-live invariants (obs 1541)

If an existing mandate or invariant already requires the behavior being
deferred, deferring it is a spec bug, not a legitimate phasing choice.
Either implement it now, or get explicit user sign-off that the live
invariant is being knowingly violated in the interim.

## Premise challenges belong in the artifact (obs 1550)

If you find reason to question the deliverable's own premise, not just a
detail inside it, record that challenge as a visible note in the design doc
or spec itself, not only in your reply to the user. Future readers of the
artifact never see the conversation.
