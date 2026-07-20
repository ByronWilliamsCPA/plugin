# Task Observer -- Confidentiality Reference

Reference content for `task-observer` covering the five confidentiality safeguard layers that keep client- and project-identifying information out of open-source skills. Read this file before drafting, regenerating, or shipping any open-source skill.

---

## Confidentiality Safeguards

The open-source/internal boundary is a confidentiality boundary. Client
names, project details, domain names, and proprietary information must never
appear in open-source skills. Because a single leak can erode trust, this
is enforced through multiple layers — any one of which should catch what
the others miss.

### Layer 1: Observation-Level Stripping

When logging an observation tagged as `type: open-source`, the Issue and
Suggested Improvement fields should already use generic language. The
private observation log can reference specifics for context, but the
Principle field — which feeds into skill creation — should be fully
generalised. Think of it as: the log is a private notebook, but the
Principle is a publishable insight.

### Layer 2: Pre-Creation Review

Before drafting or regenerating any open-source skill, scan all source
material (observations, conversation notes, existing skill content) for
identifying information: client names, project URLs, domain names, internal
terminology, site structures described so specifically they're identifiable.
Replace anything found with generic equivalents before writing begins.

### Layer 3: Post-Draft Sweep

After writing or regenerating an open-source skill, re-read it with a
specific focus on information leakage. This is a separate pass from the
general pre-flight checklist. Look for:

- Proper nouns that aren't the skill author's name
- Domain names, URLs, or project identifiers
- Industry-specific details that narrow down the client
- Internal terminology that only makes sense in one organisation's context
- Examples so specific they're traceable to a real project

If anything is found, replace it with generic equivalents or remove it.

### Layer 4: Structural Principle

The taxonomy section states this explicitly, but it bears repeating: the
open-source/internal distinction is not just about usefulness — it's about
confidentiality. When in doubt about whether a detail is too specific,
remove it. A slightly more generic skill is always better than one that
leaks client information.

### Layer 5: Cross-Product Re-Identifiability Sweep

Layers 1–4 focus on single-example scrubbing. They do not catch the case
where two or three sanitised examples in the same skill — each fine on its
own — combine to narrow the identifiable client set. A reader who knows
the author's client portfolio (which is often public on a consultant's
website) can triangulate even when each individual example is properly
placeholdered. The failure mode is invisible to the author because they
mentally compartmentalise each example; it's visible to any reader with
adjacent context.

**When to run it:** After every individual example has been sanitised —
as a final pass before the skill ships or before any major public
release. This is the last check, not a substitute for earlier layers.

**What to look for:**

- **Enumerated counts that match a known client count.** "Four builds
  across three verticals" in a skill whose author has four public clients
  across three verticals is functionally a directory. Blur the count
  ("multiple builds") or the verticals ("across regulated, editorial,
  and commerce contexts").
- **Specific numbers in a thin vertical.** Visibility percentages,
  revenue ranges, or geography given in a vertical where only one or two
  candidates plausibly exist. A single real client can be narrowed from
  "vertical × percentage × geography × timing" even when no name appears.
  Replace specific numbers with illustrative ranges.
- **Thinly-disguised placeholder names.** "Northwind Coffee" in a
  specialty-retailer vertical where the only plausible specialty-retail
  client is a coffee roaster reads as the real brand with a thin
  rename. Use the Northwind / Contoso / Fabrikam placeholder family
  explicitly, and make sure the placeholder's vertical is different from
  any real client's vertical.

**How to sweep:**

1. List every worked example in the skill and the fields each one names
   (vertical, geography, numeric range, timing, count).
2. Ask: do any two examples share enough fields that a reader with access
   to the author's public client list could map the set to real clients?
3. Mitigate by blurring counts, widening verticals, dropping specific
   numbers to illustrative ranges, or consolidating similar examples into
   a single composite.

**Why this is a separate layer:** Re-identification risk is combinatorial.
Each additional sanitised example adds a field that narrows the candidate
space. Layers 1–4 check each example in isolation and pass. The cross-
product only emerges when the examples are read together. The author is
the least reliable reader for this check because they know the ground
truth — which is exactly why the sweep has to be a mechanical pass, not
a feeling.

---
