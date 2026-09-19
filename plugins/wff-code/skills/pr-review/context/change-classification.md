# Change classification detail

This covers the detailed procedure for Step 3 (Classify Changes) of
`workflows/pr-review.md`: the signal table used to decide which review
agents activate, docs-only and lockfile-only fast paths, config/infra
behavioral-guarantee verification, reusable-workflow ref reachability, size
classification, and file rename / path-boundary detection. The spine keeps
the `## Step 3` heading with a short orchestration stub; the full procedure
lives here.

---


Analyze `CHANGED_FILES` and the first 50 lines of `PR_DIFF` to classify:

| Signal | Agent(s) to Activate |
| ------ | -------------------- |
| `.py` files present | code-reviewer, silent-failure-hunter |
| `test_*.py` or `*_test.py` or `tests/` path | pr-test-analyzer |
| New `class` definitions or `TypeAlias` in diff | type-design-analyzer |
| `try:` / `except` / `raise` changes in diff | silent-failure-hunter (ensure) |
| Docstrings or `#` comment lines changed | comment-analyzer |
| `.sh` / `.bash` files present | code-reviewer (shell mode) |
| `.yml` / `.yaml` / `.json` / `.toml` / `.cfg` only | code-reviewer (config mode) |
| `.md` / `.rst` / `.txt` only | comment-analyzer (plus the always-on code-reviewer); skip Agent C and Agent D |
| `uses: anthropics/claude-code-action` or another autonomous-agent action in a workflow file | Agent I (LLM-agent-in-CI lens, see below) |

**Always active regardless of content:**

- `code-reviewer` (CLAUDE.md compliance + bugs)
- `git-history-agent` (blame + history context on modified files) -- **skip for docs-only PRs**
- `prior-pr-agent` (past review comments on same files) -- **skip for docs-only PRs**
- `premise-gate` (Agent M: change appropriateness + regression + collision)

Docs-only definition: every changed file has a `.md`, `.rst`, or `.txt` extension. A single
non-doc file in the diff (e.g., a config change alongside a README update) makes the PR
non-docs-only and restores Agents C and D.

