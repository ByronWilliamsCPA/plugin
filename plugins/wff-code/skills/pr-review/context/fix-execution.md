# Fix Execution (Step 4)

Full procedure for `workflows/pr-fix.md` Step 4, "Execute fixes in priority
order". Consumes the unified issue list from Step 2 and the worktree from
Step 3; produces applied edits inside `WORKTREE_PATH`, grouped by the five
priority tiers below, ready for Step 5 verification.

Work through issues in this order. CI failures first because they block merge
and may cause cascading issues.

## Editing constraint: repos with PostToolUse ruff hooks

If the repo has a ruff PostToolUse:Edit hook (check `hooks.json` or the live
`~/.claude/settings.json` for `"PostToolUse"` entries running ruff or pre-commit;
per ADR-002 this repo's authoritative hook definitions live in `hooks.json` and
are merged into `~/.claude/settings.json` by `setup.sh`), each Edit call must
leave the file in a valid ruff state at hook-fire time, not just at the final
intended state.

The most common failure mode: adding `import sys` (or any stdlib import) in
one Edit call, then adding its usage in a second Edit call. Ruff's unused-
import rule (F401) fires after the first call and removes the import before
the second call can reference it.

**Rule:** When adding a new import to a file in such a repo, always include
at least one usage of the symbol in the same Edit call. Plan edits so no
intermediate state introduces an unused import or unreferenced symbol.

**Editing `.github/workflows/*.yml`:** The `security_reminder_hook.py` PreToolUse hook
commonly fires as a one-time informational reminder that blocks the FIRST Edit on a
workflow file, then allows an identical retry. For a benign change with no `${{ }}`
injection surface (e.g., a `node-version` string bump), retry the identical Edit once
before falling back to a `sed`/Python rewrite. Fall back to non-Edit rewriting only if
the retry is also blocked. Hook behavior here is environment- and version-dependent;
confirm the current behavior rather than assuming a permanent hard block.

When the `PreToolUse:Edit` security hook fires on GHA YAML and the Edit tool will not
execute even on an identical retry, use a Bash+Python fallback rather than fighting the
hook: read the file with `pathlib.Path.read_text()`, apply one targeted `str.replace()`
per finding (each guarded by `assert old in txt, "<description>"`), then write back with
`pathlib.Path.write_text()`. The assertion guards give the same unique-match safety as the
Edit tool's uniqueness check and make a partial-match failure explicit instead of silently
producing wrong output; batching all of a file's changes into one script is also more
reliable for multi-edit sessions. The hook does not intercept the Bash tool.

**RAD markers in YAML go on separate comment lines.** When writing paired `#ASSUME`/`#VERIFY`
RAD markers in YAML (workflow files, compose files), always place `#ASSUME` and `#VERIFY` on
separate comment lines; never combine them on one line. YAML indentation (commonly 8-12
chars) plus the combined form `# #ASSUME: ... #VERIFY: ...` almost always exceeds the
yamllint 120-char line-length limit at any indentation depth beyond a few characters, so the
qlty/yamllint gate fails on a marker that would fit fine in a prose comment.

**A fix pass invalidates its own downstream references and outward claims mid-pass.**
Editing one instance of a fact, a count, a line-anchor citation, a restated value, an
outward claim such as "N findings remain" or "all tests pass", does not update every other
place that states the same fact. After any edit that changes something restated elsewhere
(a summary table, a front-matter count, a cross-reference line number, a PR-body claim
about test counts or CI status), sweep every location that restates it and regenerate the
claim from the post-edit state, not from a value captured earlier in the pass. This applies
to behavioral claims as much as numeric ones: a PR-body sentence like "exits nonzero on any
threshold miss" is exactly the kind of assertion a fix for a Critical finding is most likely
to falsify, and a reviewer who trusts the stale prose will not re-derive the real behavior.
When a claim's truth depends on work still to come later in the same pass (a test count
while more tests are still being added), sequence its correction as one of the last actions
before the final verification gate, not the moment the discrepancy is first noticed;
correcting it early and then continuing to change the underlying facts silently reintroduces
the same staleness the correction was meant to fix.

## Priority 1: CI failures

