---
name: receiving-code-review-extras
description: Local delta on top of the vendored receiving-code-review skill. Adds code-as-arbiter adjudication when a review and a status board (or two reviews) conflict, and constraint-first remedy re-derivation when a finding's implied fix would violate a standing user constraint. Use alongside receiving-code-review when a review contradicts the status record, when two reviews disagree on a checkable claim, or when turning red-team/audit findings into a plan under a hard user rule. Triggers on: conflicting reviews, review vs status board, red-team findings to plan, finding implies forbidden fix, standing constraint, no re-run allowed.
---

# receiving-code-review-extras

Extends the vendored `receiving-code-review` skill (read-only, in `.submodules`). Contains only the delta: how to adjudicate conflicting findings, and how to convert findings into action without letting them smuggle in forbidden work.

## On a checkable claim, the code is the arbiter

Reviews and status boards are both secondary sources and both drift from the code. When a review and a status record disagree (or two reviews disagree) on a factual, checkable claim, read the cited code/artifact and adjudicate from ground truth, not from whichever source is more recent or more authoritative-sounding. A methodology review said one gate was still broken (already fixed) and an engine value was path-invariant (genuinely broken); only reading the live code separated the stale finding from the real one. "Greener than the code" and "scarier than the code" are symmetric failure modes. Capture the split verdict explicitly: list which findings are real and which are stale, so downstream work targets only the real ones.

## A finding names a problem; it does not get to choose the remedy

When converting external findings (a code review, a red-team report, an audit) into a plan under a hard user constraint, each finding carries an implied remedy that was written without knowledge of the user's boundaries and will silently breach them if copied through. "Pass-through is unwired" implies "wire it and re-run," but a re-run may be forbidden; "covariance is a single point of failure" implies "add a stress exhibit," but new modeling may be declined. For each finding, restate its remedy in the constraint's terms (remove or soften the claim and disclose the omission; strengthen an existing disclosure rather than build new modeling), and flag explicitly where the finding's own suggested fix would violate the constraint so the executing session does not default to the naive fix. Make the standing constraint the first thing in the plan so it governs every item.
