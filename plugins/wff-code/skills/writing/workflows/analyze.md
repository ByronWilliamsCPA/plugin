# Analyze Workflow

Run the audience-reaction-analyzer on a finished document to predict how the target
audience will comprehend, respond to, and act on the content.

## Precondition Check

This workflow is a post-pipeline step. The document should have passed Stage 3 before
analysis.

Ask the user: "Has this document been through the writing pipeline (Stage 1, 2, and 3)?"

- If yes, or if the user confirms the document is in final form: proceed.
- If no, or if uncertain: offer to run `/writing edit` first. Explain that analyzing a
  draft with unresolved grammar, factual, or voice issues will produce less accurate
  audience predictions.
- If the user wants to analyze anyway (e.g., a quick gut-check before deciding whether
  to polish): proceed, but note in the output that the analysis was run on an unreviewed
  draft.

## Step 1: Gather Inputs

The audience-reaction-analyzer requires these parameters to do its job. Ask for any
that are missing:

- **Document**: File path or content.
- **Target audience**: Who will read this? Be specific: "Oregon appellate court judges,"
  "non-technical board members," "a CPA firm client who is a small business owner."
- **Audience knowledge level**: What do they already know about the subject?
- **Desired outcome**: What do you want the reader to do or believe after reading?
  Be specific: "approve the $150K budget," "understand why the tax position is defensible,"
  "sign the engagement letter."
- **Author-to-audience relationship**: Advisor to client, associate to partner,
  advocate to court, etc.
- **Reading context**: How will this be read? Printed memo at a board meeting, email
  on a phone, submitted brief in a case file?

All six are required. The analyzer cannot predict audience response without knowing
who the audience is and what success looks like.

## Step 2: One Audience at a Time

If the user mentions multiple audiences ("both the board and the implementation team"),
run the analyzer separately for each audience. Do not blend reactions.

Inform the user upfront: "I'll run the analysis separately for each audience — the
predictions can differ significantly depending on who's reading."

## Step 3: Invoke audience-reaction-analyzer

Pass the document and all gathered inputs. The agent does not edit text — it predicts
response and identifies gaps.

## Step 4: Report

Present the full analyzer output. After the output, add a brief synthesis:

**If READY**: "The document is ready to send. [1-2 sentence summary of key strengths.]"

**If NEEDS REVISION**: List the HIGH-priority items in order and suggest the most
efficient path to address them. If the issues require new content (missing sections,
unstated consequences), suggest `/writing draft` to generate additions. If the issues
require tone adjustment, suggest `/writing rewrite`.

**If SIGNIFICANT REWORK**: The document has structural problems that a light edit
won't fix. Identify the root cause (weak thesis, wrong register, missing evidence,
misaligned emotional trajectory) and suggest whether a rewrite or a re-draft is
the right path.

## Multiple-Audience Runs

When running for multiple audiences, present each analysis separately with a clear
header, then provide a cross-audience comparison at the end:

- What works for all audiences
- What works for audience A but not B (and vice versa)
- Whether there are irreconcilable conflicts (e.g., content that reassures audience A
  will concern audience B) — flag these as decisions for the author, not problems
  the pipeline can solve
