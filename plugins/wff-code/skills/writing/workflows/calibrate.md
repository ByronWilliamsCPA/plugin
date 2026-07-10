# Calibrate Workflow

Run the style-analyzer to build a personalized style profile from your writing samples.
This replaces the repository author's default targets with measurements calibrated to
your actual voice.

## When to Run

- Once, when first adopting the reference library pipeline
- When your writing style has meaningfully evolved
- When the pipeline consistently flags your natural writing as "AI-sounding" (a signal
  the profile targets don't match your voice)

Running this before your first pipeline use produces better results across all modes.

## Step 1: Context

Explain to the user:

"The style-analyzer measures your sentence rhythm, lexical diversity, hedging patterns,
and voice characteristics from real samples you wrote. It then updates `style-profile.md`
with targets calibrated to your voice, rather than the library defaults. All future pipeline
runs — grammar, validation, style — will use these personalized targets.

This takes 10–15 minutes and requires 2,000+ words of your own writing."

## Step 2: Gather Writing Samples

Ask the user for 3–5 writing samples meeting these criteria:

- Written by you, not AI-assisted (or at least not heavily revised by AI)
- Total: 2,000+ words across all samples
- Variety: different document types if possible (a memo + an analysis + a letter, for
  example) to capture natural register variation
- Recent: written in the last 2–3 years, so they reflect your current voice

Good sources: sent client memos, filed legal briefs, completed analyses, published
articles, significant emails you wrote from scratch.

If the user can't meet the 2,000-word minimum, explain that the analysis will be less
precise but still useful — proceed with what's available.

## Step 3: Invoke style-analyzer

Pass all samples to the `style-analyzer` agent. The agent will:

1. Compute stylometry metrics (sentence length mean/σ, TTR, hedge density, short/long
   sentence distribution, burstiness)
2. Characterize voice attributes (precision, tone confidence, structure preference,
   thinking style)
3. Identify signature patterns and AI-blacklist overlaps (natural word choices that
   happen to be on the detection list)
4. Generate three proposed updates:
   - Updated `style-profile.md` with measured targets
   - Adjusted `ai-detection.md` entries for legitimate overlaps
   - Agent adjustment notes for the pipeline

## Step 4: Review Before Applying

Do not apply the updates automatically. Present the recommendations and ask the user
to confirm.

Show the key changes:

```text
Proposed style-profile.md updates:
  Sentence length:  Avg XX words (was 17-22)  |  σ = X.X (was ≥ 8)
  Short sentences:  XX% < 8 words (was ≥ 15%)
  Long sentences:   XX% > 30 words (was ≥ 15%)
  TTR:              X.XX (was ≥ 0.40)
  Hedge density:    XX% (was 5-10%)

Proposed ai-detection.md adjustments:
  [List any terms being added to the "acceptable overlap" list]

Voice characteristics identified:
  [Summary of precision, tone, confidence, structure, thinking style]
```

Ask: "Does this match how you write? Any targets that look wrong?"

If the user wants to adjust any targets manually, make those changes before applying.

## Step 5: Apply and Confirm

Once the user approves, the style-analyzer writes the updated files. Confirm:

"Style profile updated. Future pipeline runs will use your personalized targets. To
re-run calibration at any time, use `/writing calibrate`."

Suggest running `/writing edit` on a recent document as a quick sanity check to verify
the calibrated profile produces expected results.
