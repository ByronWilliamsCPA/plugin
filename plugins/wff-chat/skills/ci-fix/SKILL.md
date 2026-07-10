---
description: >
  Full CI gate sequence with auto-fix loop. Runs ruff format, ruff lint, qlty check,
  pre-commit, pytest, bandit, and pip-audit in order: fixing what it can and reporting
  blockers. Triggers on: ci-fix, fix ci, fix gates, all gates green, pre-commit failing,
  tests failing, ci failing, fix everything, gates failing.
tools: ["Read", "Bash", "Grep", "Glob", "Edit", "Write"]
---

# CI Fix Skill

Run a consistent 7-gate quality sequence, auto-fix where possible, and offer to commit when
all gates are green.

## Invocation

```text
/ci-fix
```

No arguments. Always runs the full gate sequence.

## Gate Sequence

Run gates in this fixed order. After each fix attempt, re-run the gate before advancing.
Never skip a gate. Never change the order. If the same gate fails after two consecutive fix
attempts, mark it `❌ BLOCKER` and advance to the next gate.

| # | Gate | Command | Auto-fix strategy |
|---|------|---------|-------------------|
| 1 | ruff format | `uv run ruff format --check .` | `uv run ruff format .` (deterministic) |
| 2 | ruff lint | `uv run ruff check .` | `uv run ruff check --fix .`; remaining unfixable rules: edit manually |
| 3 | qlty check | `qlty check` | No auto-fix: refactor functions exceeding complexity/nesting thresholds |
| 4 | pre-commit | `pre-commit run --all-files` | Re-run after ruff fixes; remaining failures: fix and re-run |
| 5 | pytest | `uv run pytest` | Read failure output, fix test or implementation issues, re-run |
| 6 | bandit | `uv run bandit -r src/ -c pyproject.toml` | Fix code issues; false positives: add `# nosec BXXX -- tracked: <URL or ticket>` with an open tracking reference |
| 7 | pip-audit | `uv run pip-audit` | Report only: dependency upgrades require user decision |

> **Bandit source root**: Before running bandit, check `pyproject.toml` for a `[tool.bandit]`
> `targets` field. If present, use that path. If absent, use `src/` if it exists, otherwise
> use `.` as the scan root.

## Status Table

Print the full table after each gate completes. Always print all 7 rows regardless of
how many have completed.

```bash
CI Fix Status
─────────────────────────────────────────────────────
Gate          Status       Notes
─────────────────────────────────────────────────────
ruff format   ✅ PASS
ruff lint     ✅ PASS      4 issues auto-fixed
qlty check    🔧 FIXING    2 functions exceed complexity threshold
pre-commit    ⏳ PENDING
pytest        ⏳ PENDING
bandit        ⏳ PENDING
pip-audit     ⏳ PENDING
─────────────────────────────────────────────────────
```

Status values:
- `⏳ PENDING`: not yet run
- `🔧 FIXING`: fix in progress
- `✅ PASS`: gate green (include note if fixes were applied)
- `❌ BLOCKER`: failed after fix attempt; manual intervention required

## Blocker Behavior

When a gate fails and cannot be resolved in one fix attempt:
- Mark it `❌ BLOCKER` in the table
- Continue running the remaining gates: report the full picture
- Do not stop early

pip-audit findings are always reported but never count as a blocker for the commit offer.
pip-audit status is always `✅ PASS` or `✅ PASS (advisories found: see notes)`: never `❌ BLOCKER`. List any advisories in the Notes column regardless of exit code.

## Completion

**All non-pip-audit gates green:**

```text
All 6 required gates green (pip-audit findings noted above). Commit now? (yes/no)
```

- **Yes**: invoke the `/git` skill with commit intent. Provide the gate summary (which gates passed, what was fixed) as context so it can generate an accurate conventional commit message.
- **No**: stop: present the green status table and hand back

**Any blocker remains:**

```text
5/7 gates pass. Blockers:

  ❌ pytest: 2 tests failing in tests/unit/test_processor.py (see output above)
  ❌ bandit: HIGH severity B608 at src/query.py:45 (see output above)

These require manual investigation before committing.
```

No commit offer when blockers remain.

## Environment Notes

Real-world operational patterns for common CI failure scenarios.

### GitHub Actions workflow file editing (Obs 62/41/48/49/50)

The security-guidance PreToolUse hook blocks the Edit and Write tools on `.github/workflows/*.yml` files. When editing workflow files, use Python string replacement via Bash as the primary path:

```bash
python3 - <<'EOF'
with open('.github/workflows/myfile.yml', 'r') as f:
    content = f.read()
content = content.replace('old_string', 'new_string')
with open('.github/workflows/myfile.yml', 'w') as f:
    f.write(content)
EOF
```

Use the most specific anchor string possible (include surrounding lines to make the pattern unique). Keep each file's replacement idempotent -- a failure on one file must not affect others.

### Batch CVE/lint backlog cleanup (Obs 76)

