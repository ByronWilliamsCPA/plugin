# Rewrite Workflow

Transform a document's register for a different audience while preserving all factual
content, then run the full editing pipeline.

## Step 1: Gather Inputs

Before invoking the tone-rewriter agent, confirm:

- **Source document**: File path or pasted content. If a path, read the file first.
- **Source tone palette**: What is the current register? (If not obvious, the agent can
  infer it — say so.)
- **Target tone palette**: What register should the output be in? Options: Formal/Scholarly,
  Professional/Analytical, Warm/Conversational, Plain/Direct, Technical/Precise,
  Persuasive/Advocacy, Instructional/Procedural, Legal/Statutory.
- **Target audience**: Who is the new audience? What do they know? What is their relationship
  to the author?
- **Scope adjustment permissions**: What can be shortened or removed?
  - Must preserve: all factual claims, recommendations, action items, logical relationships,
    qualifications, attributions, legal citations
  - May transform: vocabulary, sentence structure, formality level, tone, examples
  - May remove (with permission only): highly technical detail, footnotes, appendices —
    ask before removing unless the user has explicitly said it's fine

If any required inputs are missing, ask before proceeding.

## Step 2: Invoke tone-rewriter

Pass all gathered inputs to the `tone-rewriter` agent.

**Two hard constraints to include in the invocation:**

1. **No additions**: The rewriter reshapes existing content — it does not add claims,
   examples, forward-looking statements, or advice not present in the source document.
   If a fact is not in the source, it cannot appear in the output.
2. **No reasoning in the document body**: All internal verification steps, self-corrections,
   and source checks must stay in the agent's thinking process. Phrases like "Wait —",
   "Re-checking...", or "Actually..." must never appear in the document output. Stage 1
   will flag and remove them, but the rewriter should not produce them.

The agent will produce a transformed document with a `rewrite_metadata` block:

```yaml
rewrite_metadata:
  ai_generated: true
  source_palette: [original palette]
  target_palette: [new palette]
  target_audience: [description]
  scope_adjustments: [what was shortened or removed, if anything]
```

This metadata signals Stage 3 to apply heightened scrutiny and signals Stage 2 to
re-verify semantic preservation.

## Step 3: Stage 2 Semantic Preservation Check

This is the critical extra responsibility in the rewrite flow. When passing the
rewrite-metadata output to `document-validator` (Stage 2), explicitly instruct the
agent to:

1. Verify that all factual claims from the source document are present in the rewrite
2. Confirm that no recommendations or action items were dropped or altered in meaning
3. Confirm that all qualifications and caveats survived the transformation
4. Flag any content that appears to have been silently removed or rephrased to change
   its meaning

Stage 2 FAIL in this context means the rewriter dropped or distorted factual content —
not just that there are unverified claims. Surface this to the user before proceeding.

## Step 4: Feed into the Editing Pipeline

Follow `edit.md` Steps 2–6 with these specifics:

- At Stage 1: pass document type and new audience context
- At Stage 2: include the semantic preservation check instruction above
- At Stage 3: the `ai_generated: true` flag is present — heightened scrutiny applies
  (0 AI patterns tolerated, not 3)

## Step 5: Report

After the pipeline completes:

```text
Rewrite Pipeline Result: [PASS | NEEDS_WORK | ESCALATE]
──────────────────────────────────────────────────────
SEND: READY / NOT READY
Rewriter:              Complete — [source palette] → [target palette]
Semantic preservation: [VERIFIED | ISSUES FOUND]
Stage 1 (Grammar):     [status]
Stage 2 (Validation):  [status]
Stage 3 (Style):       [status] (heightened scrutiny applied)
Remediation cycles:    [N of 3]
──────────────────────────────────────────────────────
Summary: [2-3 sentences on transformation quality and pipeline result]
```

**SEND: READY** when all stages PASS and no CONDITIONAL items require author resolution.
**SEND: NOT READY** when any stage FAIL, max cycles reached, or Stage 2 CONDITIONAL items
include factual conflicts, arithmetic contradictions, or unverified claims that appear
in the document body.

If Stage 2 was CONDITIONAL, list each item under a **"Before You Send"** heading with the
specific resolution required (e.g., "Confirm whether taxable income exceeds the $182,050
threshold — the document currently states both figures and they contradict"). The user
must resolve these before the document is sent; the pipeline cannot resolve source-level
factual errors on their behalf.
