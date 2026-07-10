# Edit Workflow

Run an existing draft through the full three-stage editing pipeline.

## Step 1: Gather Inputs

Before invoking any agent, confirm:

- **Document**: File path or pasted content. If a path, read the file first.
- **Document type**: Client memo, legal brief, analysis, report, proposal, email, etc.
- **Target audience**: Who will read this? Technical level?
- **Legal context**: Does this involve Oregon legal writing (briefs, statutory language, bills)?
  If yes, the grammar-composition-editor and document-validator agents will apply Oregon legal
  style rules rather than general prose rules.

If any of these are missing and cannot be inferred from context, ask before proceeding.

## Step 2: Stage 1 — Grammar and Composition

Invoke the `grammar-composition-editor` agent on the document.

Pass:
- The document content
- Document type
- Target audience
- Legal context flag (yes/no)

**Hard constraint — no reasoning narration**: The grammar-composition-editor must output
only the structured Issue Log, the corrected document, and the `pipeline_status` block.
No internal self-correction text, no conversational narration. Phrases like "Wait —",
"Re-reading...", "Let me check...", or "Flagged as issue #N" in prose must not appear
in the deliverable output — only in the agent's internal thinking.

**Check the `stage_1_grammar` status block in the output:**

| Status | Action |
| --- | --- |
| PASS | Proceed to Stage 2 immediately |
| NEEDS_WORK | Proceed to Stage 2; note that Stage 1 must re-run on any sections Stage 3 rewrites |
| FAIL | Stop. Surface all flagged issues to the user. Do not proceed to Stage 2. |

If FAIL: present the issue log, explain what needs to be resolved before the pipeline
can continue, and offer to re-run Stage 1 after the user has made corrections.

## Step 3: Stage 2 — Document Validation

Invoke the `document-validator` agent on the Stage 1 output.

Pass:
- The Stage 1 corrected document
- Document type and audience context

**Check the `stage_2_validation` status block:**

| Status | Action |
| --- | --- |
| PASS | Proceed to Stage 3 immediately |
| CONDITIONAL | Proceed to Stage 3; note the conditional issues to the user after Stage 3 completes |
| FAIL | Stop. Surface the validation issues. Do not proceed to Stage 3. |

If FAIL: present the issue log (SUSPECT claims, fabricated entities, unsupported causation,
unqualified universal quantifiers). Explain that these must be resolved before continuing.

## Step 4: Stage 3 — Voice and Style

Invoke the `writing-style-editor` agent on the Stage 2 output.

Pass:
- The Stage 2 validated document
- Note whether this document came from `document-drafter` or `tone-rewriter`
  (if yes, include the `ai_generated: true` flag so Stage 3 applies heightened scrutiny)
- **Instruct Stage 3 to scan the full document** for policy violations (em-dashes,
  blacklisted AI phrases) — not only sections it rewrites. Violations in untouched
  headings or paragraphs must be flagged and corrected at the same time as style edits.
- **PCP constraint reminder**: No em-dashes anywhere in the document body — including in
  any section Stage 3 drafts or rewrites from scratch. This applies to all output, not
  only to edits of the input.

**Auto-detect heightened scrutiny**: If Stage 1 flagged 5 or more distinct blacklisted
AI pattern terms (see `.claude/rules/writing.md` — "significantly", "leverage",
"synergies", "cutting-edge", "game-changing", etc.) in the document, pass a heightened
scrutiny flag to Stage 3 (0-instance tolerance) even if `ai_generated` metadata is absent.
External documents submitted for editing can carry AI patterns without a generator flag.

**Stylometry note for short documents**: For documents under 400 words, inform Stage 3
that the long-sentence threshold (≥15% sentences >30 words) does not apply. Stage 3
should assess sentence rhythm using ExpertJudgment for short documents rather than
enforcing a percentage threshold that would require manufacturing artificially long
sentences to meet a quota.

**Check the `stage_3_style` status block:**

| Status | Action |
| --- | --- |
| PASS | Done. Proceed to final status report. |
| NEEDS_WORK | Enter remediation loop (see Step 5). |
| FAIL | Enter remediation loop (see Step 5). |

## Step 5: Remediation Loop

Track total cycles. Maximum 3. After 3 cycles without PASS, stop and escalate.

**Each remediation cycle:**

1. Stage 3 identifies sections that need rewriting for voice/AI patterns
2. Re-run Stage 1 (`grammar-composition-editor`) on the rewritten sections only
3. Re-run Stage 2 (`document-validator`) on those same sections to verify semantic
   preservation — the rewrites must not change facts or remove assumptions
4. Re-run Stage 3 (`writing-style-editor`) on the full document
5. Check Stage 3 status again; repeat or exit

**After 3 cycles without PASS:**

Stop. Tell the user: "After 3 remediation cycles, [section names] still require attention.
This likely needs human review. Here's what remains unresolved: [issue summary]."

## Step 6: Final Status Report

After the pipeline completes (PASS or max cycles reached), deliver a consolidated report:

```text
Pipeline Result: [PASS | NEEDS_WORK | ESCALATE]
────────────────────────────────────────────────
SEND: READY / NOT READY
Stage 1 (Grammar):     [PASS | NEEDS_WORK | FAIL]
Stage 2 (Validation):  [PASS | CONDITIONAL | FAIL]
Stage 3 (Style):       [PASS | NEEDS_WORK | FAIL]
Remediation cycles:    [N of 3]
────────────────────────────────────────────────
Summary: [2-3 sentences on overall quality and what changed]
```

**SEND: READY** when all stages PASS and Stage 2 has no CONDITIONAL items requiring
resolution. **SEND: NOT READY** when any stage FAILed, max cycles reached, or Stage 2
CONDITIONAL items include factual conflicts or unverified claims in the document body.

If Stage 2 was CONDITIONAL, list each item under a **"Before You Send"** heading with
the specific action required (e.g., "Verify the arbitration venue — the letter
references binding arbitration but no venue was specified"). The user must resolve
these before sending; the pipeline cannot resolve source-level gaps on their behalf.

Offer to run `/writing analyze` if the document will be sent to a specific audience
and the user wants to know whether it will land.