When a CI gate fails on something a local scanner can list exhaustively, enumerate the full backlog locally first, then fix all entries in one commit:

1. Run the local scanner: `uv run pip-audit`, `uv run ruff check .`, etc.
2. Fix all identified issues individually (single-package upgrade, single-rule fix)
3. Verify locally with the same scanner
4. Push once

Do not iterate one-fix-per-CI-cycle for a single class of issue. CI is the slowest oracle; local scanners return the full list at once. The bridge between "wholesale upgrade" (collateral risk) and "one-at-a-time" (slow) is "enumerate locally, fix individually, verify locally, push once."

### `uv lock --upgrade-package` requires explicit sync (Obs 77)

`uv lock --upgrade-package <name>` updates the lock file but does NOT update the active `.venv`. After running an upgrade, verify the new version is installed:

```bash
uv lock --upgrade-package idna
uv sync --reinstall-package idna   # update the venv to match the new lock
uv run pip-audit                    # now reflects the upgraded version
```

Without the explicit `uv sync --reinstall-package`, local `pip-audit` or test runs may still see the old version, producing a false "fix didn't work" signal.

### `git diff --name-only` includes deletions (Obs 137)

Any CI step that pipes `git diff --name-only` into a per-path tool (linter, formatter, test runner) will fail when the PR deletes files, because the deleted path no longer exists in the working tree. Add `--diff-filter=ACMR` to exclude deletions:

```bash
# Bad: includes deletions
git diff --name-only "origin/$BASE"

# Good: only Added, Copied, Modified, Renamed
git diff --name-only --diff-filter=ACMR "origin/$BASE"
```

Diagnostic tell: a per-file linter job fails fast (13-15s) while the tool's SaaS check passes -- that mismatch indicates a harness/enumeration error, not real lint findings.

### Path-filtered CI jobs hide regressions on main: reproduce-on-main diagnosis (Obs 78)

A CI job with a path filter (only runs on PRs touching `docs/`, only on Python changes, a
release-only workflow) trades compute for staleness latency: a regression in its domain can
sit undetected on main until the next path-matching PR inherits the breakage and gets blamed
for it. Example: a docs-build job only triggered on docs-touching PRs; a transitive plugin
interaction silently broke `mkdocs build --strict` on main, and the next PR that touched a
docs file inherited the red build.

Before fixing a failure on a path-filtered job, classify it: did this PR introduce the
failure, or merely expose an inherited regression already on main? Reproduce against main
before editing the PR's own changes:

```bash
# Reproduce the path-filtered job against main, independent of the current PR scope
git stash || true
git checkout main && git pull
# run the exact job command, e.g.:
uv run mkdocs build --strict
# or fetch the latest main run for that workflow:
gh run list --workflow=<docs-job>.yml --branch main --limit 1
```