**Generated-lockfile-only PRs (match review effort to the artifact).**
When `CHANGED_FILES` is exactly one generated lockfile (`uv.lock`, `poetry.lock`,
`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, etc.), the diff is machine-generated:
its defects live in the resolved version set and the PR description's accuracy, not in
diff hunks. Skip the hand-written-code agent battery (Agents B, E, F, G, H, K, L) and run
only:

- a **dependency-delta check**: parse name/version pairs from the lockfile diff and flag
  any major or minor bumps against the PR description's claims (Renovate's boilerplate
  "patch only / no breaking changes" is frequently false; a major bump can still be valid
  when direct deps use `>=` lower bounds and the full CI matrix passed, but it must be
  surfaced, not assumed);
- confirmation that the **dependency-security CI checks** (Dependency Review, Socket,
  Trivy, SonarCloud) are green.

Agents A (CLAUDE.md), C, D, J, and M still apply if not skipped by the
docs-only rule.

**Trivial-change fast path (scale effort to the analyzable surface, not just line count).**
When the diff is a single file (or all files share one config/data extension) AND total
changed lines are <= 30 AND there is no history or prior-PR surface (a brand-new file),
collapse to: config-mode `code-reviewer` + Agent J (PR-desc-vs-diff) + a security/secrets
scan + the Step 8 bot-finding harvest. Skip git-history (Agent C), prior-PR (Agent D), and
the bug/type/test/perf agents (B, H, G, K), and skip Step 7b Critical-validation when zero
Critical findings exist. This scaling is EXPECTED, not a coverage failure: a brand-new
single config file has near-zero surface for history, type, test, and performance analysis,
so the "report everything / do not dismiss as trivial" instruction must not be read as
"spawn every agent." Agent M (premise) and Agent A still apply.

**Config/infra files encode behavioral guarantees, not just syntax.** For config-mode PRs
(CI workflows, dependabot/renovate, Docker, k8s manifests), syntax validity is necessary
but not sufficient. For each behavioral guarantee asserted in the PR body or config
comments, verify the configured option's DOCUMENTED behavior supports the claim (fetch the
tool's docs when uncertain), and where a live setting governs the guarantee, query it
(e.g., `gh api` repo settings) to confirm the invariant currently holds. Emit an Important
finding when the guarantee depends on an out-of-file setting the change does not document.
Example: `open-pull-requests-limit: 0` does not govern Dependabot security-update PRs (they
use a separate internal limit), so a "sole PR-opener" guarantee also depends on
`automated-security-fixes` being disabled, which is invisible in the diff. Treat
unverifiable behavioral claims about tool semantics like unverifiable quantitative claims:
confirm or flag, never assume.

**Reusable-workflow ref reachability (workflow files present).** For each
`uses: <owner>/<repo>/...@<sha>` cross-repo reusable reference, verify the SHA is reachable
from some ref that will persist, not merely that it currently resolves:

```bash
gh api "repos/<owner>/<repo>/compare/<sha>...<default>" --jq '.status'
```

`diverged` alone is NOT proof of orphaning: it is also the normal result for a valid commit
on an active feature branch that has unique commits on both sides of the comparison (the
branch is ahead of default in its own commits and behind in default's later commits). Do not
flag on `diverged` by itself. The status that DOES prove safety is `ahead` or `identical`:
either means `<sha>` is an ancestor of (or equal to) the default branch, so it is part of
permanent history and can never be orphaned by a branch deletion. Only when the status is
`diverged` or `behind` (sha not reachable from default) does the pin need a second check,
since neither status distinguishes "still a live branch tip" from "reachable from no ref at
all":

```bash
gh api "repos/<owner>/<repo>/commits/<sha>/branches-where-head" --jq 'length'
```

A nonzero result means `<sha>` is currently the tip of a live branch, so the pin is safe for
now (though it depends on that branch surviving, unlike a default-branch ancestor). A zero
result means the SHA is not the head of any existing branch and is not reachable from
default either; this is the genuine orphan signal (commonly a PR-branch SHA the Actions
resolver refuses once the branch has been deleted, or the object has already been garbage
collected). Note `contents?ref=<sha>` still serves the file for a dangling commit until GC
actually runs, so a file-existence check alone gives false confidence; use the two checks
above instead. Only emit the finding when BOTH the ancestor check and the branch-tip check
come back negative:

```text
[Important] Workflow: reusable ref @<sha> is not reachable from <repo> default branch; it
will fail to resolve once the source branch is deleted (e.g., after squash-merge). Re-pin to
a reachable SHA.
```

A passing CI check on the PR head is NOT sufficient evidence that a pinned cross-repo ref is
durable: the check passes only until the orphaning event happens. Review the durability of
external references, not just their current resolvability.

**Size classification:**

- Small: < 100 lines changed
- Medium: 100–500 lines changed
- Large: > 500 lines changed (see large-PR handling strategy at the top of Step 5)

**File rename / path-boundary detection:**

After size classification, scan `CHANGED_FILES` for renames or moves. Use the REST
`pulls/{n}/files` endpoint, which exposes `previous_filename` for renamed files:

```bash
gh api repos/"$OWNER"/"$REPO"/pulls/"$PR_NUMBER"/files --paginate \
  --jq '.[] | select(.status=="renamed") | {old: .previous_filename, new: .filename}'
```

Note: `gh pr view --json files` does not expose `previous_filename`, and the GraphQL
`previousFilename` field on `PullRequestChangedFile` was removed from GitHub's schema
(a query using it errors with "Field 'previousFilename' doesn't exist"). The REST
endpoint above is the authoritative source.

For any rename where the source and destination top-level path segments differ (e.g.,
`scripts/` to `src/`, `utils/` to `lib/`), emit an Important finding immediately
-- before spawning agents:

```text
[Important] PathBoundary: {old_path} moved to {new_path}. Destination-path quality
gates (darglint/pydoclint, interrogate, ruff per-file-ignores in pyproject) now apply to the
WHOLE file, not just the diff lines. Pre-commit's changed-files scoping will NOT
surface violations the move newly exposed until the next unrelated edit to that file.
```

Include the moved file path in the CHANGED_FILES list for agents B, F, G, and K so
they read full file context, not just the diff hunk (these are the four agents that
receive `CONTEXT_FILES`; see `review-agents.md`'s File context fetch section. Agent I,
Security, works from the diff alone and is not part of this set).
