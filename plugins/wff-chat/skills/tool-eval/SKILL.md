---
name: tool-eval
description: Evaluate an external tool or repo against our ~/.claude config setup and produce a decision: SUBMODULE, PORT PATTERNS, RUN STANDALONE ALONGSIDE, or IGNORE.
user-invocable: true
---

# Tool Eval

## Overview

Structured workflow for deciding what, if anything, to take from an external
tool or repo. Produces a decision document covering characterization, LOC
mapping, coupling analysis, licence gates, relationship classification, gap
mapping, and delivery-model fit.

**Announce at start:** "I'm using the tool-eval skill."

**When to use:** Any time you encounter a tool, repo, or project and want a
principled answer to "should we cherry-pick anything from this?"

**When to skip:**

- The target is already homogeneous loadable content (skills, agents, markdown)
  and the only open question is whether to `git submodule add` it; run
  `git submodule add` directly.
- The target is a trivial single-file utility with no licence ambiguity and an
  obvious direct port.

**Save output to:** `docs/tool-evals/<tool-slug>.md`

---

## Workflow

Work through the phases below in order. Do not skip a phase; each gate feeds
the next. Concrete commands for each phase live in `workflows/evaluation.md`.

### Phase 1: Characterize

This phase has two distinct sub-phases that operate on different objects: a
pre-clone quick read and a post-clone provenance record. They are intentionally
separate. `workflows/evaluation.md` shows the concrete commands.

**Phase 1a (pre-clone quick read):** Before any clone exists, read the target's
`README`, `DESIGN`, `SPEC`, or architecture docs (e.g. via a `curl` of the raw
`/main/` doc URLs). Produce one paragraph: what it is, stated purpose, primary
stack, and stated scale target.

**Phase 1b (post-clone provenance record):** After cloning, record the commit
actually inspected (`git rev-parse HEAD`) and note the source URL alongside it.

> **Why the split matters (Obs 329):** the Phase 1a doc preview hardcodes
> `/main/` because no clone yet exists, while the Phase 1b provenance record
> captures whatever commit was cloned, which may differ from `main`. These are
> NOT meant to reference the same object. Keep the label so a reviewer or future
> editor does not read the two adjacent blocks as one unit and raise a false
> "the curl `/main/` and the recorded SHA are inconsistent" reproducibility
> finding. When a two-phase workflow operates before and after a resource
> exists, the boundary needs an explicit label.

### Phase 2: Map the source tree

Identify the VALUE CORE (files that deliver the reusable capability) and the
PERIPHERAL MASS (UI, marketing, blog, sample assets, build tooling). Report a
LOC split using `wc -l` or equivalent. The reader must see how much of the
repo is actually a candidate for reuse.

### Phase 3: Coupling-boundary gate

Read the imports of each core candidate file. Classify:

- **PORTABLE:** pure stdlib or framework-free; cheap to lift.
- **FRAMEWORK-LOCKED:** imports Electron, React, a specific ORM, etc.;
  lifting requires carrying the framework.

Only PORTABLE units are cheap to take.

### Phase 4: Licence gate

Check `LICENSE`, `COPYING`, and any carve-outs in `README` (non-commercial
asset bundles, font licences, sub-dependency exceptions). Flag any carve-out
that would contaminate a wholesale vendor relationship. A permissive body
licence with a non-commercial asset carve-out is a common pattern that is fine
for inspiration but blocked for direct inclusion.

### Phase 5: Relationship classification

Classify the target's relationship to our setup:

| Class | Description | Submodule fit |
| --- | --- | --- |
| HOMOGENEOUS LOADABLE CONTENT | Skills, agents, markdown that Claude Code loads the same way it loads this repo | Yes, submodule is appropriate |
| INVERTED / HOST | An app that hosts or wraps Claude Code rather than content Claude Code reads | No; run standalone alongside instead |
| ORTHOGONAL | A different language or runtime; not directly loadable | Port concepts only |

### Phase 6: Gap mapping

For each PORTABLE unit, identify the specific gap it would fill in our setup:
`.claude/agents/`, `.claude/skills/`, `.claude/rules/`, `.claude/standards/`.
A unit that maps to no gap is not worth taking regardless of its quality.

### Phase 7: Delivery-model weighting

Our setup's advantage: it is ambient and inherited, in-editor (VS Code), on by
default in every project, with no app to launch. Score each candidate:

- **FITS:** compounds across inherited projects, works within a single session,
  no persistent out-of-editor process required.
- **FIGHTS:** assumes a persistent daemon, a separate UI, or a launch step the
  user tends manually.

An element that fights the model is lower value even when technically strong.
State this judgement explicitly for each candidate.

### Phase 8: Convergent-validation note

Call out patterns where the target independently arrived at something we
already do. These are validation signals, not action items.

---

## Output Format

```markdown
# Tool Eval: <Tool Name>

**Date:** YYYY-MM-DD
**Source:** <URL, commit or tag>
**Verdict:** SUBMODULE | PORT PATTERNS | RUN STANDALONE ALONGSIDE | IGNORE

## Characterization

<One paragraph: what it is, purpose, stack, scale target.>

## Value core vs. peripheral LOC

| Segment | LOC | Notes |
| --- | --- | --- |
| Value core | N | <files/dirs included> |
| Peripheral mass | N | <what was excluded> |
| **Total** | N | |

## Candidate element table

| Element | Portable? | Maps to our gap | Fits delivery model? | Value-to-effort |
| --- | --- | --- | --- | --- |
| <name> | PORTABLE / FRAMEWORK-LOCKED | agents/ / skills/ / rules/ / standards/ / None | FITS / FIGHTS | High / Medium / Low |

## Licence

<Licence name. Flag any carve-outs explicitly.>

## Relationship classification

<HOMOGENEOUS LOADABLE CONTENT / INVERTED HOST / ORTHOGONAL>, with one sentence of rationale.

## Convergent-validation notes

<Patterns where the target independently arrived at something we already do.
Write "None identified" if absent.>

## Recommended actions

<Ordered list of concrete next steps for each element worth taking.
Write "No action." if verdict is IGNORE.>
```

## Verdict definitions

| Verdict | Meaning | Next step |
| --- | --- | --- |
| SUBMODULE | Target is homogeneous loadable content; wholesale inclusion is appropriate | `git submodule add <url>` and install via plugin mechanism |
| PORT PATTERNS | Specific PORTABLE elements fill real gaps and fit the delivery model | Lift those elements into our `.claude/` tree; adapt as needed |
| RUN STANDALONE ALONGSIDE | Target is INVERTED / HOST; submodule is a category error but the tool has standalone value | Document launch procedure; do not submodule |
| IGNORE | No portable elements, no gap match, licence block, or delivery-model mismatch throughout | No action |

Multiple verdicts are allowed when different parts of the target warrant different
treatment (for example, PORT PATTERNS for the core and IGNORE for the UI layer).

## Sources

- `.claude/rules/supervisor.md` (agent dispatch, output envelopes)
- `.claude/rules/git-workflow.md` (submodule and worktree context)
- Claude Code skills: <https://code.claude.com/docs/en/skills>
