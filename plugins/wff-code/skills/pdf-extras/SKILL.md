---
name: pdf-extras
description: Local delta on top of the vendored pdf system skill. Adds an environment sanity gate to run before any PDF or data extraction loop. Use alongside the pdf skill whenever extracting text/tables from PDFs in a Python project, especially when CLAUDE.md names a project root or package manager. Triggers on: pdf extraction, extract from pdf, pdfplumber, pymupdf, poetry run, uv run extraction.
user-invocable: true
---

# pdf-extras

Extends the vendored `pdf` system skill (read-only, in `.submodules/anthropics-skills`). Contains only the delta: a pre-extraction environment sanity gate. Load this alongside `pdf` for any extraction task in a Python project.

## Environment sanity gate (run before the extraction loop)

Project memory describes intent at authoring time; the filesystem describes truth now. A CLAUDE.md that names a nested staging subdir or a specific package manager can be stale once the repo is initialized in place. Never trust a project-doc-stated path or package manager for the extraction toolchain. Before the main loop:

1. **Confirm the documented path exists.** `ls -d <path-from-CLAUDE.md>`. If it is absent, `ls` the stated repo root and discover the real project markers (`pyproject.toml`, `uv.lock`, `poetry.lock`) there.
2. **Resolve the real interpreter / package manager from the lockfile present**, not the one the docs prescribe. A `uv.lock` means `uv run`; a `poetry.lock` means `poetry run`. These disagree often.
3. **Prove the extraction library imports with a printed version string** from the confirmed root: `uv run python -c "import pdfplumber; print(pdfplumber.__version__)"`. Require a concrete version (e.g. `0.11.9`), not a bare "OK".
4. Only then run the extraction loop.

## Why a printed artifact, not "OK"

Agent-thread cwd resets between bash calls, so a compound `cd <path> && poetry run ...` can have its `cd` fail silently and a stray global interpreter resolve the import inconsistently, printing a misleading "OK". When a cwd-and-interpreter-dependent invocation "succeeds" without producing a concrete, verifiable artifact (a version string, a row count), suspect a silent no-op and prove the toolchain with a positive signal first.

## Multi-numbering documents: build a page-offset map before citing (obs 352)

Documents that bundle sub-documents (board books, regulatory filings, combined
decks) carry several numbering systems at once: the absolute PDF page, per-section
slide footers, and per-tab "Page N of M" schemes. The same physical page can be
referenced three ways, and a brief often cites an internal scheme, not the PDF
page. Before extracting:

1. Scan for divider/footer pages and derive the fixed offset between each internal
   numbering scheme and the absolute PDF page (e.g. slide N = PDF page N+12;
   Tab 7 "Page N" = PDF page N+114).
2. Record a small mapping table.
3. Cite the absolute PDF page in lineage, and note the internal reference in
   parentheses.
4. Flag (do not silently reconcile) when a brief's cite uses an internal scheme;
   confirm the offset against the map before trusting any single cite.

Without the map, every cite risks being off by a fixed offset and downstream
tie-outs are unverifiable.

## Tie-out: verify inherited basis labels, not only values (obs 358)

Tie-out that checks only numeric values is incomplete. Metadata labels (basis:
geometric vs arithmetic, as-of date, net/gross, currency) are load-bearing
assumptions that flow into downstream transforms (e.g. a geo->arith conversion is
only valid if the input truly is geometric). An unstated-but-assumed label is a
silent error class that value spot-checks cannot detect.

For each metadata label, verify it against an on-page statement. If the page does
not state it, mark `UNLABELED` with `#ASSUME`/`#VERIFY` rather than inheriting the
label from a sibling column or a prior extraction. Treat label provenance with the
same rigor as value provenance.

## Dense fact sheets: layout/schema-aware parsing (obs 460)

Single-page dense financial fact sheets extract as a flat number stream with no
column headers attached (e.g. `19387 19.1% 27.5% -8.4% -8504`), and bar-chart
performance numbers come out as an unlabeled flat stream (e.g. 36 numbers =
9 series x 4 periods). The spatial context is visually clear in the PDF but the
text extraction drops it. Correct parsing requires knowing the table schema in
advance:

1. State the expected table schema before parsing (e.g. 5 columns:
   MV, Actual Wt, Target Wt, Diff%, Diff$).
2. Map the number stream to column positions against that schema.
3. Cross-validate: sum of MV rows must equal the total row; cross-check the first
   series (e.g. Total Fund) against a benchmark/monthly report for the same
   trailing periods.

## No-sudo dependency note

For one-off extraction dependencies in locked-down environments, prefer `uv run --with <pkg> python ...` (e.g. `--with pymupdf`); it needs no sudo/root and leaves no global state, unlike a system poppler-utils install.
