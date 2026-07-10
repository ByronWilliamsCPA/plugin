# Draft Workflow

Generate a voice-calibrated first draft from an outline, bullets, or prompt, then run
the full editing pipeline.

## Step 1: Gather Inputs

Before invoking the document-drafter agent, confirm:

- **Input**: Outline, bullet points, prior document to expand, topic-plus-audience
  description, or email with reply direction. If not provided, ask.
- **Tone palette**: Which of the 8 tone palettes applies? Options: Formal/Scholarly,
  Professional/Analytical, Warm/Conversational, Plain/Direct, Technical/Precise,
  Persuasive/Advocacy, Instructional/Procedural, Legal/Statutory. If unsure, ask or let
  the agent infer from document type and audience.
- **Target audience**: Who will read this? What do they already know?
- **Document type**: Memo, letter, analysis, proposal, report, email, brief, etc.
- **Length guidance**: Approximate target length or scope (e.g., "one page," "executive
  summary," "full analysis").
- **Legal context**: Oregon legal writing? If yes, specify which style applies (appellate,
  legislative, statutory).

If any required inputs are missing and cannot be inferred, ask before drafting.

## Step 2: Invoke document-drafter

Pass all gathered inputs to the `document-drafter` agent.

The agent will produce a first draft with a `draft_metadata` block at the top:

```yaml
draft_metadata:
  ai_generated: true
  tone_palette: [palette name]
  audience: [description]
  document_type: [type]
  input_type: [outline | bullets | prior_doc | prompt]
```

This metadata signals Stage 3 to apply heightened scrutiny (0 AI patterns tolerated,
not the standard 3).

## Step 3: Feed into the Editing Pipeline

Take the document-drafter output directly into the edit workflow. The `ai_generated: true`
flag is critical — pass it to Stage 3 explicitly.

Follow `edit.md` Steps 2–6 exactly, with one addition at Stage 3:

> **Heightened scrutiny is active.** The draft_metadata block includes `ai_generated: true`,
> which means Stage 3 will apply zero-tolerance for AI patterns (not the standard 3-instance
> threshold). Expect more Stage 3 NEEDS_WORK results than on a human-authored draft, and
> more remediation cycles.

## Step 4: Report

After the pipeline completes, report:

```text
Draft Pipeline Result: [PASS | NEEDS_WORK | ESCALATE]
────────────────────────────────────────────────────
SEND: READY / NOT READY
Drafter:               Complete — [tone palette used]
Stage 1 (Grammar):     [status]
Stage 2 (Validation):  [status]
Stage 3 (Style):       [status] (heightened scrutiny applied)
Remediation cycles:    [N of 3]
────────────────────────────────────────────────────
Summary: [2-3 sentences on the draft quality and pipeline result]
```

**SEND: READY** when all stages PASS and no CONDITIONAL items require resolution.
**SEND: NOT READY** when any stage FAILed, max cycles reached, or Stage 2 CONDITIONAL
items include assumptions or inferred content that the user must verify (e.g., legal
clauses, venue/party details, scope exclusions). List each such item under a
**"Before You Send"** heading so the user knows exactly what to confirm before sending.