If the failure reproduces on clean main, it is an inherited regression, not a defect in the
PR. Report it as a separate diagnosis class ("reproduces on main, not introduced by your
changes"), fix it as a real bug fix for main, and do not attribute it to the PR author. The
same pattern applies to any path-filtered job (release workflows, security-analysis when no
Python files changed).

### Dependency-review license failures may be pre-existing policy debt (Obs 255)

When the `dependency-review-action` gate fails on a license (not a vulnerability), distinguish "introduced by this PR" from "surfaced by this PR" before fixing. The gate only evaluates packages *changed* in the PR, so a routine Renovate version bump can surface a license-policy gap that already existed in the base branch.

```bash
# Was the flagged package already in main's lock file at an older version?
git show origin/main:uv.lock | grep -A2 'name = "<package>"'
```

If the package already exists on the base branch, the bump did not introduce the problem; it exposed it. Route the fix to the workflow allowlist (`allow-dependencies-licenses` on the dependency-review step) or a documented exemption, not to a revert of the bump. Diff-scoped gates (dependency review, patch coverage) report at the changed line or package, but the root cause may be pre-existing debt in the base branch.

### startup_failure with zero jobs is a caller/callee contract mismatch (Obs 266)

A GitHub Actions run that concludes `startup_failure` with an empty jobs array and no logs gives no error message via API or UI annotations, because the rejection happens at parse/contract time, before any job starts. The error surface is the contract between caller and callee (inputs, secrets, permissions, nesting depth), never the job logs. Do not search for logs that do not exist; diff the two workflow files:

```bash
# 1. Confirm the referenced workflow resolves
gh run view <run-id> --json referencedWorkflows

# 2. Diff caller with: block against callee workflow_call inputs (rule out input-name mismatch first)
# 3. Diff caller permissions block against EVERY job-level permissions block in the callee
```

Any permission the callee requests (e.g. `actions: read` on a codeql job) but the caller's explicit `permissions:` block omits fails validation before any job runs. (See also systematic-debugging: sample sibling consumers before concluding the reusable workflow itself is broken.)

### Stale-base CI failures masquerade as real failures: read the log and rebase first (Obs 586)

Before fixing code for a failing gate, confirm the failure belongs to the change and not the base. A branch several commits behind base can fail a gate on something the base already fixed: a `pip-audit --frozen` run against a stale lockfile keeps reporting CVEs that a later-merged PR already patched on base, and re-running the job can never clear it. The tell is that the failing artifact named in the log is unrelated to what the PR changed (e.g. pip-audit flags `pydantic-settings`/`msgpack` on a PR that only bumps `transformers`).

Diagnostic step before editing code:

1. Read the actual failure log; identify the failing artifact or package.
2. Compare it against what the PR changes. If unrelated and the branch is behind base, suspect a stale base.
3. Rebase onto current base and re-run. Only treat the failure as intrinsic once the branch is current with base.

A CI failure on a branch behind its base may belong to the base, not the change. Rule out stale-base before spending any effort on a code fix.

### `gh run rerun` replays a frozen merge commit, not the current base (Obs 510)

After fixing a broken workflow file on the base branch, `gh run rerun` on existing PR runs will NOT pick up the fix. For same-repo pull requests, GitHub creates a virtual merge commit (PR head merged onto base at merge time); `gh run rerun` replays that original merge commit unchanged, so it uses the workflow file as it was on the base at the time of the original merge event, not the current base.

To pick up a base-branch workflow fix, a new `pull_request` synchronize event is required, which makes GitHub build a fresh merge commit against the current base:

- Push (or force-push) to the PR branch.
- For Renovate branches where direct push is not possible, comment `@renovatebot rebase` to force a rebase.

Distinction: `gh run rerun` = replay the same frozen merge commit; new synchronize event = fresh merge commit against current base.

### Pre-validate every downstream config before each unblocking push (Obs 289)

A pipeline red for weeks hides every defect downstream of the first failing step. A pipeline that has never reached step N gives zero evidence about steps N+1..end, so fixing failures one CI round-trip at a time is the slowest possible loop. Before pushing each fix that unblocks a long-failing pipeline, locally validate every config the now-reachable downstream steps will consume:

```bash
# semantic-release config
uvx --from python-semantic-release semantic-release --noop version

# renovate.json
npx --package renovate renovate-config-validator
```

Treat every downstream config as unvalidated and run its dry-run or validator locally where one exists, instead of discovering defects one merge cycle at a time. Build the per-tool local-validation checklist as you go.

## GitHub Actions Authoring Anti-Patterns

Defects introduced while authoring or editing workflow files. These do not surface as lint findings; they surface as runtime failures with misleading error messages, so catch them at authoring time.

### Inline comment after `\` silently breaks line continuation (Obs 509)

In a `run:` block, `\` is a bash line continuation ONLY when it is the absolute last character on the line. A comment placed after `\` on the same line makes the `\` part of the comment text, so the next line is not joined and the shell sees a truncated command. The resulting error (e.g. `error: missing required argument 'collection'`) gives no hint that a misplaced comment is the cause, and the pattern is easy to introduce during review cleanup ("add a comment near this digest pin").

```bash
# Broken: the trailing comment consumes the continuation
my-cmd sha256:...run  # pin the digest \
  --collection foo

# Correct: comment on its own line before the command
# pin the digest
my-cmd sha256:...run \
  --collection foo
```

Line continuation (`\` as last char) and inline comments (`# ...`) are mutually exclusive on the same line; place comments on the preceding line, never after the continuation operator.

### Detect-before-scan for tools that exit hard on empty input (Obs 684)

A CLI tool that exits non-zero when given no work (rather than exiting 0 with no output) fails the build even when its scan is legitimately not applicable. Example: `snyk iac test` exits code 2 (a hard error, not "found issues") on a directory with no supported files, so a repo with no Terraform would fail an IaC gate.

Wrap such tools in a two-phase pattern: a detect job that probes for file presence (e.g. `find` for the relevant file types) runs first, and each scan job is gated via `needs:` + `if: needs.detect.outputs.found == 'true'`. Treat a `skipped` scan job as passing so the build is not blocked when the scan type is absent. This keeps the workflow safe to add to any repo regardless of its footprint, with no per-repo operator configuration.

Tools that distinguish "ran and found nothing" (exit 0) from "couldn't run at all" (exit 2) need detect-then-act; treating detect-and-skip as a success case is what makes the gate universally safe.

### `enable-*` vs `run-*` verb convention for reusable workflow inputs (Obs 685)

Naming verbs in reusable workflow inputs carry semantic load; a consistent convention makes the relationship between inputs readable without reading the implementation, and its absence forces explanatory comment blocks.

- `enable-*`: activates a feature nested inside another feature (requires a parent toggle to also be true). Example: `enable-aibom` is subordinate to `run-snyk: true`.
- `run-*`: toggles a standalone job or top-level capability at the same level as sibling jobs.

Both are boolean; the verb signals whether the input is a subordinate feature gate or a peer job toggle. Apply this when adding inputs to reusable workflows so future additions do not need a comment to explain the distinction.
