---
description: >
  Documentation health audit. Scans markdown docs for frontmatter violations,
  broken internal links, count claim drift, and stale version references.
  Outputs a terminal summary table and writes docs/audit-report.md.
  Triggers on: doc-audit, audit docs, check docs, frontmatter audit,
  broken links, stale docs, documentation health.
tools: ["Read", "Bash", "Glob", "Grep", "Write"]
---

# Doc Audit Skill

Run a four-category documentation health audit and produce a persistent report.

## Invocation

```text
/doc-audit [scope]
```

`scope` is optional (default: `docs/`). Examples:
- `/doc-audit` — audit all of `docs/`
- `/doc-audit docs/superpowers/specs` — audit a subdirectory

## Workflow

1. Determine scope from argument or default `docs/`
2. Run the audit script:
   ```bash
   python3 scripts/doc-audit.py --scope <scope>
   ```
3. Parse the JSON output
4. Print the terminal summary table (see format below)
5. Write `docs/audit-report.md` (overwrite if it exists)
6. Print the completion message

## Terminal Summary Table

Print this table after parsing the JSON:

```text
Doc Audit Summary
─────────────────────────────────────────────────────
Category       Status      Issues
─────────────────────────────────────────────────────
Frontmatter    ✅ PASS     0 issues
Broken links   ⚠️  WARN    2 broken internal links
Count claims   ✅ PASS     0 issues
Version refs   ⚠️  WARN    4 stale references
─────────────────────────────────────────────────────
6 issues found. Full report: docs/audit-report.md
```

Status per category:
- `✅ PASS` — error=0 and warn=0
- `⚠️  WARN` — warn>0, error=0
- `❌ ERROR` — error>0 (regardless of warn count)

Issue count in the summary line: sum of all findings with severity ERROR or WARN across
all categories. INFO findings are not counted in the summary line but appear in the report.

## Audit Report

Write `docs/audit-report.md` with this structure (substitute actual values):

```markdown
# Doc Audit Report

Generated: YYYY-MM-DD  Scope: docs/

## Summary

| Category     | Pass | Warn | Error |
|-------------|------|------|-------|
| Frontmatter | N    | N    | N     |
| Broken links | N   | N    | N     |
| Count claims | N   | N    | N     |
| Version refs | N   | N    | N     |

## Frontmatter Issues

- `docs/foo.md` line 1: missing required field `owner` (schema_type: common)

## Broken Links

(none)

## Count Drift

- `docs/overview.md` line 14: claims '15 agents' — actual: 18

## Stale Version References

- `docs/setup.md` line 7: Python 3.8 is outside declared range >=3.10,<3.15 in pyproject.toml
```

For sections with no findings, write `(none)` as the body. Include INFO findings in the
relevant section with an `[INFO]` prefix so they are visible but clearly distinguished from
actionable WARN/ERROR items.

## Docs Build Health on main (Obs 78)

The four static categories above do not catch a docs build that is broken on `main` itself.
The docs-build CI job is typically path-filtered (only runs on PRs that touch `docs/`), so a
transitive dependency regression (e.g., a pygments / pymdown-extensions interaction) can break
`mkdocs build --strict` on main and stay invisible until the next docs-touching PR inherits
the failure and is wrongly blamed for it.

When the project ships a docs build, run it against current main as a supplementary check and
report the result independently of the static-scan categories:

```bash
# Reproduce the path-filtered docs job against main
uv run mkdocs build --strict
# or fetch the latest main run for the docs workflow
gh run list --workflow=docs.yml --branch main --limit 1
```

If the build fails on clean main, surface it as an ERROR-level finding ("docs build broken on
main, independent of any open PR") so the inherited regression is fixed at the source rather
than discovered by the next contributor.

## Completion Messages

Print one of these after writing the report:

- Any `ERROR` finding: "Audit complete. X errors require attention before next PR."
- Only `WARN` findings, no errors: "Audit complete. X warnings flagged for review."
- No WARN or ERROR findings: "Audit complete. No issues found."

X is the total count of findings at that severity level.
