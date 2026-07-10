# Frontend Design Reference Catalogs

Static, model-referenceable design catalogs for the `frontend-design` skill.
Load the relevant catalog when you need concrete options (a style, a font
pairing, a chart type, a product-pattern decision) instead of inventing one.

## Provenance

Extracted from [`nextlevelbuilder/ui-ux-pro-max-skill`](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)
(MIT License, Copyright (c) 2024 Next Level Builder), commit
`b7e3af80f6e331f6fb456667b82b12cade7c9d35`, retrieved 2026-06-19.

The upstream `search.py` BM25 + regex runtime was intentionally dropped: these
files are small enough to reference directly, so no search engine or Python
dependency is needed. The catalogs are the source of truth; read the rows you
need. This directory is authoritative for what was actually extracted: the
file list and row counts here are canonical and may differ from the
exploratory survey notes. The decision to extract and own these catalogs
(rather than vendor the upstream skill) is recorded in
`docs/tool-evals/skills-deep-dive-2026-06.md` (item 19) and
`docs/tool-evals/skills-repos-survey-2026-06.md`, which may reference a
different working set of files as the survey evolved.

Upstream `data/` files deliberately excluded: `google-fonts.csv` (the full
745 KB Google Fonts catalog; the curated pairings in `typography.csv` cover the
need), `design.csv` / `draft.csv` (single-column Chinese-language dumps),
`icons.csv`, `react-performance.csv` (overlaps our performance skills), and the
framework-specific `stacks/*.csv` (our skill is framework-agnostic).

## Catalogs

| File | Rows | What it holds | Use when |
| --- | --- | --- | --- |
| `styles.csv` | 84 | UI style families (Swiss/minimal, brutalism, glassmorphism, etc.) with keywords, primary/secondary color palettes, effects, best-for / do-not-use-for, light/dark support, AI prompt keywords, and CSS keywords | Choosing or describing a visual style; sourcing a palette; writing an image/codegen prompt |
| `typography.csv` | 74 | Curated font pairings: heading + body font, mood keywords, best-for, Google Fonts URL, CSS import, Tailwind config | Picking a font pairing with ready-to-paste imports |
| `charts.csv` | 25 | Chart types with use case, library recommendation, and accessibility grades | Choosing a chart and an accessible library for it |
| `ui-reasoning.csv` | 161 | Per product-type UX reasoning: recommended pattern, style/color/typography priority, key effects, decision rules, and anti-patterns | Deciding the layout and pattern for a given product type (SaaS, e-commerce, portfolio, etc.) |
| `app-interface.csv` | 30 | Interface correctness issues with Do / Don't and good/bad code examples, tagged by platform and severity | Reviewing or building interface details (accessible labels, touch targets, focus states) |

Note: there is no separate `colors` catalog; color palettes live in the
`Primary Colors` / `Secondary Colors` columns of `styles.csv`.

## How to use

1. Identify the decision you are making (style, type, chart, product pattern,
   interface detail).
2. Open the matching catalog and read the relevant rows. Do not load all five
   at once; load the one that fits the task (the `context-engineering` selective
   include principle).
3. Treat the rows as options to choose from and justify, not as mandatory
   output. The `frontend-design` aesthetics guidelines and the project's own
   constraints still govern the final design.
