# PR Fix Workflow

Gathers all open issues on a PR from every source and resolves them.
Can run standalone (`/pr-fix <URL>`) or as a follow-up from `pr-review.md` Step 10.

## Input

**Standalone mode**: `$ARGUMENTS` contains the GitHub PR URL.
If empty, detect from the current branch via GitHub MCP `pull_request_read`
method `get`, or `gh pr view --json url`.

**From pr-review**: `FINDINGS`, `SONAR_FINDINGS`, `OWNER`, `REPO`,
`PR_NUMBER`, `HEAD_BRANCH`, and `PREMISE_VERDICT` (if present) are already in
context from the review. When `PREMISE_VERDICT.verdict` is `HOLD` or `UNRESOLVED`,
prepend a line to the fix summary: "Premise gate flagged {PREMISE_VERDICT.verdict}:
{PREMISE_VERDICT.headline}. This fix proceeds at the user's explicit direction."
(`UNRESOLVED` means Agent M's outcome is unknown after a retry and gates identically
to a confirmed `HOLD`; see [context/review-agents.md](../context/review-agents.md).)
Standalone /pr-fix runs (not invoked via /pr-review) have no `PREMISE_VERDICT`; omit
the line in that case.

---

## Configuration

Panel parameters used throughout this workflow. Edit these values to tune
model selection and review depth without touching the workflow logic.

```text
PANEL_MODEL:        google/gemini-2.5-pro-preview
PANEL_TIERED_LEVEL: 1
```

- `PANEL_MODEL`: the single model passed to `Skill("panel")` in flexible panel
  mode (a one-model roster) for targeted validations
- `PANEL_TIERED_LEVEL`: level (1/2/3) for `Skill("panel")` tiered-review calls;
  level 1 uses 3 free models (cap $0.50), level 2 adds economy models (6 total,
  cap $1.00), level 3 adds high-cost models (8 total, cap $10.00)

Both modes require `OPENROUTER_API_KEY`. If it is not set, degrade to
single-model verification with the `doubt-driven-development` skill and tag the
output `VERIFIED-SINGLE-MODEL` so downstream readers know decorrelation was not
achieved.