For each failing check, apply the fix strategy from the Step 1a table.
After each category, verify locally before moving on. The verification
commands use `uv tool run` (overseer's global tool environment), not
`uv run` (which would pull tools from the reviewed repo's `pyproject.toml`
and `uv.lock` and recreate the AG04 trust gap that Step 5a's tiers close).

- Lint fixes: `cd {WORKTREE_PATH} && uv tool run ruff check .`
- Format fixes: `cd {WORKTREE_PATH} && uv tool run ruff format --check .`
- Type fixes: resolve the source directory first; do not hard-code `src/`, which
  silently no-ops on a repo laid out differently (a flat package, `lib/`, a `packages/*`
  monorepo). Read `tool.basedpyright.include` from `pyproject.toml` if present, else the
  package name under `[project]` / `[tool.hatch.build]`, else fall back to the repo root:
  `cd {WORKTREE_PATH} && uv tool run --from basedpyright basedpyright {SRC_DIR}`
- Test fixes: do NOT run `pytest` here. `pytest` auto-imports `conftest.py`
  at collection time, which executes reviewed-repo Python before any test
  body runs. Defer test verification to Step 5a's confirm tier, which
  presents `pytest` to the user as an opt-in confirmed candidate. Mark
  the test-fix category as "verification deferred to Step 5a" and
  proceed to the next category.

**Verify per-repo before assuming the changelog gate is a no-op.** The changelog is
generated at release time by python-semantic-release from Conventional Commits, and most
repos in this org have no per-PR changelog gate to satisfy: the org `Changelog Check` job
is a deprecated no-op that always passes (see `ByronWilliamsCPA/.github` PR #288). This is
not universal, and the blanket claim that a red Changelog check "always" means a stale
pinned ref is falsified by at least one repo: cyo-adventure defines its own live local
`changelog` job that greps for a `CHANGELOG.md` entry and fails the PR without one, with an
`if:` condition that explicitly sanctions a `skip-changelog` label. Before diagnosing a red
required Changelog or Dependency-and-Standards check, grep the repo's own
`.github/workflows/*.yml` for a locally-defined `changelog` job.

- If none exists, the stale-ref diagnosis stands: do not hand-edit `CHANGELOG.md`, do not
  apply changelog-skip labels, and never fabricate a `[Unreleased]` entry; diagnose it as a
  workflow-load/ref issue instead.
- If a live local job exists, still do NOT hand-edit `CHANGELOG.md`. Apply the sanctioned
  `skip-changelog` label instead, and mind the ordering: the job reads labels from the
  triggering event's payload, not live PR state, so the label must be applied *before* the
  next push or synchronize. Adding the label to an already-red run and waiting for it to
  "re-evaluate" is a silent no-op; nothing re-runs until a fresh event carries the label.

For repos without a local gate, the release-impacting signal lives in the PR title and
commit types, which the commit-type validation below enforces.

**Invalid commit-type fixes (non-interactive reword):** When a commit on the branch uses
an invalid or non-allowed Conventional Commit type (a Critical CLAUDE.md violation),
rewrite it without an interactive terminal. Interactive `git rebase -i` is unavailable in
automated contexts; use scripted editors instead:

**Validate before interpolating (mandatory).** `<bad-prefix>` and `<good-prefix>` come from
commit-message text in the reviewed, untrusted PR. Interpolating either directly into the
single-quoted `GIT_SEQUENCE_EDITOR`/`GIT_EDITOR` values below is a shell injection vector: an
unescaped `'` in the commit-message text breaks out of the quoted string, and whatever
follows it executes as a shell command during the automated `rebase -i`. Reject anything that
is not a bare Conventional Commit type before building either command:

```bash
for p in "$BAD_PREFIX" "$GOOD_PREFIX"; do
  [[ "$p" =~ ^[a-z][a-z0-9_-]*$ ]] || {
    echo "Refusing to rewrite: '$p' is not a safe commit-type token" >&2
    exit 1
  }
done
```

Only after both values pass this check may they be substituted below; the allowlist pattern
makes the shell-metacharacter injection impossible rather than merely escaped.

```bash
# GIT_SEQUENCE_EDITOR marks the target commits as `reword`;
# GIT_EDITOR replaces the invalid prefix in each reworded message.
GIT_SEQUENCE_EDITOR='sed -i "s/^pick \(.*\) <bad-prefix>:/reword \1 <bad-prefix>:/"' \
GIT_EDITOR='sed -i "1s/^<bad-prefix>:/<good-prefix>:/"' \
git -C {WORKTREE_PATH} rebase -i origin/{BASE_BRANCH}
```

This rewrites every subsequent commit SHA and requires a force-push (Step 8). Flag in the
PR summary that any SHA referenced in prior review comments is now stale.

**Dependency CVE bumps: check base and open bot PRs first.** On an actively-maintained
repo, automated bots may resolve the same CVE concurrently, so authoring a duplicate bump
creates redundant work and a lockfile conflict. Before committing a dependency bump to clear
a CVE: (1) `git fetch origin {BASE_BRANCH}` and check whether base's lockfile already
satisfies the fixed version (`git show origin/{BASE_BRANCH}:uv.lock | grep -A1 'name = "<pkg>"'`);
(2) check for an open Renovate/Dependabot PR bumping the same package. If base already fixes
it or a bump PR is open, recommend "rebase onto base / merge the bump PR" instead of a
duplicate bump. This moves the rebase-preference check earlier (pre-commit, not just
pre-push at Step 7).

**Python version compatibility:** Check for `datetime.UTC` (use
`datetime.timezone.utc`), `tomllib` without fallback, `match/case` syntax,
`ExceptionGroup` without backport. Apply 3.10-compatible equivalent.

**File move / path-boundary fixes:** When CHANGED_FILES includes a file rename
across a path-boundary (e.g., `scripts/` to `src/`), run the destination-path
linters against the FULL moved file (not just changed lines):

```bash
uv tool run ruff check {new_path}
# If darglint/pydoclint applies to dst path:
uv tool run --from pydoclint pydoclint {new_path}
```

Pre-commit's changed-files scoping hides violations the move newly exposed;
a full-file scan is required to surface them before commit.

**JS/TS dependency manifest-lockfile sync (blocking):** When a fix adds or removes a
JS/TS package (e.g., migrating a generator's plugin config), `package.json` and its
lockfile must stay in exact sync or CI's `npm ci` fails hard (`npm ci` requires an exact
match; a half-migration is strictly worse than no change because it converts a latent
issue into a hard CI failure). The Step 5a default gate is Python-only and will not
catch this. Treat a manifest/lockfile desync as a blocking condition:

1. Detect the package manager from the committed lockfile: `package-lock.json` -> npm,
   `pnpm-lock.yaml` -> pnpm, `yarn.lock` -> yarn.
2. **Confirm before running (mandatory; this is a confirm-tier action, not default-tier).**
   `npm install`, `pnpm install`, and `yarn install` execute repo-controlled `package.json`
   lifecycle scripts (`preinstall`/`postinstall`/`prepare`) unconditionally; there is no
   `uv tool run`-equivalent isolation for the JS/TS ecosystem. Present the lockfile diff and
   the exact command to the user and require the literal reply `yes`, using the same
   per-candidate confirmation sequence as Step 5a
   ([context/fix-verification.md](fix-verification.md#5a-local-gate-sequence)), before
   running `npm install` / `pnpm install` / `yarn install`. Never run it unprompted, even when
   every other part of the fix is auto-fixable.
3. Verify the frozen-install command succeeds before commit: `npm ci`
   (or `pnpm i --frozen-lockfile`, `yarn install --frozen-lockfile`). The binding
   correctness check for a lockfile-bearing ecosystem is "does the frozen-install
   succeed against the regenerated lockfile," not the language linters.
4. Run the repo's dependency-vulnerability scanner locally against the regenerated
   lockfile (`npm audit`, `osv-scanner`; by analogy `uv export | pip-audit` for `uv.lock`)
   and confirm 0 high/critical BEFORE committing. A lockfile is an input to security/SCA
   gates: an out-of-sync lockfile can make `npm ci` fail before the scanner ever parses it,
   so regenerating it to satisfy the installer can feed the full resolved tree to a scanner
   that gates merge and flip a previously-green REQUIRED gate (Security Gate / OSV-Scanner)
   to red. Fixing a non-required check (e.g. a `Frontend` npm-ci check) this way can regress
   a required one. If the scan surfaces advisories, patch them (or revert) before pushing;
   never push a regenerated lockfile without re-running the dependency scanner that consumes
   it.

**Sequential-ID register collisions: check concurrent branches before appending.** A fix
that appends a row to an append-only, sequentially-numbered register (a standards
manifest, a numbered lessons log, an ADR index) can collide with an identical append
landed on a sibling branch: both branches read the same "next" ID, both commit it, and
per-branch CI stays green because nothing detects the collision until the second branch
merges and the ID space is scanned as a whole. A mechanical renumber to resolve the
collision is worse than the collision itself: it can silently falsify any row whose own
text quotes the shifted ID range (a cross-reference, a "rows 40-45" summary), and the
renumber succeeds syntactically, so this is easy to miss. Before appending: (1) diff the
register file against `origin/{BASE_BRANCH}`, since `mergeable` describes the diff as it
stands and says nothing about a conflict the append is about to create, and merge the base
in first if it is ahead in that file; (2) scan other open PRs touching the same register
file for an in-flight ID claim in the same range. Prefer a non-sequential or
content-derived ID scheme in new registers to remove this class of collision at the
source.

## Priority 2: SonarQube findings

**Auto-fix** (no user prompt needed): mechanical, low-risk changes:

| SonarQube pattern | Fix |
| --- | --- |
| Missing explicit `return` (shell:S7682) | Add `return 0` or `return` |
| Redundant exception type (python:S5713) | Remove subclass from tuple |
| Security hotspot | Apply prescribed remediation; call `show_rule` for guidance |
| Single-bracket conditional (shelldre:S7688) | Replace `[ ... ]` with `[[ ... ]]` only if the script shebang is `#!/bin/bash` or `#!/usr/bin/env bash`; skip if `#!/bin/sh` or no shebang |
| Missing default case in `case` (shelldre:S131) | Add `*) ;;` default case to `case` statements |
| Error message to stdout (shelldre:S7677) | Redirect error messages to stderr: `echo "..." >&2` |
| Positional parameter not named (shelldre:S7679) | Assign positional parameters to named local variables at function start |
| Constant boolean expression in test (python:S5914) | Remove the trivially-true assertion or replace with a meaningful assertion for what the test actually verifies; use `assertIsNotNone` only when the test intent is specifically a non-None check |
| Float equality check (python:S1244) | Replace float equality check with `math.isclose()` in production code, or `pytest.approx()` in test code |

**Trivy / container-security `.trivyignore` fix pattern:**
When remediating container scan failures by editing `.trivyignore`, verify
the workflow's `paths:` filter includes `.trivyignore`:

```bash
grep -l "trivyignore\|trivy" .github/workflows/*.yml \
  | xargs grep -l "paths:" \
  | xargs grep "trivyignore" 2>/dev/null || echo "trivyignore NOT in paths filter"
```

If `.trivyignore` is absent from the `paths:` filter, add it (and the workflow
file itself) to both trigger paths, so the fix self-verifies when pushed.

Also, before investing in Trivy remediation, verify the check is actually a
merge blocker. A red Trivy check with `mergeStateStatus: UNSTABLE` (not
`BLOCKED`) means it is advisory; scope effort accordingly.

**Propose and confirm** (show the proposed change, wait for user approval before
applying): these touch logic, security policy, or refactoring:

For each propose-and-confirm finding, before presenting the proposed fix to
the user, call `Skill("panel")` in flexible panel mode to validate the fix:

```text
Skill("panel")(
  mode:   "panel",
  models: [PANEL_MODEL],
  prompt: "A SonarQube finding requires a propose-and-confirm fix before I
           show it to the user. Validate the proposed fix is correct and safe.

           Finding: {rule key}: {message}
           File: {file path}, line {line}
           Current code:
           {10 lines of context around the finding}

           Proposed fix:
           {description of the planned change}

           Questions:
           1. Is the proposed fix semantically correct (does it preserve the
              original behavior for all non-vulnerable inputs)?
           2. Does the fix introduce any new risks (e.g., regression, changed
              semantics, security implications)?
           3. Is there a better fix?

           Reply with: APPROVE, REVISE (with suggested revision), or
           REJECT (with reason). One word verdict on the first line."
)
```

If the panel returns REVISE or REJECT, update the proposed fix before showing
it to the user. Do not block on this call; if `OPENROUTER_API_KEY` is not set
or the panel is unavailable, proceed with the original proposed fix and note
"panel validation skipped" in the presentation.

| SonarQube pattern | Proposed fix |
| --- | --- |
| ReDoS regex (python:S5852) | Show current pattern and proposed replacement; explain why it is vulnerable; apply only after approval |
| Nested `if` in shell (shelldre:S1066) | Show merged condition; note whether `set -e`/`errexit` affects error-handling semantics; apply only after approval |
| Nested `if` in Python (python:S1066) | Show merged condition using `and`; apply only after approval |
| Unused local variable (shelldre:S1481) | Show variable and usage context; confirm intent before removing (may be an intentional placeholder) |
| Repeated string literal (python:S1192) | Show proposed constant name and extraction site; apply only after approval |
| Broad workflow permissions (githubactions:S8234) | Read job steps, derive minimum permission set, show diff; apply only after approval |
| Workflow-level permissions (githubactions:S8233) | Show proposed per-job permissions block; apply only after approval |

## Priority 3: Review comments

For each unresolved actionable comment:

1. Read the referenced file in the worktree (20 lines of surrounding context)
2. Apply the requested change
3. Record: thread ID, file, description of fix (for reply in Step 7)
4. Fix the root cause of the finding, even if it lives in a different function or file
   than where the symptom was reported. Keep the diff as small as the root cause
   requires. Do not refactor unrelated code, rename variables for style, or add
   features not requested. When the root cause fix touches more than 3 files not in
   the original diff, pause and confirm with the user before proceeding.

**Trace the mechanism and blast radius before fixing, not just the root-cause file.** A
root-cause fix that stops at "the function now behaves correctly" can still leave the
defect reachable. Enumerate every caller, every test double standing in for the changed
code, any generated artifact derived from it (a snapshot, a lockfile, a compiled schema),
any mirror instance of the same logic copied elsewhere in the repo, and any state reachable
through the change but not exercised by the review that found it. An unguarded
out-of-diff caller, or a hand-rolled test double built against the old (looser) contract,
survives a fix that claims to close the whole class and reopens the same finding on the
next pass. Treat "how many places does this reach" as part of the fix's cost to evaluate
before committing to it, not as a follow-up discovered later.

**Documenting a declined recommendation:** When the fix DECLINES a recommendation (keeps
the current posture deliberately), the documentation must state the decision first, then
scope any mitigation to the audience it applies to. Write (a) that the declined posture
is a deliberate decision, and (b) any opt-out/mitigation instruction bounded to its
audience (e.g., "on other machines, set X"). A RAD `#VERIFY` note that states only the
mitigation ("set the entry to false first") without stating the decision reads as a
contradiction of the committed value, and an automated reviewer (CodeRabbit) will flag
the gap on the next pass, costing a re-fix cycle. Decision first, mitigation second.

**Verify a finding's claim before applying it (substantive vs cosmetic).** Both review-agent
findings and bot review comments can be confidently wrong; applying them blindly inherits
their false positives.

- *Substantive findings* get behavioral verification: treat the assertion as a hypothesis
  and confirm it against the actual code before changing anything.
- *Technical claims about tool schema/behavior* (from Copilot/CodeRabbit) get doc
  verification: confirm against the authoritative source (WebFetch) before acting. If the
  claim is false (e.g., a "this option is invalid" claim the docs contradict), record it as
  "Declined: false positive" with the doc citation instead of authoring a wrong fix.
- *Cosmetic/style findings* (indentation, formatting, quoting, naming) get
  convention-consistency verification: before applying, check whether the flagged pattern is
  the file's consistent house style. The only valid outcomes are "fix all occurrences" or
  "leave as house style"; never fix a strict subset, which introduces the very inconsistency
  the finding claimed to remove.
- *Documented intentional non-catches:* before applying any silent-failure fix, read the
  full file (not just the hunk) and honor a rationale documented in the enclosing function or
  module docstring. A documented deliberate non-catch is not a defect; do not implement a fix
  that contradicts it.
- *Every stated fact needs re-derivation at its own pinned reference, not trust in the
  finding's transcription.* A finding's stated file path, line number, occurrence count,
  granularity (single line vs whole block), and scope (this file vs every file matching a
  pattern) are each a separate claim, and each can be wrong independently of the others.
  Before editing, open the finding's own cited reference (a commit SHA, a specific line, a
  rule ID) and re-derive every one of these facts directly, rather than transcribing the
  finding's numbers into the edit. A stated line number applied verbatim, when the file has
  shifted since the finding was generated, writes a correct-looking edit into the wrong
  place. When a finding names more than one call site, re-derive the remedy at each site
  independently rather than applying one fix uniformly: a shared API does not imply shared
  semantics, and the same default can be right at one call site and wrong at another.

**Agent-supplied test assertion verification:** When applying tests from the pr-test-analyzer
agent or any agent-generated test skeleton, treat assertions as hypotheses, not ground truth.
Before committing, confirm each assertion against the actual control flow:
- Check the function's exit code convention (scripts often exit 0 on logical failure)
- Verify stdout vs stderr routing for the asserted output
- Run the new test and confirm it passes because the code does what the test claims

**Handling by finding category:**

| Category | Fix approach |
| --- | --- |
| Shell script error handling (`set -e` before `$?`, wrong exit code) | Fix specific line; match repo hook contract |
| Bare python calls (`python` vs `uv run python`) | Replace; check pyproject.toml/uv.lock first |
| Hard-coded absolute paths (`/home/user/...`) | Replace with `~`, `$HOME`, or relative path |
| Documentation accuracy (see sub-categories below) | Read the authoritative source, update docs to match |
| Broken relative links | Compute correct path from source to target |
| Diagram/config drift (PUML vs actual settings) | Read actual config, update diagram source |
| Markdown table formatting (extra pipes, missing spaces) | Fix table syntax |
| Closure scope capture (implicit outer vars) | Make parameter explicit |
| Assert in production (`assert x is not None`) | Replace with `if x is None: raise RuntimeError(...)` |
| Em-dash violations | Replace with comma, semicolon, colon, or restructured sentence |
| `== None` / `!= None` | Replace with `is None` / `is not None` |
| Bare `except:` | Replace with `except Exception:` |
| Docstring parameter mismatch | Update docstring to match function signature |
| `jq` invoked without presence guard (with `set -euo pipefail`) | Add `command -v jq >/dev/null 2>&1 \|\| { echo "jq not found" >&2; exit 1; }` before first `jq` call; in Claude Code hooks, omit `>&2` so Claude can surface the error (see hook block message row) |
| Hook block message written to stderr instead of stdout | Change `>&2` redirect to stdout so Claude surfaces the block reason; this applies to hook scripts only, not general shell scripts |
| `grep -nP` used (requires GNU grep / PCRE) | Replace with POSIX-compatible `grep -n` plus equivalent pattern, or note BSD incompatibility inline |
| PowerShell single-quote escaping in bash | Mark "requires manual fix": escaping logic is error-prone to auto-patch |
| Stale file-header comment blocks | After fixing all implementation-level references to a replaced tool, also grep the file's comment/documentation block (lines 1-30) for references to the deprecated tool and update them |

**Documentation accuracy sub-categories:**

| Sub-category | Fix approach |
| --- | --- |
| Docs reference wrong Python version | Read `requires-python` from `pyproject.toml`, update docs to match |
| Docs describe wrong pre-commit hook exclude list | Read `.pre-commit-config.yaml`, update docs to match actual excludes |
| Spec frontmatter `status` conflicts with body `Status:` blockquote | Frontmatter `status` is schema-validated (`draft \| in-review \| published`); update the body blockquote to be consistent in spirit with the frontmatter value; never change frontmatter to a non-schema value |
| Architecture section asserts a hook is wired in `settings.json` but it is not | Update doc to say "not yet wired" rather than asserting it is wired |
| Design spec missing required metadata blockquote (Date / Status / Scope) | Add the blockquote using the same format as other specs in the same directory |
| Skill SKILL.md intro says "N modes" but body documents N+1 modes | Count the documented modes and update the intro sentence to match |
| Collaboration document (e.g., `COWORK.md`) says filename is "or similar" but README specifies exact filename | Read the README for the canonical filename and update the collaboration document to match |

**Assign to specialized agent (cannot auto-fix):**

For each of the following, launch the named agent to evaluate the finding and
produce a concrete fix recommendation or draft fix. Run agent evaluations in
parallel after all auto-fixes are applied (Step 4 end). Include agent outputs
in the Step 6 commit options and Step 8 PR summary.

**Brief mechanical-fix agents to forbid the harmful class precisely, not an over-broad
proxy.** When dispatching agents for a mechanical batch fix (docstring sync, type-hint
backfill, import sort), do NOT instruct "never change code": that over-broad prohibition
conflicts with validators whose rules require signature annotations (e.g., pydoclint DOC107
on an unannotated `call_next`), and an agent forced to satisfy both will reach for a
suppression hack (`# noqa`) that trips the next linter. Instead forbid the harmful class
exactly: "do not change runtime behavior or logic." Permit type-only signature changes
(matching the existing pattern in sibling files) with the supervisor reviewing the aggregate,
or carve the type-requiring cases out for the supervisor to handle directly.

| Finding type | Agent to invoke | What to ask it |
| --- | --- | --- |
| Test coverage gaps (from review comments) | `test-writer` | Generate minimal tests covering the flagged uncovered lines |
| Type design issues | `type-design-analyzer` | Evaluate the type and rate encapsulation/invariant expression; propose improvements |
| Cognitive complexity (python:S3776) | `code-reviewer` | Propose the minimal refactor to reduce complexity below the threshold |
| Complex logic bugs | `code-reviewer` | Evaluate the reported bug; propose a safe, targeted fix |
| Security vulnerabilities (non-secret) | `security-auditor` | Assess severity, propose a remediation that does not change calling contracts |
| Path from user-controlled data (pythonsecurity:S2083) | `owasp-web` | Evaluate the injection risk, propose input validation or path sanitization |
| SVG regeneration | `diagram-maintenance-agent` | Regenerate SVG from the updated PlantUML source |
| PlantUML diagram accuracy | `diagram-maintenance-agent` | Cross-reference settings files, update diagram source, regenerate SVG |
| Force-push guard bypass | `security-auditor` | Evaluate the bypass vector, propose a configuration or hook-based guard |

**Always mark human-only (no agent can resolve):**

| Finding type | Reason |
| --- | --- |
| Design debates from prior PRs | Unresolved architectural decisions requiring stakeholder input |
| GitGuardian secret detected | Alert user immediately; never auto-patch or agent-patch |
| Reversing a deliberate product decision | Requires explicit product owner approval |

## Priority 4: Coverage gaps

**Unified test policy:** Tests are generated automatically only when Codecov
is failing and specific uncovered lines can be identified from the coverage
report. Never add tests in response to review comments alone. If a review
comment requests better test coverage but Codecov is not failing, mark the
item "requires manual fix" and include it in the skipped list.

If Codecov is failing:

- Identify uncovered new/modified lines from coverage report
- Use test-writer agent pattern to generate minimal tests that cover only
  those specific lines; do not pad coverage by testing unrelated code
- Run tests in worktree to verify
- Before confirming with the user, validate the generated tests are not
  tautological:

```text
Skill("panel")(
  mode:   "panel",
  models: [PANEL_MODEL],
  prompt: "Review these generated tests for tautological failures (tests that
           will pass regardless of whether the code under test is correct).

           Tests to review:
           {generated test code}

           Code under test:
           {relevant function/method being tested}

           For each test, answer:
           1. Would this test catch a wrong return value?
           2. Would this test catch a missing branch?
           3. Does this test assert behavior, or does it just call the function
              and assert it does not throw?

           Flag any test that is tautological. Suggest a minimal fix for each
           flagged test. If all tests are sound, say 'All tests are behaviorally
           meaningful.'"
)
```

  If the panel review flags tautological tests, revise them before presenting
  to the user.
  Note any tests that could not be made non-tautological in the confirmation
  prompt.

- Confirm with the user before committing generated tests

If no Codecov integration, skip entirely.

## Priority 5: Agent findings (from pr-review)

If `FINDINGS` from pr-review are in context, apply fixes using the same
category rules from Priority 3 above. The "requires manual fix" skip list
is the same.
