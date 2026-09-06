---
name: audience-reaction-analyzer-extras
description: >
  Local delta on top of the vendored audience-reaction-analyzer agent (read-only,
  symlinked into .submodules). Adds a spec-diff-first method for completeness and
  gap review: diff the deliverable against its own governing outline/spec/TOC
  before judging completeness, and verify every "X is missing" claim with a search.
  Use alongside the audience-reaction-analyzer agent or any deliverable-gap review.
  Triggers on: gap review, completeness review, what is missing, CIO gap review,
  diff against outline, spec-diff review, audience reaction analysis.
user-invocable: true
---

# audience-reaction-analyzer-extras

Extends the vendored `audience-reaction-analyzer` agent (read-only, symlinked into
`.submodules`, so the agent file itself cannot be edited). Contains only the delta.
Load this guidance for any deliverable-gap or completeness review.

## Diff the deliverable against its own outline/spec/TOC first (obs 484)

Completeness review against a spec beats completeness review against intuition. A
deliverable's own outline, spec, table of contents, or template is a free,
authoritative checklist. Reading the prose for "feels complete" misses gaps because
each section can read as internally coherent while a required element (e.g. mandated
peer-positioning paragraphs) is absent.

First pass: if the artifact has a governing outline/spec/TOC/template, load it and
diff the artifact against it. Surface every required element the body does not
contain.

## Back every "X is missing" claim with a search (obs 484)

Absence is a positive claim: cheap to verify, embarrassing to get wrong. Before
asserting any gap, verify it with a targeted search of the full artifact tree
(grep the expected terms: expected return, Sharpe, fees, peer, benchmark,
transition cost, etc.). Distinguish:

- "absent from the body where the reader decides" (a real gap),
- "present only in an appendix" (a placement issue), and
- "genuinely absent everywhere" (a true omission).

Report a gap only when a search found nothing, not because you did not notice it.