**Configuration drift flag (`PANEL_MODEL`).** The value above
(`google/gemini-2.5-pro-preview`) is a `-pro` variant, which conflicts with
standing guidance elsewhere in this project to avoid `-pro` models. It has not
been re-validated against the current OpenRouter roster and may no longer
resolve. Do not silently substitute a replacement model ID on the strength of
this note: an unverified guess that happens to look current fails silently at
call time, which is worse than a value flagged as stale. Before the next
invocation that depends on this line, check the live roster (PAL `listmodels`,
or `Skill("panel")`'s own listing) and update it to a currently-listed,
non-`-pro`, cross-vendor model; that substitution is a decision for whoever
runs the check, not something to resolve here by guessing.

---

## Step 0: Parse URL and fetch metadata

Extract owner, repo, and PR number from the URL:

```bash
PR_URL="$ARGUMENTS"
OWNER=$(echo "$PR_URL" | sed 's|https://github.com/||' | cut -d'/' -f1)
REPO=$(echo "$PR_URL" | sed 's|https://github.com/||' | cut -d'/' -f2)
PR_NUMBER=$(echo "$PR_URL" | grep -oE '[0-9]+$')
```

If values came from the calling pr-review workflow, skip parsing.

Fetch PR metadata via GitHub MCP `pull_request_read` method `get`:

```text
owner: OWNER, repo: REPO, pullNumber: PR_NUMBER
```

Store `HEAD_BRANCH`, `BASE_BRANCH`, `PR_TITLE`, `PR_BODY`.

Also fetch `mergeable`, `mergeStateStatus`, and `autoMergeRequest`:

```bash
gh pr view "$PR_NUMBER" --repo "$OWNER/$REPO" \
  --json mergeable,mergeStateStatus,autoMergeRequest
```

**Abort if: PR is closed, or metadata fetch fails.**

**Settle before evaluating (mandatory):** `mergeable` and `mergeStateStatus` are
computed asynchronously and commonly read `null` or `UNKNOWN` on a freshly opened
or freshly pushed PR. A single fetch is therefore not enough to apply the
precondition below. Poll until the field is settled, and treat an unsettled read
as "retry", never as "passed":

```bash
for i in $(seq 1 10); do
  MS=$(gh pr view "$PR_NUMBER" --repo "$OWNER/$REPO" --json mergeStateStatus \
    --jq '.mergeStateStatus // "UNKNOWN"')
  [ "$MS" != "UNKNOWN" ] && [ -n "$MS" ] && break
  sleep 3
done
```

If it is still unsettled after the loop, say so and stop; do not fall through to
Step 1 on an unknown value. This is the gap that made the precondition below
unenforceable: the only abort conditions were "PR is closed" and "metadata fetch
fails", so a `null` read silently proceeded.

**PR conflict precondition (mandatory):** If `mergeable` is `CONFLICTING` or
`mergeStateStatus` is `DIRTY` or `BEHIND`, do NOT proceed to Step 1. A
conflicted PR is not actionable for an automated fix workflow because
GitHub Actions does not reliably trigger workflow runs on conflicting PRs
(the `pull_request: synchronize` event fires, but required-check workflows
silently no-op, leaving the merge gate stuck even after fix commits land).

When a conflict is detected, surface it and ask the user how to resolve
before any fix work begins:

```text
PR #{N} has unresolved conflicts with the base branch ({BASE_BRANCH}).
GitHub Actions will not reliably re-trigger required checks on a
conflicting PR. Resolve before applying fixes:

1. Merge {BASE_BRANCH} into {HEAD_BRANCH} (creates a merge commit)
2. Rebase {HEAD_BRANCH} onto {BASE_BRANCH} (linear history, force-push)
3. Cancel /pr-fix; resolve conflicts manually first

Which option?
```

If the user picks 1 or 2, perform the resolution in the worktree (Step 3)
before continuing to Step 1 issue gathering. After resolution, push so the
PR shows `mergeable: MERGEABLE` before any fix commits.

**The branch refresh can itself be the remediation.** A class of findings is
state-dependent and clears on a fresh `synchronize` alone: stale CI results from a run
that predates a label or base change, label-timing races in jobs gated on
`github.event.pull_request.labels`, and orphaned/queued checks. For these, the BEHIND-
resolving rebase/update the precondition just performed IS the fix, and Steps 1-8 may
have nothing left to do. After pushing the refreshed tip, re-fetch CI status and
mergeStateStatus on the NEW head SHA before gathering or applying further fixes. If the
findings that motivated /pr-fix were stale-CI or label-timing-race class (greppable
signals: a failing check that is non-required, a job gated on
`github.event.pull_request.labels`, a check whose run SHA predates the latest label/base
event), verify whether the refresh already resolved them before hunting for code fixes.
Frame branch refresh as potentially-remediating, not solely as setup.

The merge or rebase commit that records the conflict resolution is subject
to the same `--no-verify` prohibition documented in Step 6. Run pre-commit
on the merge commit and fix anything it flags; do not skip hooks even when
the resolution kept HEAD's tree unchanged for the conflicting files.

**Rebase preference for conflict resolution:** When both rebase and merge are
options, prefer rebase. A rebase simultaneously resolves conflicts AND picks up
lockfile updates from base (resolving CVEs and dependency drift), whereas a merge
commit only resolves conflicts. The lockfile CVE and merge conflict often share the
same root cause (stale dependencies).

If the user picks 3, exit cleanly without modifying the PR.

**Auto-merge detection:** If `autoMergeRequest` is non-null, or if the repo
allows auto-merge (`gh api repos/{OWNER}/{REPO} --jq '.allow_auto_merge'`
returns `true`), set `AUTO_MERGE=true` and warn the user before entering the
Step 9 watch-and-refix loop:

```text
This PR is configured for auto-merge. The first all-green CI pass will merge it
immediately. New review findings that arrive after merge require a follow-up PR.

Proceed with the watch loop? (yes / disable auto-merge for this session)
```

If the user chooses "disable auto-merge":

```bash
gh pr merge --disable-auto "$PR_NUMBER" --repo "$OWNER/$REPO"
```

Set `AUTO_MERGE=false` and proceed normally.

---

## Step 1: Gather all issues (run sources in parallel)

Each source is independent. Launch them simultaneously.

### 1a. CI check failures

Fetches CI check-run failures via GitHub MCP `get_check_runs`, drills into the
failing job's failing step to reduce log noise, then classifies each failure
by check-name pattern into a fix strategy consumed by Step 4 Priority 1
("apply the fix strategy from the Step 1a table"). The full classification
table (25+ patterns from lint/format/type-check through GitGuardian secrets)
and the discursive diagnosis notes (harden-runner audit noise, auth-suspected
failures, workflow-load failures, wrong-ref fixes, and scanner exit codes) live
in the context file below.

A scanner invoked with a file-output flag (`osv-scanner --output=report.json`,
`trivy --output`, `bandit -o report.json`) writes findings to an artifact and
prints only a summary plus exit code to the log; see
[context/github-api-idioms.md](../context/github-api-idioms.md) ("Scanner exit
codes: a verdict, not a diagnosis") for the shared version of this rule.

**Full procedure (orchestrator runs this step; read when you reach it, not before):** [context/issue-gathering.md](../context/issue-gathering.md#1a-ci-check-failures)

### 1b. Review comments

Use GitHub MCP `pull_request_read` with these methods (page with `perPage: 100`):

- `get_review_comments`: inline review threads
- `get_reviews`: top-level review verdicts
- `get_comments`: conversation-level comments

For each item, record: author, body, file path, line, is_resolved,
is_outdated, thread/comment ID.

**Classify by author.** Copilot uses two different logins depending on what it
posted, and matching only one of them silently drops the other into the "Human"
bucket below, where it is triaged as a change request from a person. Review
*submissions* are authored by `copilot-pull-request-reviewer[bot]`; the *inline
comments* attached to that review are authored as bare `Copilot`, with no `[bot]`
suffix. Match both, case-insensitively, and match on substring rather than exact
equality so a future suffix change does not reopen the same gap:

- login matches `copilot` (covers `Copilot` and
  `copilot-pull-request-reviewer[bot]`) --> Copilot
- login matches `coderabbitai` (covers `coderabbitai[bot]`), or the body carries
  CodeRabbit markers --> CodeRabbit
- Contains `Generated with [Claude Code]` --> pr-review bot
- All others --> Human

The "All others --> Human" line is a catch-all, so any classifier gap fails
*quietly* into it rather than erroring. That is why the bot patterns above must
be permissive: an unmatched bot is not a visible failure, it is a mis-triage.

Which unresolved threads are actionable (change requests, Copilot/CodeRabbit
suggestions, bug reports) versus non-actionable (resolved threads, bot summary
walkthroughs, pure praise) is enumerated in the context file below.

**Full procedure (orchestrator runs this step; read when you reach it, not before):** [context/issue-gathering.md](../context/issue-gathering.md#1b-review-comments)

### 1c. SonarQube findings

**Abridged summary; `pr-review` Step 4 is authoritative.** The five steps below
are the happy path only. The full procedure lives in
`workflows/pr-review.md` Step 4 (substeps 4a through 4g) and covers cases this
summary omits, including the pre-flight configuration check, security hotspots,
and the Qlty gate. If the two ever disagree, `pr-review` Step 4 wins. Read it
rather than this list whenever detection does not succeed on the first attempt.

The five-step happy path (org detection, MCP-server routing, project-key
resolution, `search_sonar_issues_in_projects`, branch-issue fallback), the
token-discovery snippet, and the per-finding recording convention are in the
context file below.

A SonarQube MCP server that fails to connect must be recorded as
`SONAR_FINDINGS: unavailable`, never collapsed into zero findings; see
[context/github-api-idioms.md](../context/github-api-idioms.md) ("An
unreachable MCP server is not an empty result set") for the shared version of
this rule.

**Full procedure (orchestrator runs this step; read when you reach it, not before):** [context/issue-gathering.md](../context/issue-gathering.md#1c-sonarqube-findings)

### 1d. Codecov / coverage status

1. Check repo root for `codecov.yml` or `.codecov.yml`
2. Check CI check runs for "codecov" in the name
3. If present and failing: note coverage delta and affected files
4. If not configured: record "not configured", skip

### 1e. pr-review agent findings

If `FINDINGS` from the calling pr-review workflow exists in context,
incorporate directly (already scored and tiered).
If standalone invocation, this source is empty.

### 1f. Conversation comments (bot signals)

Fetch PR conversation-level comments for known bot patterns:

```bash
gh api repos/{OWNER}/{REPO}/issues/{PR_NUMBER}/comments \
  --jq '[.[] | select(.user.login | test("dependabot|renovate|coderabbitai")) | {author:.user.login, body:.body, created:.created_at}]'
```

Scan for actionable patterns:
- Dependabot/Renovate "A newer version of X exists": record as a Step 1a-class finding
- SonarCloud quality gate summary links: defer to Step 1c
- CodeRabbit rate-limit messages: note "CodeRabbit review pending; will surface in Step 8"

Record found signals as Step 1f findings, tagged by source.

---

## Step 2: Classify and present

Build the unified issue list. Present:

```text
PR Fix: {OWNER}/{REPO}#{PR_NUMBER}
Branch: {HEAD_BRANCH}

Issues found:

  CI Failures:        {N} ({list of failing check names})
  Review Comments:    {N} unresolved ({N_copilot} Copilot, {N_coderabbit} CodeRabbit, {N_human} human)
  SonarQube:          {N} findings
  Coverage:           {status or "not configured"}
  Agent Findings:     {N} from pr-review (if available)
  Bot Signals:        {N} from Step 1f (if any)

Tier coverage (from pr-review findings):
  Critical:           {N} (all addressed)
  Important:          {N} (all addressed)
  Suggested:          {N} (all addressed)
  Informational:      {N} (addressed if single-file, low-risk; otherwise skipped)

Fixability:
  Auto-fixable:       {N}
  Agent-evaluated:    {N} (assigned to specialized agents, not deferred)
  Human-only:         {N} (design debates, security policy decisions; listed at end)

Proceed? (yes / review details / cancel)
```

If the user asks to review details, expand each category.
Wait for confirmation before proceeding.

**Partition failing checks by ruleset required-contexts FIRST, and present required-first.**
When a PR is BLOCKED with many red checks, the merge gate is defined by the ruleset's
required status contexts, not by the count of red Xs; "required" and "red" are independent
axes. As an explicit first action in this step, fetch the branch ruleset's
`required_status_checks` contexts and partition the failing checks into required vs
non-required. Order the fix plan required-first: the single highest-leverage fix is usually
the one that clears a cascade-failing REQUIRED gate, while many reds are non-required noise.
This is the same required-vs-non-required tiering pr-review applies to CI findings; the same
partition must drive pr-fix prioritisation and the user-facing plan, not just the finding
tier.

**Classify each fix as code-changing vs GitHub-metadata-only** (PR title/body edits,
thread resolution, label changes, comment replies). Record
`HAS_CODE_FIXES = true` only if at least one fix touches a working-tree file. This gates
Step 3: a fix set that mutates no files needs no worktree.

**Shared-root-cause triage when many PRs are BLOCKED.** If this run is part of a fleet
where N>1 PRs are all BLOCKED with the same red signal, suspect shared infrastructure
before per-PR work: diff the branch-protection / ruleset required status-check contexts
against the contexts actually emitted on the PR head, and check whether the same failure
appears on the base branch. A never-reported required context sits pending forever and
blocks silently, while the visible red Xs may be stale orphaned contexts NOT in the
required set. Confirm with `gh api .../rulesets`, `gh pr view <n> --json statusCheckRollup`,
and a presence/state cross-check of each required context. Fixing the contexts on one
keystone PR often unblocks the fleet; only after ruling out shared infra should PRs be
treated individually.

## Step 3: Set up worktree

**Skip worktree creation entirely when `HAS_CODE_FIXES` is false** (metadata/
thread-resolution only). Apply the metadata fixes directly via `gh`/GraphQL and leave
`WORKTREE_PATH` unused; provisioning a checkout to edit nothing is pure overhead. Gate the
heavyweight isolation on the presence of the working-tree mutation it protects against.

Create an isolated worktree on the PR branch:

```bash
git fetch origin {HEAD_BRANCH}
git worktree add .worktrees/fix-pr{PR_NUMBER} {HEAD_BRANCH}
```

Record `WORKTREE_PATH=.worktrees/fix-pr{PR_NUMBER}`.

All file edits happen inside `WORKTREE_PATH`. Never touch the main working tree.

**Worktree-head vs PR-head precondition (mandatory).** `git worktree add {HEAD_BRANCH}`
checks out the LOCAL branch ref, which can be ahead of the origin PR head when the
author has unpushed local commits. A later rebase-and-force-push would then silently
publish those unreviewed commits to the PR under the banner of the fix. A workflow that
operates "on a PR" must treat the remote PR head as the source of truth, not the local
ref of the same name. Immediately after `git worktree add`:

```bash
git -C {WORKTREE_PATH} fetch origin {HEAD_BRANCH}
WT_HEAD=$(git -C {WORKTREE_PATH} rev-parse HEAD)
PR_HEAD=$(git -C {WORKTREE_PATH} rev-parse origin/{HEAD_BRANCH})
if [ "$WT_HEAD" != "$PR_HEAD" ]; then
  git -C {WORKTREE_PATH} log --oneline origin/{HEAD_BRANCH}..HEAD
fi
```

If they differ, surface the divergent commits and their diffs BEFORE any fix work, state
that a force-push will publish these previously-unpushed commits to the PR, and require
explicit confirmation. Prefer resetting the worktree to the fetched origin PR head
(`git -C {WORKTREE_PATH} reset --hard origin/{HEAD_BRANCH}`) when the goal is strictly to
fix reviewed findings; treat local-ahead commits as an opt-in addition the user
acknowledges.

**Error handling:**

- **Branch already in main working tree:** Before attempting `git worktree add`,
  check `git rev-parse --abbrev-ref HEAD`. If it equals `{HEAD_BRANCH}` AND the
  working tree is clean AND HEAD matches the PR head SHA: skip worktree creation
  and set `WORKTREE_PATH=.` (in-place mode). Log: "Branch already checked out in
  main tree; working in-place (isolation goal already met)."
- **If `.worktrees/fix-pr{PR_NUMBER}` already exists:** do NOT run
  `git worktree remove --force` on it unconditionally. In a clone where several
  sessions run concurrently, that directory may hold another session's
  uncommitted work, and `--force` discards it silently. Establish that it is
  abandoned and yours to remove first:

  ```bash
  # Is anything uncommitted in it?
  git -C ".worktrees/fix-pr{PR_NUMBER}" status --porcelain
  # Does it hold commits not reachable from the remote branch?
  git -C ".worktrees/fix-pr{PR_NUMBER}" log --oneline \
    "origin/{HEAD_BRANCH}..HEAD"
  ```

  If both are empty, remove it with a plain `git worktree remove` (no
  `--force`). If either is non-empty, stop and surface it to the user with the
  path and what it contains; another session probably owns it. Reach for
  `--force` only after the user says the contents are disposable.
- If branch not found: check that the branch exists on origin with `git fetch origin`
- If `fatal: '{HEAD_BRANCH}' is already used by worktree`: report the existing path
  (from `git worktree list --porcelain`) and offer: (1) use that worktree, (2)
  create a detached worktree at the head SHA (`git worktree add --detach`), or (3) abort.

**Lock file stabilisation (prevent hook false-failures):** After creating the worktree,
if both `pyproject.toml` and `uv.lock` are present, run `uv sync` in the worktree before
any pre-commit invocations:

```bash
if [ -f "{WORKTREE_PATH}/pyproject.toml" ] && [ -f "{WORKTREE_PATH}/uv.lock" ]; then
    (cd {WORKTREE_PATH} && uv sync --frozen 2>/dev/null || uv sync)
fi
```

A worktree created from a committed branch inherits a committed `uv.lock` that may lag
behind `pyproject.toml`. Pre-commit hooks using `entry: uv run <tool>` will regenerate
the lock file as a side effect and report "files were modified by this hook" -- a false
failure unrelated to the PR's changes. This one-time sync stabilises the lock before any
hooks fire.

**Sync with the project's extras when a repo-wide type-check hook is present.** A bare
`uv sync` installs only core deps. When the repo has a type-check hook configured
`pass_filenames: false` (it scans all of `src/` regardless of staged files) AND the typed
deps (numpy/torch/numba and similar) live in `[project.optional-dependencies]` extras,
that bare sync leaves the stubs uninstalled and basedpyright emits dozens of purely
environmental `reportUnknown*` errors that block an otherwise-clean commit. Grep
`.pre-commit-config.yaml` for `pass_filenames: false` type-check hooks before choosing sync
depth; if found (or if the project CLAUDE.md documents an extras requirement), sync with the
documented extras instead:

```bash
if grep -qE 'pass_filenames:\s*false' "{WORKTREE_PATH}/.pre-commit-config.yaml" 2>/dev/null; then
    (cd {WORKTREE_PATH} && uv sync --all-extras --frozen 2>/dev/null || uv sync --all-extras)
fi
```

A worktree's local gate only matches CI when its environment matches CI's; a tree synced
without the extras CI installs produces false-failures indistinguishable from real defects.

**Pin the interpreter to a CI-supported Python version.** A local gate predicts CI only when
BOTH the dependency set AND the interpreter version match CI. `uv` defaults to the newest
installed interpreter, which can exceed the project's CI matrix and silently break version-
sensitive tools (bandit, AST-based linters) on touched and untouched files alike,
manufacturing failures unrelated to the diff. For example, bandit pinned at 1.7.7 cannot
parse a 3.14 AST and crashes with exit 0 on every file, which would fail the `uv run bandit`
pre-commit hook (and `--no-verify` is prohibited). After lock-file stabilisation, determine
the CI matrix's max supported Python (from `.github/workflows/*` or the `requires-python`
upper bound) and, if `uv run python --version` in the worktree exceeds it, recreate the venv
pinned to a CI-supported version before any Step 5a gate or commit:

```bash
(cd {WORKTREE_PATH} && uv venv --python <ci-version> && uv sync)
```

**Edit precondition is path-specific (worktree vs main tree).** The Edit tool's
"file has been read" precondition keys on the exact absolute path, not on content. A
file Read earlier from the main tree (`/repo/README.md`) does NOT satisfy an Edit on
the worktree copy (`/repo/.worktrees/fix-prN/README.md`); the Edit rejects with "File
has not been read yet." Before editing ANY file inside the worktree, Read it from the
worktree path first, ideally with offset/limit near the insertion point. Never edit a
worktree file on the strength of having read its main-tree counterpart.

---

## Step 4: Execute fixes in priority order

Consumes the unified issue list from Step 2 and the worktree (`WORKTREE_PATH`)
from Step 3. Produces applied edits inside `WORKTREE_PATH`, grouped by the five
priority tiers below, ready for Step 5 verification. Work through issues in
this order: CI failures first, because they block merge and may cause
cascading issues.

1. **CI failures** ("Priority 1"): apply the fix strategy from the Step 1a
   table; verify locally with `uv tool run` (never `uv run`, which would trust
   the reviewed repo's own tool declarations and recreate the AG04 trust gap);
   defer test verification to Step 5a's confirm tier.
2. **SonarQube findings** ("Priority 2"): auto-fix mechanical patterns without
   prompting; for anything touching logic, security policy, or refactoring,
   validate the proposed fix with a `panel` flexible-mode call, then present it
   to the user for propose-and-confirm.
3. **Review comments** ("Priority 3"): apply the requested change at the root
   cause, even when that cause lives outside the file the comment was posted
   on; verify substantive, technical, and cosmetic claims before applying them
   (bots and agents can be confidently wrong); hand off whatever cannot be
   auto-fixed to a specialized agent, or mark it human-only only when no agent
   applies.
4. **Coverage gaps** ("Priority 4"): generate tests only when Codecov is
   actually failing on identifiable lines, never in response to a review
   comment alone; validate generated tests are not tautological before
   presenting them to the user.
5. **Agent findings from pr-review** ("Priority 5"): same category rules as
   Priority 3.

A cross-cutting editing constraint applies throughout: in a repo with a ruff
PostToolUse hook, a new import and its first usage must land in the same Edit
call, or the unused-import rule strips the import before the usage exists.

**Full procedure (orchestrator runs this step; read when you reach it, not before):** [context/fix-execution.md](../context/fix-execution.md)

---

## Step 5: Verify

Step 4's per-category verification commands (lines above) use `uv tool run`
to invoke ruff and basedpyright from the overseer's global tool environment.
Test verification is explicitly deferred from Step 4 to Step 5a's confirm
tier because `pytest` auto-imports `conftest.py` from the reviewed repo at
collection time. Step 5a is the final gate before commit: it re-runs the
static checkers in a single pass to confirm the worktree is in a clean
state, plus it presents the confirm-tier candidates (`pytest`, `pre-commit`,
`nox`, `tox`, `make`) for user confirmation.

If the worktree has PostToolUse ruff hooks configured, Step 5a's ruff
invocations re-trigger them. This is harmless but may produce redundant
log output.

The `uv tool run` isolation claim (default-tier commands resolve from
the overseer's global tool environment, not the reviewed repo's project
environment) depends on `uv tool run` semantics in uv >= 0.4. If `uv`
changes its tool isolation behavior in a future release, the trust claim
in this section must be re-validated. `#VERIFY uv tool run isolation
remains in effect when bumping the documented uv minimum version.`

### 5a. Local gate sequence

Two trust tiers gate what runs against the (untrusted) reviewed repo: a
**default tier** of static analyzers (`ruff format --check`, `ruff check`,
`basedpyright`, `bandit`) invoked via `uv tool run` from the overseer's global
tool environment, run without prompting; and a **confirm tier**
(`pytest`, `pre-commit run --all-files`, `nox`, `tox`, `make`) that executes
reviewed-repo code by design and requires the user to reply with the literal
word `yes` after reviewing an untrusted-content excerpt. A third branch,
**hard refuse**, fires for arbitrary shell scripts and indirection (`eval`,
`subprocess.*`, a `scripts/*.sh` launcher) and has no `yes` path at all.

Decisions the caller must make here: confirm or skip each detected
confirm-tier candidate individually (never bundle them into one prompt), and,
if the default gate is unavailable (no `pyproject.toml`, unhealthy `uv tool`
environment), choose between skipping Step 5a with a documented gap or
aborting `/pr-fix` outright.

The full trust-tier mechanics, the per-candidate confirmation sequence, the
indirection-guard regex set, the retry policy (up to 3 cycles, full sequence
only), the pre-existing-failure policy, and the defect-class rescoping check
for a BEHIND branch are in the context file below.

**Full procedure (orchestrator runs this step; read when you reach it, not before):** [context/fix-verification.md](../context/fix-verification.md#5a-local-gate-sequence)

### 5b. CI dry-run: validate GitHub Actions configs locally

After the default gate passes, statically validate `.github/workflows/*.yml`
against checks that only otherwise surface after pushing (wrong file paths,
missing extensions, bad action versions). The same default/confirm/hard-refuse
trust tiers from Step 5a apply: REUSE and shellcheck run without prompting;
`pip-audit` requires the literal `yes` confirmation; a project-named
compliance script (e.g. a FIPS check) is hard-refused. Checks that cannot run
locally at all (ClusterFuzzLite, SARIF-producing scanners, SonarCloud,
Codecov) are validated statically instead (file existence, path correctness,
config parses).

**Full procedure (orchestrator runs this step; read when you reach it, not before):** [context/fix-verification.md](../context/fix-verification.md#5b-ci-dry-run-validate-github-actions-configs-locally)

---

## Step 6: Commit and present options

Group fixes into logical commits using conventional commit format.
One concern per commit. Sign each: `git -C {WORKTREE_PATH} commit -S -m "..."`.

**New shebang scripts need the Git-tracked executable bit.** When staging a new file whose
first line is a shebang (`#!/`), set the executable bit in Git's index with
`git add --chmod=+x <file>`. Git tracks file mode separately from the filesystem: plain
`chmod +x` sets the working-tree bit but not Git's tracked mode, and the
`check-shebang-scripts-are-executable` pre-commit hook checks the tracked mode, so a
`chmod`-only fix passes locally yet fails in CI. The default-tier gate (ruff, basedpyright,
bandit) does not check this; only confirm-tier `pre-commit run --all-files` does.

**Staged-content byte-sanity check (run before committing).** A green test+lint+build is
NOT evidence a committed text file is byte-clean: an Edit can write a stray NUL byte (e.g.
where a space was intended) that `tsc`, eslint, vitest, and the production build all tolerate
silently, and a `grep -P '[^\x00-\x7F]'` misses it (a NUL is within 0x00-0x7F). Git's own
binary detection is the cheap reliable signal. After staging, run
`git -C {WORKTREE_PATH} diff --cached --numstat` and flag any known-text path that shows
`-  -` (binary), and/or `git diff --cached --stat` and flag any text path reported as
`Bin ... bytes`. Scan staged text files for NUL bytes before commit when either fires.

**Procedural git rule (mandatory):** Never invoke `git commit` with
`--no-verify` on any commit, including merge commits. The rule applies even
when the agent reasons that pre-commit "would have passed anyway" or that
the merge resolution kept HEAD's tree unchanged for the conflicting files.
If pre-commit fails, fix the underlying issue or ask the user before
proceeding; do not bypass. Merge commits with auto-merged content from the
base branch DO trigger hooks on the incoming changes, so skipping is rarely
a no-op even when it appears to be one. The only time `--no-verify` is
permitted is when the user has explicitly requested it for the current commit.

| Group | Type | Example message |
| --- | --- | --- |
| CI lint/format fixes | `fix(lint)` | `fix(lint): resolve ruff violations and format issues` |
| Shell script bugs | `fix(hooks)` | `fix(hooks): correct exit codes and stdin reading pattern` |
| SonarQube findings | `fix(quality)` | `fix(quality): add explicit returns, remove redundant exceptions` |
| Review comment fixes | `fix(review)` | `fix(review): address Copilot findings on PR #{N}` |
| Documentation fixes | `docs` | `docs: correct Python version and fix broken links` |
| Test additions | `test` | `test: add coverage for uncovered functions` |
| Config portability | `fix(config)` | `fix(config): replace hard-coded paths with portable alternatives` |
| Em-dash removal | `fix(writing)` | `fix(writing): replace em-dashes per project style rules` |

Present completion options:

```text
Fixes applied. {N_fixed} of {N_total} issues resolved.
{N_skipped} items require manual review.

Skipped (manual review needed):
- {item}: {reason}

Options:
1. Push, reply to review comments, and post PR summary
2. Push only (no PR interaction)
3. Keep worktree for manual review
4. Discard all fixes

Which option?
```

---

## Step 7: Rebase check and push

Before pushing in any option, check whether the base branch has diverged:

```bash
git -C {WORKTREE_PATH} fetch origin {BASE_BRANCH}
if ! git -C {WORKTREE_PATH} merge-base --is-ancestor \
    origin/{BASE_BRANCH} HEAD; then
  echo "Base branch has diverged since this branch was created."
fi
```

If diverged, present the user with options:

```text
Base branch ({BASE_BRANCH}) has new commits since this branch diverged.
Pushing without rebasing may cause merge conflicts later.

1. Rebase onto origin/{BASE_BRANCH} before pushing (recommended)
2. Push as-is (merge conflict risk)
3. Keep worktree for manual resolution

Which option?
```

If the user selects rebase: run `git -C {WORKTREE_PATH} rebase origin/{BASE_BRANCH}`.
If conflicts occur, report them and offer Option 3 (keep worktree).

**Linter/validator-snapshot commits go semantically obsolete when rebased past refactors.**
When the PR's diff is the output of a linter/validator/formatter snapshot (docstring sync,
type-hint backfill, import sort) AND the branch is BEHIND a base that refactored the same
symbols (renamed functions, consolidated helpers, new params), mechanical conflict
resolution is insufficient: taking either side leaves the validator failing because the
snapshot no longer matches the new signatures, and a clean `git rebase --continue` is a
false finish. The only trustworthy finish is to re-run the validator against the rebased
tree and fix the residuals. Offer "fresh from base + regenerate" as a first-class option
alongside rebase/merge: reset to base, re-apply only the non-generated change (e.g., the
config edit), and regenerate the tool's output against current base. A commit that encodes
a tool's output is a snapshot of code at one instant; re-running the tool is the only
verification the rebased result is correct.

**CI workflow identity conflict guard:** When resolving conflicts in
`.github/workflows/` files, classify each conflict. A conflict where BOTH sides
rewrote the `uses:` reusable-workflow reference or job `name:` field is a DESIGN
CONFLICT, not a mechanical merge. Both sides represent different CI designs, and
the correct resolution depends on which job names are listed as required-status-check
contexts in branch-protection. Neither side is automatically "more correct."

Stop and escalate:

```text
Conflict in {file}: both sides independently restructured the same CI gate.
Job names in workflow files define required status-check contexts -- auto-resolving
this could silently break or bypass a gate.

Which CI structure should apply? (show branch side / show main side / abort)
```

If rebase succeeds (no identity conflicts), continue with the selected push option.

**Conflict-free is not correct: verify semantically before trusting a clean resolution.**
Absence of `<<<<<<<` conflict markers after a merge or rebase is not evidence the result
is correct. Git resolves non-overlapping hunks automatically even when the surviving hunk
contradicts what the removed hunk intended, so a clean three-way merge can silently
reinstate lines a sibling PR deliberately removed. After any merge or rebase completes
without reported conflicts, re-read the changed regions against all three stages (ours,
theirs, and the merge base), not just against the absence of markers, and confirm the
result still reflects what each side intended rather than merely what git could
mechanically combine.

Two `--onto` recipes handle the cases a plain rebase or merge mishandles:

- **Stacked branch whose parent PR squash-merged:** a plain rebase onto the new base
  replays this branch's own commits alongside content the parent already landed under a
  different SHA, producing phantom add/add conflicts on every duplicate commit. Rebase
  only the branch's unique range instead: `git rebase --onto origin/{BASE_BRANCH}
  {OLD_BASE_TIP} {HEAD_BRANCH}`, where `{OLD_BASE_TIP}` is the last commit shared with the
  parent branch before it diverged. Duplicate commits become empty and auto-drop; the
  genuinely new work applies cleanly.
- **Branch with no shared ancestry to the current base at all** (`git merge-base
  --is-ancestor` finds nothing, typically after a squash-merged sibling): ahead/behind
  commit counts are meaningless across a disjoint history, so a direct diff against
  `origin/{BASE_BRANCH}` is the only reliable check. Classify each differing file by
  direction: branch-ahead is a keep candidate, branch-behind is noise the rebase must not
  reintroduce.

**Re-verify branch ownership immediately before every mutating step, not once at
worktree setup.** Step 3's worktree-head vs PR-head check is a snapshot taken at creation
time; a concurrent session, the PR author, or a bot can push to the same branch at any
point during Steps 4 through 8. Re-fetch `origin/{HEAD_BRANCH}` and diff it against the
worktree's recorded base immediately before each of: applying fixes (Step 4), committing
(Step 6), and pushing (below), not only once at the start. A rejected push is evidence of
a live concurrent writer, not evidence the PR was superseded or abandoned; treat it as a
signal to pause and diff the new remote commits against the fix already in hand, never as
license to force past it.

**Force-push safety: `--force-with-lease` alone is not sufficient.** The lease compares
against the *local* remote-tracking ref (`refs/remotes/origin/{HEAD_BRANCH}`), not against
live remote state. If that ref was never fetched in the current worktree (only
`{BASE_BRANCH}` was fetched, which is exactly what the rebase check above does), the lease
is computed against stale or absent data and passes even though the real remote has moved.
This is not theoretical: on this repo, a `--force-with-lease` push destroyed a concurrent
session's review-fix commit and merge commit on PR #288 (2026-08-03) for this exact
reason. The corrected sequence has two mandatory parts, and the first is load-bearing:

1. `git fetch origin {HEAD_BRANCH}` (the branch itself, immediately before the push, not
   the earlier `{BASE_BRANCH}` fetch from the rebase check above) so the lease is computed
   against current remote state; then `--force-with-lease`, never raw `--force`.
2. Before force-pushing, enumerate other worktrees on the same branch
   (`git worktree list`) and check each for unpushed commits
   (`git -C <path> log --oneline origin/{HEAD_BRANCH}..HEAD`). If any hold unpushed
   work, stop and surface it; do not force-push over a session that has not published yet.

---

## Step 8: Execute chosen option

### Option 1: Push, reply, and summarize

**Push:**

```bash
git -C {WORKTREE_PATH} push origin {HEAD_BRANCH}
```

**After push, check PR state when AUTO_MERGE=true:**

```bash
gh pr view "$PR_NUMBER" --repo "$OWNER/$REPO" --json state --jq '.state'
```

If `state == "MERGED"`: the PR auto-merged before new findings could be addressed.
Do NOT push again (a post-merge push re-creates the deleted branch as a dangling
branch). Surface any in-flight or staged fixes as a follow-up PR and stop.

**Reply to all threads:**

For every open finding in the unified issue list, whether fixed, deferred, or declined,
post a reply to its GitHub thread using the dedicated review-comment replies endpoint:

```bash
gh api repos/{OWNER}/{REPO}/pulls/{PR_NUMBER}/comments/{comment_id}/replies \
  -X POST -f body="{reply text}"
```

**Build a finding-id to comment-id map first; never carry one `comment_id` across
findings.** When batch-replying to several threads in one block, a reused or last-known id
silently attaches a correct reply to the wrong thread (a decline rationale landing on an
unrelated finding), which is harder to notice than an outright failure. Resolve each
finding's `comment_id` from the source of truth (one lookup by path+line) immediately
before its own write, post against that mapped id, and after posting re-read each thread to
confirm the reply landed under the intended comment.

Use this form, not `pulls/{n}/comments -X POST -f in_reply_to={id}`: the latter fails 422
because `-f` sends `in_reply_to` as a string and the endpoint's oneOf schema rejects it.
The `/replies` endpoint takes only a `body` field and works for every thread. (The GitHub
MCP `add_pull_request_review_comment` method is an equivalent if available, but the
`gh api` call above is the confirmed-working form.)

If you instead post against the create-review-comment endpoint, the threading field is
`in_reply_to` (an INTEGER, pass with `-F in_reply_to="$comment_id"`), NOT `in_reply_to_id`:
a 422 with "`in_reply_to_id` is not a permitted key" means the field NAME is wrong, not the
value. GitHub's reply-threading key names are inconsistent across endpoint families (the
create-review-comment endpoint uses `in_reply_to`; some other APIs use `reply_to_id`), so
verify the exact parameter name and type (`-f` string vs `-F` integer) against the specific
endpoint's schema before a batch of reply calls.

| Outcome | Reply format |
| --- | --- |
| Fixed | `Fixed in {commit SHA}: {one sentence description of what changed}` |
| Deferred | `Deferred: {reason}. Tracked in {ticket or follow-up issue number}.` |
| Declined | `Declined: {reason}. This is intentional because {explanation}.` |

Never leave a thread without a reply. Reviewers must be able to mark threads resolved
without chasing context.

Mark addressed review threads as resolved via GitHub MCP if the server supports
a resolve method (method name varies by version; check server docs).

**Post summary comment** via GitHub MCP `add_issue_comment`:

```markdown
### PR Fix Summary

Addressed {N} findings:

**CI Fixes**: {bullet list}
**Review Comments**: {bullet list with thread refs}
**SonarQube**: {bullet list}

**Remaining (manual review needed)**:
- {items with reasons}

Pre-commit passing locally. CI re-run triggered by push.
```

**Continue to Step 9 (watch-and-refix loop).**

### Option 2: Push only

```bash
git -C {WORKTREE_PATH} push origin {HEAD_BRANCH}
```

**After push, check PR state when AUTO_MERGE=true** (same check as Option 1 above).

**Continue to Step 9 (watch-and-refix loop).**

### Option 3: Keep worktree

Report:

```text
Worktree preserved at {WORKTREE_PATH} on branch {HEAD_BRANCH}.
Push when ready: git -C {WORKTREE_PATH} push origin {HEAD_BRANCH}
```

Do not clean up. Skip Step 9.

### Option 4: Discard

Confirm: ask the user to type "discard". If confirmed:

```bash
git worktree remove --force {WORKTREE_PATH}
```

Do not delete `{HEAD_BRANCH}` itself. Skip Step 9.

---

## Step 9: Watch-and-refix loop

After pushing (Options 1 or 2), enter a bounded watch loop that monitors CI
and review bots. This eliminates the manual "push, wait, come back, re-run"
cycle that dominated both PR #20 and dna#1.

### Phase A: Wait for CI + reviewer stabilization (up to 10 minutes)

Poll every 60 seconds, anchored to `PUSH_SHA` (never `gh pr checks`, which can
report stale pre-push data): CI check-runs on the new SHA, review-comment
count stabilization, and (when `AUTO_MERGE=true`) PR state. Exit on all-green
plus a debounce (2 minutes elapsed or two consecutive all-terminal polls), or
after 10 minutes. `mergeStateStatus`/`mergeable` are used only in the negative
direction here, never as the confirming signal; the authoritative green
signal is direct check-run data plus `mergeable_state == "clean"`.

### Phase B: Assess results

Re-fetch and classify comments using the same methods and author-classification
rules as Step 1b ([context/issue-gathering.md](../context/issue-gathering.md#1b-review-comments)),
not a separate re-derivation; Copilot's dual-login pattern and the other bot rules
apply identically to a post-push comment batch. Filter stale comments (an older
`commit_id` whose cited content no longer exists at HEAD) out of the new-findings
count before classifying the outcome.
A hard-FAILED check is not automatically a merge blocker: it is advisory when
non-required and `mergeStateStatus` is `UNSTABLE` (not `BLOCKED`) with
`mergeable: MERGEABLE`.

**Green-but-BLOCKED: distinguish the cause before acting.** "All checks green" is
necessary but not sufficient for mergeability. Use `mergeStateStatus` here only in
the negative direction, consistent with Phase A above: a settled `BLOCKED` is
grounds to stop and diagnose, but it is never the signal that confirms the branch
is ready. Phase A's rule stands, this does not override it. BLOCKED has multiple
independent causes that each need a different, non-code action. When CI is all
green AND there are no new non-stale comments AND `mergeStateStatus` is BLOCKED:

- **Unresolved review threads** (branch protection enforces conversation resolution):
  check `reviewThreads.nodes` for `isResolved == false` whose findings are already
  addressed, and resolve them via the `resolveReviewThread` GraphQL mutation (already
  implied by Step 8). This clears BLOCKED -> CLEAN without any code change.
- **Phantom or name-mismatched required checks** (a required context that is never
  reported sits pending forever): clears by fixing branch protection / the workflow job
  name, not by resolving threads.

Neither cause is a re-fix cycle. Identify which one applies before acting.

**PR lifecycle sequencing changes what "all-green" means after a push.** Three
sequencing effects, none of them a code defect, can distort the Phase A/B read:

- **A metadata edit right after a push cancels in-flight checks.** If Step 8 Option 1
  edits the PR body or title shortly after pushing, the edit fires its own
  `pull_request: edited` event; workflows with concurrency groups cancel their in-flight
  run from the push event and re-run under the edit event. The settled rollup then
  carries CANCELLED entries alongside SUCCESS re-runs of the same check name, and a naive
  failure count reads CANCELLED as a failure. Before treating any CANCELLED conclusion as
  a failure, look for a same-named check with a later start time, and corroborate with
  `mergeStateStatus == CLEAN`, which does not care about superseded rows. Where practical,
  finish body/title edits before the push rather than after, to avoid generating the
  duplicate rows at all.
- **A stacked PR's base can retarget mid-run.** When a stacked PR's parent merges,
  GitHub retargets the child to the grandparent via an `edited` event. Many
  `pull_request:` trigger lists cover only `[opened, synchronize, reopened]` and never
  fire on `edited`, so required contexts can go completely unreported on the retargeted
  head while unrelated checks stay green. Whenever `BASE_BRANCH` changed since Step 0,
  confirm every required context actually ran on the *current* head SHA, not just that
  the visible rollup looks green.
- **Squash-merge breaks ancestry-based "is this merged" checks.** If any cleanup or
  supersession judgment in this loop needs to know whether a branch's work already
  landed, `git branch --merged`, `git cherry`, and ahead/behind counts all false-negative
  under squash-merge, because the merged commit shares no ancestry with the original
  branch commits. Use the PR's own merge state (`gh pr view --json state,mergedAt`) or a
  content diff against the target, never commit-graph ancestry, to decide.

### Phase C: Automatic re-fix pass (up to 2 cycles)

If Phase B indicates issues, present a delta summary and, on confirmation,
apply fixes (Step 4 rules), verify (Step 5), commit (Step 6), push, and
re-enter Phase A. Maximum 2 automatic cycles; after that, run a `panel`
tiered-review stuck-loop diagnosis and present its `can_retry` verdict as the
exit option. Clean up the worktree only once the loop completes all-green, or
the user explicitly discards.

**Full procedure (orchestrator runs this step; read when you reach it, not before):** [context/watch-refix-loop.md](../context/watch-refix-loop.md)

---

## Error Handling

| Situation | Action |
| --- | --- |
| `gh` / GitHub MCP not authenticated | Stop. Print auth instructions. |
| PR not found or closed | Stop with clear message. |
| Worktree already exists | Do NOT blanket `--force` remove; another session may own it. Follow the guarded check in Step 3 (uncommitted changes and unpushed commits both empty before a plain `git worktree remove`; `--force` only after the user confirms it is disposable). |
| Pre-commit fails after 3 attempts | Report failures, ask commit anyway or stop. |
| Finding cannot be auto-fixed | Assign to the appropriate specialized agent (see Priority 3 agent table in [context/fix-execution.md](../context/fix-execution.md)). Mark "human-only" only when no agent applies. |
| Push rejected (protected/diverged) | Report error. Offer Option 3 (keep worktree). |
| SonarQube MCP unreachable | Log "SonarQube: MCP offline", continue without. |
| No Codecov configured | Log "Coverage: not configured", continue. |
| GitGuardian secret detected | Alert user immediately, never auto-fix. |
| PR merged by auto-merge between push and Phase A check (see [context/watch-refix-loop.md](../context/watch-refix-loop.md)) | Surface staged fixes as a follow-up PR; do not push to merged branch. |
| `gh pr create` denied by permission gate | Fallback: `gh api repos/{OWNER}/{REPO}/pulls -X POST --field title=... --field head=... --field base=...` |
