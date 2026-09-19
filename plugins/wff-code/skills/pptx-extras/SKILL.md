---
name: pptx-extras
description: >
  Local delta on top of the vendored pptx system skill. Adds a "plainness is the
  requirement" exception so a mandated institutional house style overrides the
  skill's decorative design defaults. Use alongside pptx whenever the deck must
  match a regulated, legal, governmental, or corporate house style. Triggers on:
  house style deck, institutional template, plain by mandate, regulated
  presentation, no decorative graphics, executive board deck, OST/OIC staff style.
user-invocable: true
---

# pptx-extras

Extends the vendored `pptx` system skill (read-only, symlinked into
`.submodules`). Contains only the delta. Load alongside `pptx`.

## When plainness is the requirement (obs 465)

The pptx skill's Design Ideas push bold palettes, a visual motif, and "every slide
needs a visual element / don't create boring slides." Those defaults are correct in
the general case, but they must yield to an explicit house style.

When the deliverable must match a regulated, legal, governmental, or corporate
house style (e.g. a board/executive staff deck for a public institution), the house
style overrides the bold-design defaults. Reproduce the institution's conventions
rather than imposing a visual motif:

- Restrained palette (e.g. navy/gray/white, grayscale plus minimal accent).
- Table-first and text-first layouts; do not force a "visual element" onto every
  slide.
- No decorative imagery or accent graphics unless the house style uses them.
- Source/footnote lines where the institution expects them.

Keep the skill's existing "avoid accent lines under titles" rule, which already
aligns with restrained house styles.

### Visual QA fallback ladder when LibreOffice is unavailable (Obs 594)

Slide-render visual QA normally depends on LibreOffice to rasterize slides for
review. When LibreOffice is not installed or not invokable in the environment,
fall back in order rather than skipping visual QA silently: (1) an available
alternate renderer capable of PPTX-to-image conversion, (2) inspecting the
raw XML/shape tree for the specific properties being checked (font size,
color values, layout bounds) as a text-only proxy for the visual property, (3)
if neither is available, report visual QA as unverified rather than as
passed.

A presentation that must belong to a specific institutional context succeeds by
matching that context's restraint, not by maximizing visual interest. When the
brief states a house style, the house style wins over the generic
"make it impressive" default.
