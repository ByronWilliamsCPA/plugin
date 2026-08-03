# PR Review Workflow

Comprehensive pull request review orchestrated from a GitHub PR URL.
No local checkout. All context fetched via `gh` CLI and SonarQube MCP.

## Input

`$ARGUMENTS` contains the GitHub PR URL, e.g.:
`https://github.com/owner/repo/pull/123`

If `$ARGUMENTS` is empty, check if `gh pr view` resolves a PR for the current
branch. If neither works, ask the user for the PR URL before proceeding.

---

## Configuration

Model-validation parameters used throughout this workflow. Edit these values to tune
model selection and consensus depth without touching the workflow logic.

```text
PANEL_MODELS:          ["google/gemini-2.5-pro-preview", "openai/gpt-4o"]
CONSENSUS_LEVEL:       1
PREMISE_MERGED_PR_LOOKBACK:   10
PREMISE_STALENESS_HOLD_DAYS:  14
```

- `PANEL_MODELS`: model list passed to `Skill("panel")` in flexible panel mode
  for Agent L (the engine's `--models` argument). Precondition:
  `OPENROUTER_API_KEY` must be set; if it is not, skip Agent L and note the gap.
- `CONSENSUS_LEVEL`: level (1/2/3) for the `/panel` skill engine used in Step 7b;
  level 1 uses 3 free models (cap $0.50), level 2 adds economy models (6 total, cap
  $1.00), level 3 adds high-cost models (8 total, cap $10.00)
- `PREMISE_MERGED_PR_LOOKBACK`: number of recently merged PRs scanned for file and
  symbol overlap in Step 2e
- `PREMISE_STALENESS_HOLD_DAYS`: branch age in days above which staleness biases
  Agent M toward a HOLD verdict on a confirmed regression

Step 7b cross-model validation runs through the `/panel` skill's CLI engine
(`.claude/skills/panel/scripts/consensus_cli.py`), not PAL `tiered_consensus`. The
PAL multi-step protocol reliably returned setup-only messages without verdicts in this
step (observed repeatedly), so it was replaced with the one-shot consensus engine, which
returns model responses and counts in a single `run` call.

---

## Step 0: Parse URL

Extract owner, repo, and PR number from the URL:

```bash
PR_URL="$ARGUMENTS"
CLEAN_URL=$(echo "$PR_URL" | sed 's|[?#].*||' | sed 's|/\+$||')
OWNER=$(echo "$CLEAN_URL" | cut -d'/' -f4)
REPO=$(echo "$CLEAN_URL" | cut -d'/' -f5)
PR_NUMBER=$(echo "$CLEAN_URL" | cut -d'/' -f7)
```

Echo the resolved values for verification:

```text
Resolved: {OWNER}/{REPO}#{PR_NUMBER}
```

If any variable is empty, stop and report: "Could not parse PR URL: {PR_URL}. Expected
format: `https://github.com/owner/repo/pull/123`"

---

### Step 1: Confirm GitHub Copilot Review is queued

Copilot is enrolled as an automatic reviewer via the `copilot_code_review`
rule in the org ruleset (`<ORG>-default-branch-baseline` in both
ByronWilliamsCPA and williaby). It is requested when the PR opens.
No API call from this workflow is needed.

Verify it landed (one-line, non-blocking). Treat "requested OR already-submitted" as
success: a reviewer that has already submitted is removed from `requested_reviewers` and
moves to `/reviews`, so checking only the pending queue false-negatives on a
fast-reviewing or previously-pushed PR.

```bash
if gh api repos/"$OWNER"/"$REPO"/pulls/"$PR_NUMBER" \
     --jq '.requested_reviewers[].login' | grep -q copilot-pull-request-reviewer; then
  echo "Copilot: ruleset-requested OK"
elif [ "$(gh api repos/"$OWNER"/"$REPO"/pulls/"$PR_NUMBER"/reviews \
     --jq '[.[] | select(.user.login=="copilot-pull-request-reviewer[bot]")] | length')" -gt 0 ]; then
  echo "Copilot: already reviewed (submission present)"
else
  echo "Copilot: NOT requested -- verify copilot_code_review rule in org ruleset"
fi
```

Only the final branch (neither pending nor submitted) indicates a real ruleset
misconfiguration. If that branch fires, the `copilot_code_review` rule is missing or
disabled. Re-apply via:

```bash
uv run python scripts/setup_org_rulesets.py --org {ORG} \
  --body docs/reference/org-rulesets/{ORG}-universal.json --enforcement active
```

Do not block the rest of this workflow on the result.

---

## Step 2: Fetch PR Metadata

```bash
gh pr view "$PR_NUMBER" --repo "$OWNER/$REPO" \
  --json title,body,state,isDraft,labels,baseRefName,headRefName,headRefOid,author,number,mergeStateStatus
```

**Eligibility check (Haiku agent):**
Abort with a clear message if:

- `state` is `CLOSED`
- `isDraft` is `true` (note it in the report header but continue; drafts can
  be reviewed, user explicitly requested it)

```bash
# Fetch the full diff
gh pr diff "$PR_NUMBER" --repo "$OWNER/$REPO"

# Fetch file list with patch status
gh pr view "$PR_NUMBER" --repo "$OWNER/$REPO" --json files
```

Store:

- `PR_TITLE`: PR title
- `PR_BODY`: PR description
- `BASE_BRANCH`: baseRefName
- `HEAD_BRANCH`: headRefName
- `MERGE_STATE`: mergeStateStatus
- `HEAD_SHA`: headRefOid (PR head commit SHA; required by later steps for
  SHA-anchored file fetches and report links)
- `PR_DIFF`: full unified diff text
- `CHANGED_FILES`: list of file paths from the files JSON

**mergeStateStatus is computed lazily.** GitHub often returns `UNKNOWN` immediately
after a PR is loaded (the value is not yet computed, not a clean state). Step 2c
branches on `MERGE_STATE`, so an `UNKNOWN` read there silently skips the base-branch
lookup and can misclassify pre-existing base failures as PR-introduced. If
`MERGE_STATE` is `UNKNOWN`, wait 5 seconds and re-fetch once. If it is still `UNKNOWN`
after the retry, set `MERGE_STATE=BEHIND` conservatively (so the base-branch lookup
runs) and add to the report header:
**mergeStateStatus: UNKNOWN; branch-divergence attribution may be inaccurate.**

### 2c. CI status

> Note: `gh pr checks --json` uses `state` and `link`, NOT `status`, `conclusion`, or `detailsUrl`; those are REST API field names. Passing the wrong names causes "Unknown JSON field" errors.

```bash
gh pr checks "$PR_NUMBER" --repo "$OWNER/$REPO" \
  --json name,state,description,link \
  --jq '.[] | {name, state, description, link}'
```

Store as `CI_CHECKS`. For any check where `state` is not `SUCCESS` and not
`PENDING` (PENDING means in-progress; skip it), classify each failing check
by branch state before emitting.

**Required-vs-non-required tiering (decide tier before branch-state attribution).**
A failing check is a fact; whether it BLOCKS merge is a separate fact, and the tier
should follow the second. Before assigning a tier, determine whether the failing check
is a required status context. A check failing on an `UNSTABLE` (mergeable) PR is
non-required and does not block merge; only `BLOCKED`, or membership in
branch-protection `required_status_checks`, indicates a gate that does. Fetch the
required set once:

```bash
REQUIRED=$(gh api "repos/$OWNER/$REPO/branches/$BASE_BRANCH/protection/required_status_checks/contexts" \
  2>/dev/null | jq -r '.[]' || gh api "repos/$OWNER/$REPO/rulesets" 2>/dev/null | jq -r '..|.required_status_checks?//empty' )
```

- Failing check IS in the required set, OR `MERGE_STATE` is `BLOCKED`: tier it per the
  branch-state rules below (Critical is in play).
- Failing check is NOT required and `MERGE_STATE` is `UNSTABLE`: emit `[Important]` with
  the annotation "non-required, does not block merge" plus the check's own remediation
  hint. Do not emit BUILD FAILING for a non-required check. Rigidly labelling a trivially
  remediable non-required check (e.g., a non-required Documentation Links or spell-check
  gate) as Critical overstates impact and pushes the user toward unnecessary code changes.

For each failing check in `CI_CHECKS`:

- If `MERGE_STATE` is not `BEHIND`: emit at the tier set above; divergence attribution does not apply. No base-branch lookup is needed.
- If `MERGE_STATE` is `BEHIND`: a CI failure may originate in the diverged base history rather than in the PR's diff. Fetch the base branch's check results to distinguish the two cases:

  ```bash
  BASE_SHA=$(gh api repos/"$OWNER"/"$REPO"/branches/"$BASE_BRANCH" \
    --jq '.commit.sha')
  # The check-runs endpoint is paginated (default 30/page). Use --paginate
  # plus per_page=100 so repos with many checks return the full set; without
  # this, BASE_CHECKS is truncated and a failure present on base may be
  # misclassified as PR-introduced. --paginate emits each page as a
  # separate JSON document; jq -s slurps them and flattens check_runs
  # across all pages.
  BASE_CHECKS=$(gh api --paginate \
    "repos/$OWNER/$REPO/commits/$BASE_SHA/check-runs?per_page=100" \
    | jq -s '[.[] | .check_runs[] | {name: .name, conclusion: .conclusion}]')
  ```

  Look up the failing check name in `BASE_CHECKS`:
  - Fails on base too: emit `[Critical - pre-existing, rebase needed]`; the fix is rebase, not a code change.
  - Passes on base (or absent from base): apply the transient-infrastructure test below before emitting `[Critical - PR-introduced]`.

**Transient-infrastructure test (third category; run for any check that "passes on base").**
Pass/fail topology has three causes, not two: yours, pre-existing, and an infrastructure
flake unrelated to either branch. Before labelling a "passes on base" failure
PR-introduced, grep the failed run log for infrastructure signatures:

```bash
gh run view {RUN_ID} --repo "$OWNER/$REPO" --log \
  | grep -iE "requires authentication|httperror: 5[0-9][0-9]|rate limit|could not provision|runner.*offline|attestation.*verify" \
  | head -5
```

- Log matches an infra signature, or the conclusion is `CANCELLED` (collateral cancel):
  emit `[Critical - likely transient, rerun]` with the matched evidence line. The
  remediation is a re-run, not a code change. A docs-only or config-only diff that
  fails a code-analysis check (CodeQL, security-analysis) is a strong tell for this
  class, since such a diff cannot cause that failure.
- No infra signature and the log points at the diff: emit `[Critical - PR-introduced]`;
  the fix is in the PR's diff.

A failure that passes on base but red on the PR is PR-caused regardless of whether the
check is a *required* status context: required-context-green is necessary but not
sufficient. Pin-bump PRs (Renovate/Dependabot) that bump a reusable-workflow or action
SHA are the common offender, because the one-line SHA swap understates the upstream
behavioural delta it imports.

**Dangling-submodule check (when a `submodules: recursive` step fails).** A submodule
pinned to a SHA reachable from no ref on its remote (no branch, no tag contains it; e.g. a
pre-release commit that was garbage-collected or never pushed as a named ref) makes
`git clone --recurse-submodules` fail with `fatal: upload-pack: not our ref <sha>` on EVERY
fresh CI clone, silently failing all checks that use `submodules: recursive` regardless of
which PR triggered the run. The symptom looks like a transient network or CI-infra error.
When a CI step that checks out submodules fails this way, run `git submodule status` and
verify each listed SHA is reachable on its remote (`git ls-remote <remote-url> | grep <sha>`).
If a SHA is unreachable, this is a pre-existing repo-wide blocker (confirm by checking run
IDs before and after the PR's commits), and the fix is a submodule-bump PR, not debugging CI
config; flag it as `[Critical - pre-existing]`.

Emit each finding:

```text
[Critical] CI: {check name}: {state} ({link})
Confidence: 100 (objective CI result)
```

If any Critical CI finding exists (a required check failing, or `MERGE_STATE` is
`BLOCKED`), the report header must include:
**BUILD FAILING: do not merge until CI is green.**

**Phantom / never-reported required check (silent BLOCKED).** `gh pr checks` and the
GraphQL `statusCheckRollup` show only checks that ACTUALLY RAN; a required context that
never reports (wrong name, or no workflow emits it) sits `EXPECTED` forever and blocks
merge while the rollup looks green. When `MERGE_STATE` is `BLOCKED` but no failing check
appears in `CI_CHECKS`, cross-reference the required set against the contexts actually
emitted on the head SHA and flag any required context with no matching completed run:

```text
[Critical] CI: required context "{name}" is in branch protection but never reported on this
PR (phantom/name-mismatch). It blocks merge silently. Remediation is a branch-protection or
workflow job-name fix, not a code change.
```

GitHub Actions reports check names as `workflow_name / job_name`; a required context listed
as the bare `job_name` will never match. Reliable merge readiness requires `MERGE_STATE` in
`{CLEAN, UNSTABLE}` (not `BLOCKED`) in addition to green check conclusions.

If any finding is tagged `[Critical - pre-existing, rebase needed]`, also add to the header:
**BRANCH BEHIND: some failures may clear after rebasing on {BASE_BRANCH}.**

If every Critical CI finding is tagged `[Critical - likely transient, rerun]`, do NOT
add BUILD FAILING; instead add:
**CI: transient infrastructure failures detected; remediation is re-run, not a code change.**

---

## Step 2d: Branch staleness (parallel with Step 2c)

Compute two objective staleness signals; Agent M (Step 5) uses them as a
scan-intensity dial and a HOLD bias on confirmed regressions.

```bash
BASE_ENC=$(printf '%s' "$BASE_BRANCH" | jq -sRr @uri)
HEAD_ENC=$(printf '%s' "$HEAD_BRANCH" | jq -sRr @uri)
CMP=$(gh api "repos/$OWNER/$REPO/compare/${BASE_ENC}...${HEAD_ENC}" || echo '{}')
COMMITS_BEHIND=$(echo "$CMP" | jq '.behind_by // 0')
FIRST_DIVERGENT_DATE=$(echo "$CMP" | jq -r '.commits[0].commit.committer.date // empty')
if [ -n "$FIRST_DIVERGENT_DATE" ]; then
  # date -d is GNU coreutils; on BSD/macOS the parse fails and falls back to age 0
  DIV_EPOCH=$(date -d "$FIRST_DIVERGENT_DATE" +%s 2>/dev/null || echo "$(date +%s)")
  AGE_DAYS=$(( ( $(date +%s) - DIV_EPOCH ) / 86400 ))
else
  AGE_DAYS=0
fi
```

Store as `STALENESS = {commits_behind: COMMITS_BEHIND, age_days: AGE_DAYS}`. When
`AGE_DAYS` exceeds `PREMISE_STALENESS_HOLD_DAYS`, or `COMMITS_BEHIND` is large, Agent
M scans contested files more deeply and biases its verdict toward HOLD on any
regression it confirms. This step is non-blocking: if the compare call fails, set
`STALENESS = {commits_behind: 0, age_days: 0}` and note "staleness: unavailable".

---

## Step 2e: PR-overlap targeting (parallel with Step 2c)

Compare the current PR against recent and in-flight PRs along two dimensions:
file-path overlap and symbol overlap. The path dimension catches two PRs editing the
same file; the symbol dimension catches two PRs adding the same definition in
different files (the duplicate-provider smell). Path overlap alone is insufficient;
see the rag-processor acceptance fixture in the design spec.

Comparison set: the last `PREMISE_MERGED_PR_LOOKBACK` merged PRs plus all open PRs
except the current one.

```bash
gh pr list --repo "$OWNER/$REPO" --state merged --limit "$PREMISE_MERGED_PR_LOOKBACK" \
  --json number,title,mergedAt,files \
  --jq '[.[] | {number, title, mergedAt, files: [.files[].path]}]'

gh pr list --repo "$OWNER/$REPO" --state open \
  --json number,title,files \
  --jq "[.[] | select(.number != $PR_NUMBER) | {number, title, files: [.files[].path]}]"
```

### Dimension 1: file-path overlap

Intersect each comparison PR's file list with `CHANGED_FILES`. Produce
`CONTESTED_FILES`: records of `{file, overlapping_pr, pr_state, merged_at}`.

- Overlap with a merged PR whose `mergedAt` postdates the current branch's merge-base
  is a staleness / silent-revert risk: the current branch never saw that merged
  change.
- Overlap with an open PR is a collision / duplicate-work risk. Record it in
  `CONTESTED_FILES` (with `pr_state: open`); Agent M (Step 5) is the sole emitter of
  the finding, so it flows through Step 6 scoring like any other finding. Do NOT emit
  it here; emitting both here and from Agent M would double-count it. Agent M formats
  it as:

```text
[Important] Premise/Collision: file {f} is also modified by open PR #{n} ("{title}").
Verify the two changes do not conflict or duplicate effort before either merges.
```

Caveat: `gh pr list --json files` caps at ~100 files per PR. Acceptable for overlap
detection; note in the report if any scanned PR hit the cap.

### Dimension 2: symbol overlap

File-path overlap returns nothing when two PRs add the same symbol in different
files. Extract newly-added top-level definitions from a diff and intersect their
names across PRs, regardless of file path:

```bash
gh pr diff "$N" --repo "$OWNER/$REPO" 2>/dev/null | awk '
  /^\+\+\+ / { file=$2 }
  /^\+(async def|def|class) / {
    line=$0; sub(/^\+/,"",line);
    match(line, /^(async def|def|class)[ \t]+[A-Za-z_][A-Za-z0-9_]*/);
    print file "\t" substr(line, RSTART, RLENGTH)
  }'
```

Build `ADDED_SYMBOLS_CURRENT` for the PR under review, then run the same extraction
on the comparison set (bound cost to open PRs plus merged PRs newer than the current
branch's merge-base). A collision fires when a non-dunder, non-`test_` symbol name
added by the current PR is also added by a comparison PR in a different file:

```text
[Important] Premise/DuplicateSymbol: {symbol} is newly defined by both this PR ({file_a})
and PR #{n} ({file_b}). These are likely duplicate definitions that will need
deduplication after both merge. Confirm only one should define it.
```

Exclusions to limit false positives: dunder names (`__init__`, `__call__`), `test_*`
functions, and conventional hooks (`setUp`, `main`). Symbol collisions are
QUESTION-tier, not HOLD, because choosing the canonical definition needs human
judgment. Store all collisions as `SYMBOL_COLLISIONS` and pass to Agent M.

---

## Step 2f: Supersession pre-check (only when MERGE_STATE is DIRTY or BEHIND)

For a stale PR, the first question is "does the base branch already contain this?" not
"is this code good?" A byte-level comparison against the base costs a couple of git
commands and can invalidate the entire premise of the review before the agent fleet
runs. Skip this step when `MERGE_STATE` is `CLEAN` (the up-to-date-with-base state;
`mergeStateStatus` has no `MERGEABLE` value, that belongs to the separate `mergeable` field).

For each file in `CHANGED_FILES`, compare the PR head content to the base branch:

```bash
for f in {CHANGED_FILES}; do
  if git diff --quiet "origin/$BASE_BRANCH" "$HEAD_SHA" -- "$f" 2>/dev/null; then
    echo "IDENTICAL  $f"
  else
    echo "DIFFERS    $f"
  fi
done
```

- **Most files IDENTICAL to base:** short-circuit to a "superseded PR" report. Diff the
  remaining DIFFERS files base->head to enumerate exactly what merging would still add
  (the *residual* salvage list) and what it would REGRESS (lines a later base commit
  deliberately removed that this branch re-adds). Recommend close-plus-follow-up-issue,
  attach the salvage list, and stop before spawning the full agent fleet. Supersession
  is rarely all-or-nothing: report the residual, not a binary yes/no.

**`git diff base head` direction alone is not enough to declare a regression.** Diff
direction between two diverged tips conflates "this branch changed it" with "base changed
it later"; a DIFFERS file on a stale branch can look like it re-adds deliberately-removed
content when in fact the branch never touched the file relative to the merge-base and a
merge would cleanly take base's version. For each DIFFERS file, run a merge-base-aware
three-way classification (`git merge-tree --write-tree "origin/$BASE_BRANCH" "$HEAD_SHA"`,
or per-file three-way reasoning) to bucket it as (a) genuine conflict, (b) branch-regresses-
base, or (c) merely-behind-base (merge takes base cleanly). Only (a) and (b) are actionable;
(c) is a non-finding. Only a three-way merge tells you what a merge would actually do.
- **Few or no files IDENTICAL:** proceed to Step 3 normally; note any IDENTICAL files so
  agents do not waste effort reviewing already-merged content.

**Dependency-pin and dual-PR caveat.** `gh pr diff` is computed against the merge base,
not the live base branch, so a bot-generated dependency PR can show a SHA or version
change that a sibling PR already landed on base (e.g., two Renovate PRs pointing at the
same upstream commit via two tags). For pin PRs, fetch the changed lines' current
content on the base branch and compare to the PR's intended end-state; if base already
matches, flag "functionally superseded; effective change is comment-only" before agents
run. When verifying a SHA pin against an annotated tag, dereference it first
(`git/ref/tags/{tag}` returns the tag OBJECT sha; resolve via `git/tags/{sha}`) before
declaring a mismatch.

---

## Step 3: Classify Changes (Haiku agent)

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
from that repo's default branch and that the file exists at that ref:

```bash
gh api "repos/<owner>/<repo>/compare/<default>...<sha>" --jq '.status'   # must not be "diverged"
```

A `diverged` status means the pin points at a commit reachable from no ref (commonly a
PR-branch SHA orphaned by a squash-merge); the Actions resolver refuses it and the workflow
fails at startup once the source branch is deleted. Note `contents?ref=<sha>` still serves
the file for dangling commits, so a file-existence check gives false confidence; use
`compare`. Emit:

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

Include the moved file path in the CHANGED_FILES list for agents B, F, G, and I so
they read full file context, not just the diff hunk.

---

## Step 4: Fetch SonarQube Findings (parallel with Step 5)

### 4a. Detect organization

Check for org config in this order:

1. `.sonarlint/connectedMode.json` → `sonarCloudOrganization` field
2. `sonar-project.properties` → `sonar.organization` field
3. Infer from the GitHub owner: `byronwilliamscpa` or `williaby`

Route to the correct MCP server:

| Org | MCP Tool Prefix |
| ----- | ---------------- |
| `byronwilliamscpa` | `mcp__sonarqube__` |
| `williaby` | `mcp__sonarqube-williaby__` |

If neither org is detected, skip SonarQube and note "SonarQube: not configured
for this repository" in the report. Do not block the rest of the workflow.

**REST fallback when the MCP server is not loaded.** The sonarqube MCP server is not
connected in every session. When the MCP prefix is unavailable, query the SonarCloud Web
API directly with `SONARQUBE_TOKEN` (a local shell env var) rather than skipping Sonar
entirely:

```bash
curl -s -u "${SONARQUBE_TOKEN}:" \
  "https://sonarcloud.io/api/issues/search?projects={KEY}&organization={ORG}&pullRequest={N}"
curl -s -u "${SONARQUBE_TOKEN}:" \
  "https://sonarcloud.io/api/hotspots/search?projectKey={KEY}&pullRequest={N}"
```

Both endpoints require authentication: an anonymous request returns "Project doesn't
exist" even for a valid key, so the `-u "${SONARQUBE_TOKEN}:"` form is mandatory and the
curl path covers BOTH issues and hotspots. Only if both MCP and REST fail should the
workflow skip Sonar.

### 4b. Resolve project key

Check in order:

1. `.sonarlint/connectedMode.json` → `projectKey`
2. `sonar-project.properties` → `sonar.projectKey`

If not found, use `search_my_sonarqube_projects` to list projects and match
by repo name.

### 4c. Fetch PR-specific issues

```text
search_sonar_issues_in_projects(
  projects: [PROJECT_KEY],
  pullRequest: PR_NUMBER   ← PR-specific analysis only
)
```

If the PR has not been analyzed yet (empty result), fall back to branch issues:

```text
search_sonar_issues_in_projects(
  projects: [PROJECT_KEY],
  branch: HEAD_BRANCH
)
```

Note in the report whether results are PR-specific or branch-level.

### 4f. Fetch PR-specific security hotspots

Security hotspots are a completely separate queue from issues in SonarCloud.
`search_sonar_issues_in_projects` never returns them; this explicit call is
required. Skipping it is the most common reason hotspots go unreviewed.

```text
search_security_hotspots(
  projectKey: PROJECT_KEY,
  pullRequest: PR_NUMBER
)
```

If the result is empty (PR not yet analyzed), fall back to branch-level with
status filter:

```text
search_security_hotspots(
  projectKey: PROJECT_KEY,
  branch: HEAD_BRANCH,
  status: "TO_REVIEW"
)
```

Note in the report whether results are PR-specific or branch-level.
Store as `SONAR_HOTSPOTS`. For each hotspot record: component, line, rule key,
message, securityCategory, vulnerabilityProbability (HIGH/MEDIUM/LOW).

### 4g. Pre-flight SonarCloud configuration check

Before fetching findings, inspect any `sonar-project.properties` or
`sonar-project.properties.template` for placeholder values:

```bash
gh api repos/{OWNER}/{REPO}/contents/sonar-project.properties \
  --jq '.content' | base64 -d 2>/dev/null
```

If any of these patterns appear, emit a **Critical** finding in the report:

- `sonar.organization=your-org` or `sonar.organization=your_org`
- `sonar.projectKey=your-project` or similar placeholder
- `sonar.host.url` pointing at `localhost`

Message: "SonarCloud configuration contains placeholder values; CI quality
gate will fail. Update `sonar-project.properties` with the real organization
and project key before merge."

This prevents the silent "SonarCloud: not configured" skip that delays
findings until a later push.

### 4e. Store SonarQube findings and hotspots for the fix step

SonarQube issues are deterministic -- they have clear, prescribed fixes and
do not require human judgment. Do not include them in the review report.
Store as `SONAR_FINDINGS` and pass to the fix workflow.

For each issue record: file, line, rule key, message, severity. Run a
`show_rule` lookup for any unfamiliar rule key so the fix step has
remediation guidance ready.

Security hotspots require human judgment to decide exploitability, but still
warrant a code change in most cases (pinning an unpinned action, removing a
vulnerable regex, etc.). Store `SONAR_HOTSPOTS` alongside `SONAR_FINDINGS`
and pass both to the fix workflow.

The review report shows only a one-line summary:
"SonarQube: {N} issues and {M} hotspots queued for auto-fix."
Omit the hotspot clause if M = 0. The fix step resolves both without
further review unless a hotspot genuinely requires a human decision.

### 4h. Qlty findings (other configured quality gate)

Account for every configured quality gate that produces findings, not just the ones with
convenient APIs. Qlty posts a blocking-issue count as a GitHub commit STATUS (not a
check_run), so the check-runs/annotations API returns nothing for it. Detect it:

```bash
gh api "repos/$OWNER/$REPO/commits/$HEAD_SHA/statuses" \
  --jq '.[] | select(.context | test("qlty"; "i")) | {state, description, target_url}'
```

If a `qlty check` status is present, extract the issue count and `target_url` and note
them in the report header. If the `qlty` CLI is available locally, enumerate findings with
`qlty check --upstream origin/{BASE_BRANCH} --format json` against the PR head. Otherwise
state explicitly in the report that qlty's N issues were counted but NOT enumerated (the
qlty.sh issues page is auth-walled, so WebFetch returns a login page), so the user knows
there is an un-itemized queue rather than assuming full coverage. Pass the count to the fix
workflow. Never let an un-enumerable queue silently imply full coverage.

---

## Step 5: Run Parallel Review Agents

Launch all applicable agents simultaneously using the Agent tool. Each agent
receives its context inline (no local git state; all from `gh` output).

### Large-PR handling

If the total diff exceeds 500 lines, choose a strategy before spawning agents:

**Strategy A: Per-file chunking** (preferred when PR has many small files):
Split `CHANGED_FILES` into batches of 10 files each. Run all agents once per batch.
Merge findings across batches before Step 6. Label each finding with the batch file
that produced it.

**Strategy B: Hard stop** (preferred when PR has one or two very large files):
Emit a Critical finding immediately:

```text
[Critical] Review: Diff exceeds 500 lines ({actual_count} lines). pr-review cannot
guarantee complete coverage of diffs this large. Lines beyond 500 were not analyzed.
```

Then proceed with the first 500 lines and label the report:
`WARNING: Review covers lines 1-500 only. Lines 501 onward were not analyzed.`

Never silently truncate. Always tell the user what was and was not reviewed.

### File context fetch (run before spawning agents)

For each file in `CHANGED_FILES` that has more than 10 lines changed, fetch its full
content at the PR head SHA:

```bash
gh api repos/{OWNER}/{REPO}/contents/{FILE_PATH}?ref={HEAD_SHA} \
  --jq '.content' | base64 -d > /tmp/ctx_{FILE_SLUG}.txt
```

Store as `CONTEXT_FILES` map: `{file_path: full_file_content}`.

Agents B, F, G, and K receive `CONTEXT_FILES` in addition to the diff. Their
instructions include: "When evaluating a changed function, read the surrounding 200
lines from CONTEXT_FILES to understand callers and callees before issuing findings."

**Critical instruction for all agents:**
> Do NOT dismiss any finding as trivial, a nitpick, or "would be caught by
> a linter." Report everything you observe. Categorize it; do not omit it.
> The user reviews all tiers. Confidence scoring happens after you return.

### Agent A: CLAUDE.md Compliance (Sonnet)

```text
You are reviewing a GitHub pull request for project standards compliance.

PR: {PR_TITLE} ({OWNER}/{REPO}#{PR_NUMBER})
Base branch: {BASE_BRANCH}

CLAUDE.md content:
{contents of all CLAUDE.md files in the repo, fetched via gh}

PR diff:
{PR_DIFF}

Review the diff against CLAUDE.md. Find every violation, large and small.
Do NOT filter anything as trivial. Report each issue with: file, approximate
line, description, which CLAUDE.md rule it violates.

"Missing X" findings require verifying absence, not just verifying that X is warranted.
Before flagging a missing RAD marker (`#CRITICAL`, `#VERIFY`, `#ASSUME`, `#EDGE`) on a
production-risk assumption, grep the changed file's diff context around the flagged
construct for an existing marker of that family; a RAD-marker finding must cite the
specific lines checked and confirm none were found. A reviewer that notices an assumption
warranting a tag but does not confirm the tag is absent will routinely surface false
positives on a well-tagged codebase and cost a wasted fix cycle.

HARD CONSTRAINT: you have only the diff and the CLAUDE.md text below. Do NOT assert
any fact that requires external tool access: commit signature/verification status, CI
results, or the contents of files not present in the provided diff. You cannot verify
these and will fabricate a plausible-sounding status if you try. If you suspect an issue
needs external verification, flag it as "unverifiable from diff alone" for the main loop
to check; never state a verification status as fact.

Also check for declared-but-unwired dev tooling: scan any `pyproject.toml` in the diff
for tools added under `[dependency-groups] dev` or `[tool.poetry.dev-dependencies]`
(e.g., basedpyright, pydoclint, interrogate). For each, check whether a CI workflow file
or `.pre-commit-config.yaml` in the diff actually invokes it. A tool installed on every
`uv sync` but never run adds lock weight and a false impression of quality coverage.
Report:
  [Suggested] Dev dep "{tool}" declared but not wired to CI or pre-commit.

Also check: if `.claude/settings.json` appears in CHANGED_FILES, verify all `Bash()`
permission patterns use space syntax (e.g., `Bash(git *)`) not colon syntax (e.g.,
`Bash(git:*)`). Colon syntax is the MCP tool format and does not match shell commands;
it makes allow entries silently inert.
  [Important] CLAUDE.md: Bash permission in settings.json uses colon syntax; use space syntax.

Also check: if the diff renames a tool prefix or config identifier (`mcp__*` tool names,
MCP server keys, env var names, settings keys), resolve the NEW identifier against the
authoritative machine-readable registration (`.mcp.json`, `settings.json`, or the live
tool list), not the surrounding doc prose. Prose can lag or contradict the runtime
registration: a rename that reads as internally consistent in narrative documentation can
still be broken against the registry and fail at runtime. Report:
  [Critical] CLAUDE.md: renamed identifier "{new}" does not resolve in {.mcp.json|settings.json|live tool list}; the rename breaks every reference at runtime.

Also check commit types: fetch the commit history
(`gh api repos/{OWNER}/{REPO}/commits?sha={HEAD_SHA}&per_page=20` and scan the commit
messages), then cross-check each commit type against the project's conventional-commits allowed-type
table (fetch `.claude/standards/conventional-commits.md` via `gh api repos/{OWNER}/{REPO}/contents/.claude/standards/conventional-commits.md`;
if absent, use the default set: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert).
Any commit type not in that table (e.g., `security:`, `ops:`, `claude:`) should be flagged:
  [Suggested] CLAUDE.md: Commit type "{type}" is not in the allowed-type table.

STRUCTURAL-INVARIANT PASS (run these regardless of which diff lines changed; a
diff-line scan is structurally blind to invariants the diff implies but does not touch):

Manifest freshness: if `docs/standards-manifest.yaml` is in CHANGED_FILES, fetch it at
HEAD_SHA (`gh api repos/{OWNER}/{REPO}/contents/docs/standards-manifest.yaml?ref={HEAD_SHA}`)
and assert its header `last_updated` field is >= the latest commit date on the branch.
If the stamp is older than the newest commit, report:
  [Important] Manifest: last_updated ({value}) is stale; a manifest edit landed after it.
Do not rely on a per-PR reminder for this; it is reliably forgotten under review flow.

Spec/plan alignment: when both an implementation/workflow file AND a spec or plan file
(paths under `docs/superpowers/plans/`, `docs/superpowers/specs/`, `plans/`, or `specs/`)
appear in CHANGED_FILES, cross-check the docs against the implementation. This is a
structural consistency check, not a correctness judgment:
  (a) any format example in the plan/spec matches what the implementation actually emits;
  (b) any scope qualifier in the plan/spec ("ONLY on X", "directly emit") matches the
      implementation's actual scope.
Report drift as:
  [Important] SpecDrift: {plan/spec path} describes "{quoted text}", superseded by the
  implementation's "{actual behavior}".
```

### Agent B: Bug Scan (Sonnet)

```text
You are scanning a pull request diff for bugs.

PR diff:
{PR_DIFF}

Scan only the changed lines (additions and modifications). Find:
- Logic errors
- Null/None dereferences
- Off-by-one errors
- Incorrect conditionals
- Missing error handling
- Data integrity risks
- Security vulnerabilities in the changed code
- Platform-default encoding defects: in Python diffs, flag open(), Path.read_text(),
  Path.write_text(), and Path.open() calls that omit an explicit encoding= argument when
  the repo runs a Windows CI leg (check the diff and changed workflows for a
  windows-latest matrix entry). The platform default differs (cp1252 on Windows vs UTF-8
  on Linux/macOS), so an unencoded read silently mis-decodes non-UTF-8 input instead of
  raising. Phrase it as a portability defect, not a style nit; it is invisible to
  Linux-only pre-commit and surfaces only as a red Windows leg after push.

Batch-remediation completeness: if the PR description indicates a pattern-based fix
(keywords "remediate", "harden", "fix all", "sonar", "migrate"), do NOT trust per-line
correctness alone. For each pattern named in the description, search every changed file
for instances that still match the OLD pattern and were not converted. The same pattern
often appears multiple times in one file, and fixing the most visible instance creates a
false impression of completeness (e.g., one of two curl calls hardened). Report any
missed instance.

Exemption-guard false negatives (validators and linters): when the diff adds or changes a
guard function or allow-list predicate that suppresses findings for some input category
(an `is_local_build()`-style check, a skip list), do not judge it on whether it "makes
sense in principle." Ask what real inputs satisfy the guard and whether they should be
exempted: run the predicate against representative real inputs and flag any case where
`f(real_input)` returns True and silently exempts a substantial class of inputs that should
be flagged (e.g., `is_local_build("grafana/grafana")` -> True wrongly exempts the largest
class of real Docker Hub images). A single incorrect predicate reduces findings for every
matching input with no visible warning, so surface it as the general pattern, not just the
one instance.

Compose env-default flips break unpinned CI callers: when the diff changes the default value
of a docker-compose environment variable (pattern `${VAR:-old}` -> `${VAR:-new}`), it is a
global default change, not just a documentation change. Grep the repo's CI workflow files for
any step that starts that service; for each, verify it sets the env var explicitly. If a
caller starts the service without pinning the var, flag [Important]: it inherits the new
default, and if the new default needs credentials or infrastructure CI lacks (remote APIs,
GPU, cloud services), the break is silent until Newman or health checks fail. Reviewing an
env-default change requires cross-searching all callers.

Do NOT filter anything as trivial. Report every issue you find, regardless
of how minor. Include: file, approximate line, description, severity
estimate (Critical / Important / Suggested / Informational).
```

### Agent C: Git History Context (Sonnet)

```text
You are reviewing a pull request in the context of the repo's git history.

PR: {OWNER}/{REPO}#{PR_NUMBER}
Changed files: {CHANGED_FILES}

For each changed file:
1. Run: gh api repos/{OWNER}/{REPO}/commits?path={file}&per_page=10
   to see recent commit history on the file
2. Look for patterns: recent reverts, repeated fixes to the same area,
   known fragile code, or prior bugs in the same function

Report any issues the diff introduces that are concerning in light of
the file's history. Include: file, concern, relevant historical context.
```

### Agent D: Prior PR Comments (Sonnet)

```text
You are checking whether past review comments apply to a new pull request.

PR: {OWNER}/{REPO}#{PR_NUMBER}
Changed files: {CHANGED_FILES}

For each changed file, search for recent closed PRs that touched it:
  gh pr list --repo {OWNER}/{REPO} --state closed --json number,title,files \
    | jq '[.[] | select(.files[].path == "{file}")][:5]'

For any matching PRs, fetch their review comments:
  gh api repos/{OWNER}/{REPO}/pulls/{found_number}/comments

Report any review comments from those PRs that also apply to the current
changes. Include: original PR number, comment text, why it still applies.
```

### Agent E: Code Comment Accuracy (Sonnet)

*Run only if comment-analyzer is activated in Step 3.*

```text
You are reviewing whether code comments and docstrings in a PR are accurate.

PR diff:
{PR_DIFF}

For every docstring, inline comment, or TODO added or modified in the diff:
1. Check whether it accurately describes the surrounding code
2. Identify comment rot (comment says X but code does Y)
3. Flag missing docstrings on new public functions/classes
4. Flag outdated parameter descriptions

Report ALL issues; do not skip anything because it seems minor. Include:
file, line, the comment text, the discrepancy.
```

### Agent F: Silent Failure / Error Handling (Sonnet)

*Run only if silent-failure-hunter is activated in Step 3.*

```text
You are reviewing a pull request for silent failures and error handling issues.

PR diff:
{PR_DIFF}

Find every place where errors could be swallowed silently:
- Bare except clauses
- except Exception: pass or similar
- catch blocks that log but don't propagate
- Missing error handling on IO, network, or DB operations
- Fallback values that hide the real error
- Async errors that are not awaited or caught
- Exception handlers that do not cover the full call surface inside the
  try block: parsing calls (resp.json(), datetime.fromisoformat(), etc.)
  nested inside network try blocks that only catch network exception types
  (HTTPError, RequestException): json.JSONDecodeError and ValueError are
  NOT subclasses of those types, so a 200 response with a non-JSON body
  propagates uncaught and aborts the script rather than being treated as a
  per-item warning. For each try block, enumerate every call inside it and
  verify the except clauses cover all raised types, not just the primary
  network call.

Asserted-invariant enforcement: when the diff (or its prose/docstrings) asserts a
safety or scope invariant ("only gitignored paths", "read-only", "never touches X",
"targets only regenerable files"), verify the code ENFORCES that exact invariant, not
merely that the operation is bounded. "Bounded" is not "compliant": a deletion that
cannot escape the repo tree still violates an "only gitignored" promise if it matches
files by name (`__pycache__`, `.coverage`) instead of gating on `git check-ignore`.
Containment (can it escape?) and invariant (does it do only what it promised?) are
different checks; flag any gap between an asserted invariant and its enforcement as at
least Important.

Documented intentional non-catch: before flagging an uncaught exception type as a
silent failure, check the enclosing function AND module docstring (which may sit outside
the diff hunk) for a documented rationale. Error-handling philosophy is often documented
at module scope, outside the changed lines. If the non-catch is documented as deliberate
(e.g., "a JSONDecodeError signals an API contract change and must fail loudly"), classify
it as [Informational] documented-design, not a defect. A diff hunk alone is not enough
context to judge whether an omitted handler is a bug or a design choice.

Do NOT dismiss anything as minor. Report every case: file, line, pattern,
what failure scenario it silences, recommended fix.
```

### Agent G: Test Coverage Quality (Sonnet)

*Run only if pr-test-analyzer is activated in Step 3.*

```text
You are reviewing test coverage quality in a pull request.

PR diff:
{PR_DIFF}

For every new or modified function/method/class in the diff:
1. Check whether the PR includes tests for it
2. Identify missing edge cases, boundary conditions, negative tests
3. Flag tests that are too implementation-coupled (test internals, not behavior)
4. Flag missing tests for error conditions introduced in the diff

Rate each gap 1–10 (10 = critical, will cause production failures without it).
Report ALL gaps; do not skip low-rated ones. Include: what's untested,
what failure it could allow, the criticality rating.
```

### Agent H: Type Design (Sonnet)

*Run only if type-design-analyzer is activated in Step 3.*

```text
You are reviewing type design in a pull request.

PR diff:
{PR_DIFF}

For every new type definition (class, TypeAlias, TypedDict, dataclass,
Protocol) added in the diff:
1. Evaluate encapsulation: does the type hide implementation details?
2. Evaluate invariants: does the type prevent invalid states?
3. Evaluate usefulness: does it express domain concepts clearly?
4. Check for anemic types (pure data containers with no behavior)
5. Check for types that allow invalid combinations of fields

Rate each dimension 1–10. Report ALL issues; do not skip low scores.
Include: type name, dimension, rating, specific concern.
```

### Agent I: Security Pass (Sonnet)

```text
You are performing a dedicated security review of a pull request diff.

PR diff:
{PR_DIFF}

Evaluate every check below explicitly. Do NOT skip a check just because it
seems unlikely; state "No issues found" for each clean check.

Checks:
- SQL injection: string concatenation into queries, f-string queries, execute()
  with user-supplied input
- Command injection: subprocess calls, shell execution APIs (eval, exec) with
  user-supplied input
- Path traversal: file open operations without resolve() combined with a
  base-path check
- SSRF: outbound HTTP calls where the URL contains user-supplied hostname or path
- Authentication bypass: routes missing auth decorator, permission checks skipped
  by early return
- Secrets in code: API keys, tokens, passwords hardcoded or logged
- Insecure deserialization: unsafe deserialization of untrusted binary or text data,
  yaml.load without Loader=SafeLoader

Asserted-invariant enforcement (separate from the checks above): when the diff or its
prose claims a safety/scope invariant ("only gitignored paths", "read-only", "never
deletes tracked files"), verify the code ENFORCES that exact claim, not merely that the
blast radius is bounded. A destructive operation that is symlink-contained and cannot
escape the repo still violates an "only gitignored" promise if it matches paths by name
instead of gating on `git check-ignore`. Verifying containment (can it escape?) does NOT
satisfy invariant verification (does it do only what it promised?); the prose claim is
the spec. Flag any gap as at least Important.

For each check output one of:
  [Critical] Security/{check}: {finding}
  [Info] Security/{check}: No issues found

Confidence: Critical findings score 90 unless attacker-controlled input is
demonstrably impossible, in which case 70.

LLM-agent-in-CI lens (run ONLY when a workflow file in the diff embeds an autonomous
agent action such as `uses: anthropics/claude-code-action`): the agent's behavioral spec
is the natural-language `prompt:` block, not the surrounding YAML, so the imperative-code
checks above largely do not apply. Review the `prompt:` block as executable control flow:
- Classification/precedence rules that could route a security-relevant PR into a class
  that SKIPS substantive checks (a single-class rule with the wrong precedence is a real
  finding).
- Escalation/label-apply steps (`gh label apply` and similar) that can fail silently and
  drop the PR from a downstream queue.
- The security boundary is `--allowedTools` plus the job's token scopes, NOT the repo's
  local `.claude/settings.json` deny rules (whose CI applicability is unverified). Treat
  the allowlist and token scopes as the enforcement boundary.
- Confirm only trusted event context is interpolated into the prompt, and that the trigger
  is `pull_request`, not `pull_request_target`.
Cross-reference project memory `project_agent_in_ci_review.md` if present. Emit findings in
the same `[Critical|Important] Security/{check}` form.
```

### Agent J: PR Description vs Diff Validation (Sonnet)

```text
You are validating that the PR description accurately reflects the diff.

PR title: {PR_TITLE}
PR body: {PR_BODY}
Changed files: {CHANGED_FILES}
PR diff: {PR_DIFF}

Checks:
1. For each component or change claimed in the "## Changes" section of PR_BODY:
   verify a corresponding file or function change exists in the diff.
   Report [Important] PRDesc: {claim}: not found in diff.

2. For each file in CHANGED_FILES: verify it is mentioned (directly or by
   implication) in PR_BODY.
   Report [Suggested] PRDesc: {file} changed but not mentioned in description.

3. Check whether PR_BODY contains a "## Why" or equivalent motivation section.
   Report [Suggested] PRDesc: Missing motivation section (## Why or equivalent).

4. If the PR title or labels indicate a bug fix, check whether PR_BODY references
   an issue number (Fixes #N, Closes #N, or Relates to #N).
   Report [Suggested] PRDesc: Bug fix PR does not reference an issue number.

5. When fetching file contents to verify diff claims, always use
   `gh api repos/{OWNER}/{REPO}/contents/{path}?ref={HEAD_SHA}`, not the
   default branch. Reading main-branch files produces false positives because
   it returns the pre-change state.

   Also scan committed markdown (and other committed docs) in the diff for paths under
   `/tmp`, `/var/folders`, session-local scratchpad directories, or any path containing a
   UUID-like segment. Any such path is a dangling reference the moment the authoring
   session ends and reads as authoritative to a future reader who will 404 following it.
   Report [Important] PRDesc: committed doc {file} references ephemeral path {path}; replace
   with inline rationale or a pointer to a committed file.

6. For every quantitative claim in your findings (file counts, line counts,
   symbol names, test counts, function names): verify against
   `gh pr view --json files,title` or the PR diff before including the
   finding. Quantitative claims that cannot be verified against actual PR
   data must be dropped, not downgraded. Fabricated file counts or symbol
   names that appear plausible but are absent from the actual diff are a
   common hallucination pattern for architecture-review agents receiving
   truncated context.

7. External-claim dereferencing (manifest, compliance, and config PRs especially):
   a green CI run proves the artifact is internally well-formed, not that its claims
   about OTHER repos or files hold. When the PR introduces or edits a check, rule, or
   config that references an external file or pattern (a `verify` directive that greps
   another repo's file, a rollout count, a repo named as a PASS fixture in the test plan):
   - Dereference every external path/pattern against the live repo(s) it claims to govern.
     Fetch the named file (`gh api repos/{O}/{R}/contents/{path}`) and confirm the pattern
     the check greps for is actually present. Report [Important] PRDesc: check references
     {pattern} in {repo}:{file}, but that file contains {actual}; the stated PASS fixture
     would FAIL.
   - Treat each test-plan checkbox as a falsifiable claim and spot-verify the cheapest
     ones via `gh api` before reporting.
   - When PR_BODY claims "rebased onto current main," confirm MERGE_STATE is not
     DIRTY/BEHIND and that any sibling-PR IDs referenced in the diff are actually present
     post-rebase. Report a merge-conflict mismatch as [Critical], an unmet test-plan
     claim as [Important].
```

### Agent K: Performance Review (Sonnet)

```text
You are reviewing a pull request for performance anti-patterns.

PR diff:
{PR_DIFF}

Also available: CONTEXT_FILES (full file content for files with >10 lines changed).
When evaluating a changed function, read the surrounding context from CONTEXT_FILES
to understand callers and data flow before issuing findings.

Checks:
- N+1 queries: ORM calls inside loops (for item in queryset: item.related.all())
- Blocking I/O in async context: synchronous HTTP calls or file reads inside
  async def functions
- Unbounded loops: while True or iteration with a database/network call and no
  break or limit condition
- Quadratic complexity: nested loops where both iterables grow with user input
- Missing pagination: list endpoints returning unbounded result sets
- Large in-memory loads: loading entire files or tables into memory without
  streaming

For each issue found:
  [Important] Perf/{category}: {finding}, estimated impact: {brief statement}

If no issues found:
  [Info] Perf: No performance issues detected in diff
```

### Agent L: Architectural Review (flexible panel)

*Run when `CHANGED_FILES` includes new modules, new public API surfaces,
new base classes, or structural changes to existing modules (heuristic:
any file where more than 30% of lines changed or a new top-level class
or function was added).*

Call `Skill("panel")` in flexible panel mode with `PANEL_MODELS` and the
prompt below. Assign every model the neutral `technical_validator` role (or an
equivalent literal stance in the roles file) so all participate as independent
reviewers rather than debating a position.

```text
Prompt: You are reviewing a pull request for architectural quality.

PR title: {PR_TITLE}
PR diff:
{PR_DIFF}

Review dimensions:
1. Coupling: does the change introduce tight coupling between modules that
   were previously independent? Are dependencies flowing in the right direction?
2. Abstraction: are new abstractions at the right level? Do they generalize
   beyond this immediate use case without being over-engineered?
3. Extensibility: are extension points preserved or introduced where future
   growth is likely?
4. Consistency: does the change follow the patterns established in adjacent
   modules or diverge without clear justification?
5. Boundary clarity: are the responsibilities of each new class, function,
   or module clearly delineated?

For each concern found, report:
  [Important] Arch/{dimension}: {finding}

If no concerns found, report:
  [Info] Arch: No architectural concerns detected in diff
```

Collect the consensus synthesis as Agent L findings. Route through Step 6
confidence scoring and Step 7 deduplication with `agent source: L`.

### Agent M: Premise & Regression Gate (Opus)

Always active. Runs in the Step 5 parallel batch so it adds no wall-clock. Opus, because
every check is a judgment call. Receives: `PR_DIFF`, `PR_TITLE`, `PR_BODY`,
`CHANGED_FILES`, `CONTEXT_FILES`, `MERGE_STATE`, `STALENESS`, `CONTESTED_FILES`,
`SYMBOL_COLLISIONS`.

```text
You are assessing whether a pull request SHOULD exist and is an improvement, not
whether it is internally correct (other agents cover correctness). Most changes in
this repo are AI-authored, so do not assume the change was intentional or ideal.

PR title: {PR_TITLE}
PR body:  {PR_BODY}
Changed files: {CHANGED_FILES}
Branch staleness: {STALENESS}
Contested files (also touched by recent/open PRs): {CONTESTED_FILES}
Pre-computed symbol collisions: {SYMBOL_COLLISIONS}
PR diff: {PR_DIFF}

Run these four checks. HARD RULE: every finding MUST cite concrete evidence. If you
cannot cite evidence, DROP the finding; do not downgrade it.

1. Regression / reverted code: does the diff re-add code, config, or patterns that a
   prior commit deliberately removed or reverted? Evidence required: a specific prior
   commit SHA whose removed lines the PR re-adds. Run the forensic scan on EVERY file
   in CHANGED_FILES (a stale-branch regression can live in a file no other PR touched,
   so do NOT limit this check to CONTESTED_FILES). For each file, fetch recent commits
   via `gh api "repos/{OWNER}/{REPO}/commits?path={file}&per_page=30"` (quote the URL
   so the shell does not treat `&` as a background operator), inspect removal/revert
   commits, and compare removed lines to PR additions. STALENESS modulates depth: when
   the branch is stale, raise per_page and look further back in history.
2. Contradicts a recorded decision: does the change reverse something fixed in an ADR
   (docs/architecture/**, docs/ADRs/**), a CHANGELOG entry, or a prior PR review
   comment? Evidence required: the ADR path + section, the CHANGELOG line, or the PR
   comment. When the change renames a tool prefix or config identifier (`mcp__*` names,
   MCP server keys, env var or settings keys), ground truth is the machine-readable
   registration (`.mcp.json`, `settings.json`) and the live runtime, NOT the surrounding
   prose: a rename that reads as internally consistent in docs can still be broken against
   the registry. Resolve the new identifier against the live registration before judging
   the rename correct, and flag a rename whose new name is unregistered as a Regression
   (it breaks every reference at runtime). Evidence required: the registry key the new
   identifier does or does not match.
3. Unjustified churn / scope creep: does each change trace to the PR's stated goal in
   PR_BODY? Evidence required: the stated-goal text plus the specific change that does
   not trace to it.
4. Better-alternative: given the change's goal, is the chosen approach clearly worse
   than a pattern THIS REPO ALREADY USES elsewhere? Evidence required: a path to the
   existing in-repo pattern. You may NEVER propose a hypothetical design.

For docs-only PRs (every changed file is .md/.rst/.txt), run only checks 1 and 2.

A branch being behind base and lacking a file is NOT the same as the PR deleting that file.
If `git diff {BASE_BRANCH}..{HEAD_BRANCH}` shows a file as "deleted" (present in base, absent
from the branch), do NOT flag it as "would be silently deleted by merge" unless that file is
in CHANGED_FILES. A `mergeStateStatus: CLEAN` merge preserves all of base's files regardless
of whether the branch predates them; files absent from the branch but not in CHANGED_FILES
are simply ancestry gaps the branch predates, and the merge keeps them. CHANGED_FILES is the
authoritative source of what the PR will actually change; `git diff base..branch` shows
ancestry, not merge intent. Do not raise the PREMISE verdict on this false positive.

Also surface the pre-computed SYMBOL_COLLISIONS and any open-PR file collisions as
findings.

Emit each finding as (use the check NAME for {check}, not its number: one of
Regression, Contradicts, Churn, BetterAlternative, Collision):
  [Critical|Important|Suggested] Premise/{check}: {finding}. Evidence: {citation}.

Then emit a single verdict line as a JSON object on its own:
  { "verdict": "OK" | "QUESTION" | "HOLD", "headline": "one-line reason" }

Verdict rules (each finding maps to exactly one verdict; when a contradiction could
be either, the explicit-prohibition test decides):
- HOLD: hard evidence the change should not merge as-is: it reintroduces code a cited
  commit removed, or it reverses an ADR whose cited section explicitly prohibits the
  pattern. Staleness biases borderline regressions toward HOLD.
- QUESTION: appropriateness concerns worth a human look but non-blocking: churn, a
  contradiction that is inferred or where the cited ADR does not explicitly prohibit
  the pattern, or a symbol or open-PR collision.
- OK: no premise concern survives the evidence rule.
```

Route Agent M's individual findings through Step 6 confidence scoring and Step 7
deduplication with `agent source: M`. Capture its verdict object as
`PREMISE_VERDICT = {verdict, headline}` for the Step 9 header and the Step 11 handoff.

If Agent M produces no parseable JSON verdict (timeout, agent error, or malformed
output), set `PREMISE_VERDICT = {verdict: "SKIP", headline: "premise gate did not run"}`.
A SKIP verdict renders in the Step 9 report header as a single quiet line and does not
trigger the HOLD confirmation in Step 11.

---

## Step 6: Confidence Scoring (parallel Haiku agents)

For each finding returned by Agents A–M, launch a parallel Haiku agent with:

```text
Score this code review finding on a scale of 0–100.

Finding: {finding description}
File: {file}
Agent source: {A|B|C|D|E|F|G|H|I|J|K|L|M}
PR diff context: {10 lines of diff around the finding}

Scoring rubric:
- 0:  False positive that doesn't survive basic scrutiny, or pre-existing issue
      unrelated to this PR's changes.
- 25: Might be real, hard to confirm. Speculative.
- 50: Verifiably real, but low impact; affects edge cases rarely hit.
- 75: Real and impactful; will affect users or functionality in normal use.
      Or: directly called out in CLAUDE.md.
- 100: Certain, frequent impact. Direct evidence in the diff confirms it.

Anchor examples and caps (small scoring models pattern-match "violates a standard" to
high scores and cluster at round numbers; these constraints correct both):
- 75+ requires user-visible breakage, data loss, dead links shipped by the PR, or a
  hard CLAUDE.md rule violation evidenced in the diff.
- PR-body process hygiene (unchecked acceptance-criteria checkboxes, missing `Fixes #N`
  issue references, description completeness, missing motivation section) is capped at
  49 (Suggested) unless the finding evidences an actual untested code-behavior risk in
  the diff. A statically-verifiable no-op (e.g., a boolean input that is never read,
  default false) is not Critical.
- Doc-nit findings (doc count off-by-one, missing Bash
  permissions allow rule, SKILL.md frontmatter gap, style/vocabulary inconsistency) are
  capped at 65 (Important) unless they break a build, lose data, or violate a hard
  CLAUDE.md rule.
- Severity is impact multiplied by reachability. For code/config/detection content the PR
  ITSELF documents as not-yet-activated (feature-flagged off, awaiting a documented out-of-
  band deploy step, or guarded by an as-yet-undeployed component), a genuine correctness
  defect is at most Important (must-fix-before-activation), not Critical (must-fix-before-
  merge), unless merging itself activates it. A real bug in code that cannot execute yet is
  real but deferred; do not conflate "this is a real bug" with "this blocks merge."
- Cite ONLY rules present verbatim in the provided context. Do NOT invent a project
  rule to justify a tier (e.g., do not claim CLAUDE.md mandates issue references; it
  mandates Conventional Commits and says nothing about issue references).
- If the finding's check is pre-assigned a tier by an Agent prompt in this workflow
  (e.g., Agent J's [Suggested] checks), the score MUST stay within that tier's range
  unless the diff provides direct evidence of higher impact.
- Do not default to the 50 boundary. If torn between Important and Suggested, pick a
  score that reflects the decision, not 50 exactly.

Additional constraint: If the agent source is C (Git History) or D (Prior PR
Comments) AND the finding describes historical context, file churn, or past review
patterns rather than a specific, fixable line in the diff: cap the score at 20
regardless of the rubric above. Two exceptions lift the cap:

1. A C or D finding that cites a specific prior commit SHA where the now-reappearing
   lines were removed or reverted. It is the SHA citation, not the agent source, that
   lifts the cap; vague history churn stays capped regardless.
2. Agent M (source M) findings. Agent M is never a C or D source; its checks are
   evidence-grounded appropriateness judgments that do not fit the "historical context"
   profile the cap targets. The cap does not apply to M.

Return ONLY a JSON object:
{"score": <number>, "rationale": "<one sentence>"}
```

**Tier assignment from score:**

| Score | Tier |
| ----- | ---- |
| 75–100 | Critical |
| 50–74 | Important |
| 25–49 | Suggested |
| 0–24 | Informational |

**Do not discard any finding.** All four tiers appear in the output.
The old practice of dropping findings below 80 does NOT apply here.

---

## Step 7: Deduplicate (Haiku agent)

Pass all scored findings from all agents to a single Haiku agent:

```text
You are deduplicating a list of code review findings from multiple agents.

Findings:
{all findings as JSON array with agent source, file, line, description, score}

Instructions:
- If two findings describe the same issue at the same location, keep the
  one with the higher score. Add both agent names as sources.
- If two findings describe related but distinct aspects of the same issue,
  keep both but mark them as related.
- Do not merge findings at different files or different lines.
- Preserve all findings; deduplication only removes exact duplicates.

Return a JSON array of deduplicated findings with all original fields preserved.
```

---

## Step 7b: Validate Critical Findings

After deduplication, validate the Critical tier before assembling the final report. This
catches false positives before they reach the user. Validation follows an evidence
ladder: cheaper, more authoritative evidence first; cross-model consensus only for what
remains.

**Evidence precedence (apply in order; stop as soon as a Critical finding is resolved):**

1. **Empirical evidence from the PR's own CI run.** The system under review has often
   already executed the disputed code path. Before any model call, check whether the
   PR's own check conclusions, skipped jobs, or step outputs already demonstrate or
   refute the claimed behavior (e.g., "Documentation Links: SKIPPED" on a pull_request
   event proves a boolean gate works). Observed runtime behavior from the head SHA
   outrules model opinion in either direction. Resolve the finding on it and skip the
   consensus call for that finding.
2. **Empirical local execution (only when the local checkout is already at the PR head
   SHA).** If `git rev-parse HEAD` equals the PR head SHA and a Critical finding is an
   empirical claim (test-plan counts, lint result, build result), run the stated command
   locally with a timeout and use the result as authoritative. This is a deliberate,
   read-only exception to "no local checkout for review": running a command on an
   already-matching checkout does not touch the working tree. Never check out the PR to
   create this condition; only use it when it already holds.
3. **Primary-source verification for third-party-tool and cross-repo claims.** When a
   Critical finding (or a bot-reviewer concern) hinges on the runtime semantics of a
   third-party action or tool (python-semantic-release, sigstore, actions/checkout) or
   on state outside the diff (another repo's file names, an external convention, remote
   config), spawn a `research-agent` to verify against the tool's documentation or
   source, or `gh api`-dereference the external state, BEFORE consensus scoring.
   Doc-verified or directly-checked evidence overrides agent confidence in both
   directions. Crucially: when multiple agents converge on a finding whose correctness
   depends on state outside the diff, that agreement is NOT independent confirmation
   (the agents share the same evidence boundary). Verify the external fact directly and
   weight convergence as zero additional evidence; a clarifying-comment suggestion may
   survive, but the "bug" framing must not. This verification gate keys on the TYPE of
   claim, not the source's provenance: a technical claim about tool/runtime/library
   semantics (or about state outside the diff) from one of THIS workflow's own dispatched
   subagents (Agents A-M) gets the same authoritative-doc / direct-check verification that
   Step 8 applies to bot review comments, BEFORE it is tiered Critical or Important. An
   agent you dispatched is as capable of a confident, plausible, wrong claim as an external
   bot; trusting your own subagents more than bots is an unjustified asymmetry that lets
   false positives in through the side door.
4. **Cross-model consensus (7b-1 / 7b-2 below)** for Critical findings still unresolved
   after steps 1-3.

**Before the consensus call, extract a 15-line diff context window for each remaining
Critical finding.** Locate its `file` and `line` in `PR_DIFF` and capture lines
`[line - 7 .. line + 7]` (clamped to file boundaries) so models assess the actual code,
not just the description.

### 7b-1. Cross-model false-positive filter (Critical findings unresolved by the ladder)

If any Critical findings (score 75-100) remain after the evidence ladder, validate them
with the `/panel` skill engine (one-shot; replaces the PAL `tiered_consensus` call
that reliably returned setup-only messages with no verdicts):

```bash
cat > /tmp/prreview-consensus-prompt.txt << 'PROMPT'
You are reviewing Critical-tier findings from a PR code review. For each finding,
decide: is this a genuine defect that must be fixed before merge, or is it a false
positive? A false positive is a finding that does not survive scrutiny when you read
the actual code context provided.

Findings (JSON array):
{Critical findings as JSON with finding_id, file, line, description, score, rationale,
 and 15 lines of diff context around the finding}

Return a JSON array; for each finding:
{ "finding_id": N, "verdict": "genuine" | "false_positive", "reason": "one sentence" }
PROMPT

uv run .claude/skills/panel/scripts/consensus_cli.py select \
  --level "$CONSENSUS_LEVEL" --domain code_review > /tmp/prreview-roster.json
uv run .claude/skills/panel/scripts/consensus_cli.py run \
  --prompt-file /tmp/prreview-consensus-prompt.txt \
  --roster-file /tmp/prreview-roster.json --level "$CONSENSUS_LEVEL"
```

Synthesize the per-model responses yourself (do not delegate synthesis to a template):
a finding is `false_positive` only when a majority of succeeded models agree it does not
survive scrutiny.

**Incomplete-response fallback:** If the engine reports `succeeded < 2` (every model
failed, or only one voice returned), note "consensus validation: incomplete
(succeeded < 2); proceeding on independent evidence quality" and continue. Downgrade no
findings on an incomplete response. Do not retry within the same review.

Apply the verdicts: move any finding the panel marks `false_positive` from Critical to
Informational, appending "(consensus: false positive: {reason})" to its rationale.

### 7b-2. Security finding validation (Critical security findings only)

If any Critical finding originates from Agent I (Security Pass) or contains "Security/"
in its description, repeat the 7b-1 engine call with `--domain security` and
`--level 2` (security decisions warrant more model coverage regardless of
`CONSENSUS_LEVEL`), using this prompt:

```text
You are validating security findings from a PR review. For each finding, assess: is
the vulnerability real and exploitable given the code context, or is it a false
positive?

Findings (JSON array):
{Security findings as JSON with finding_id, file, line, description, score, and 20
 lines of diff context}

Return a JSON array; for each finding:
{ "finding_id": N, "verdict": "real" | "false_positive",
  "exploitability": "high" | "medium" | "low" | "theoretical",
  "reason": "one sentence" }
```

If 7b-1 already returned an incomplete response (`succeeded < 2`), skip 7b-2: the same
engine in the same session will near-certainly return the same outcome, and level 2 is
not free. Note the skip.

Apply security verdicts: downgrade `false_positive` security findings from Critical to
Important (not removed, so reviewers still see them). Retain `exploitability` in the
finding rationale: "(consensus security: {exploitability}, {reason})".

---

## Step 8: Wait for Copilot and CodeRabbit Reviews

Before assembling the final report, poll for async reviewer results so that
pr-fix (if selected) can address everything in a single pass.

**Polling target:** Copilot (`copilot-pull-request-reviewer`) and CodeRabbit
(`coderabbitai`) review submissions on the PR.

```bash
# Poll every 30s for up to 5 minutes (10 attempts)
for i in $(seq 1 10); do
  REVIEWS=$(gh api repos/{OWNER}/{REPO}/pulls/{PR_NUMBER}/reviews \
    --jq '[.[] | select(.user.login == "copilot-pull-request-reviewer" or .user.login == "coderabbitai[bot]") | .user.login] | unique')
  COPILOT_DONE=$(echo "$REVIEWS" | grep -c "copilot-pull-request-reviewer" || true)
  CODERABBIT_DONE=$(echo "$REVIEWS" | grep -c "coderabbitai" || true)
  if [ "$COPILOT_DONE" -ge 1 ] && [ "$CODERABBIT_DONE" -ge 1 ]; then
    break
  fi
  sleep 30
done
```

**Bot "green check" can mask a review that never ran.** A passing status check proves a
job completed, not that it did its intended work. Before counting a bot's submission as
coverage, verify the review artifact (a comment body with findings) actually exists. In
particular, when CodeRabbit's check is `SUCCESS`, fetch `issues/{PR_NUMBER}/comments` and
scan the bot's body for rate-limit markers ("Review limit reached", "run out of usage
credits", "rate limited"). If found, report in the Review Status header as
"CodeRabbit: check green but NO review ran (rate-limited)" rather than "Received N
comments". The same caution applies to any bot whose check-run completes independently of
whether its review body has content: check-state and work-done are independent signals.

**When reviews arrive during the window:**

1. Fetch Copilot review comments:
   `gh api repos/{OWNER}/{REPO}/pulls/{PR_NUMBER}/comments`
   and filter by `user.login` IN (`"Copilot"`, `"copilot-pull-request-reviewer"`,
   `"copilot-pull-request-reviewer[bot]"`). The inline-comment author login differs from
   the review-submission login: GitHub authors Copilot INLINE comments under `Copilot`
   (no `[bot]` suffix) while only the review SUBMISSION uses
   `copilot-pull-request-reviewer[bot]`. Filtering on the submission login alone returns
   zero inline comments and silently drops every Copilot finding; always match the
   alternation.
2. Fetch CodeRabbit review comments:
   `gh api repos/{OWNER}/{REPO}/pulls/{PR_NUMBER}/comments`
   and filter by `user.login == "coderabbitai[bot]"`
3. Convert each comment into a finding with:
   - file, line from the comment's `path` and `line` fields
   - description from the comment body
   - agent source: "Copilot" or "CodeRabbit"
4. **Reconcile each bot comment against the PR head SHA before tiering.** Async
   reviewers are pinned to the commit they analyzed, which may be behind head. For each
   bot comment whose `path` is in `CHANGED_FILES`, fetch the head-SHA file context
   (`gh api repos/{OWNER}/{REPO}/contents/{path}?ref={HEAD_SHA}`) and verify the flagged
   issue still exists in current code. Drop or mark "already addressed" any comment that
   does not survive the head-SHA check (a missing-RAD-markers comment where markers are
   now present, a missing-bounds comment where `Field(ge=...)` bounds already exist, an
   "except Exception" comment where the code now uses try/finally). A green CI gate (e.g.
   Ruff passing) is a corroborating signal that lint/catch-all comments are stale. Code
   read at head plus a green gate beats a stale bot comment.
5. **Verify a bot's technical assertion against authoritative docs before treating it as
   actionable.** Automated reviewers post confident, plausible, and sometimes wrong
   claims about a tool's schema or behavior. When a bot comment makes a factual claim
   about tool semantics (e.g., "`open-pull-requests-limit: 0` is invalid for Dependabot"
   when the docs state it is the supported way to disable updates), confirm it against
   the authoritative source (WebFetch the relevant docs) before classifying it as a fix
   item. If the claim is false, classify the comment as "Declined: false positive" with
   the doc citation rather than forwarding a wrong fix into the queue. Apply Agent J's
   "verify before include" posture to qualitative bot claims, not just quantitative ones.
6. Run each surviving comment through the same confidence scoring as Step 6
7. Merge into the existing `FINDINGS` list and deduplicate (Step 7)

**Stale PR description detector:**

After processing bot review comments, compute the set difference between each bot
comment's `path` field and `CHANGED_FILES`. For any comment whose `path` is NOT in
`CHANGED_FILES`, emit:

```text
[Important] PRNarrowed: Reviewer {bot} commented on {path}, which is not in the
current diff. The PR was likely narrowed since that review. Verify the PR
description still matches the current diff scope.
```

Additionally, scan the branch commit subjects (already fetched for the commit-type
check) for removal verbs: "remove", "drop", "revert", "strip ... from PR". When
found alongside PR body claims of those artifacts, emit:

```text
[Important] PRDesc: Branch commit history shows "{verb} {artifact} from PR"; PR
description may overstate current deliverables.
```

**Timeout behavior:**

- If both arrive: proceed with full findings
- If only one arrives: proceed, note the missing reviewer in the report header
  (e.g., "CodeRabbit: review pending, not included in this pass")
- If neither arrives: proceed without them, note both as pending
- If Copilot was not successfully requested in Step 1: do not wait for it
- If the repo has no CodeRabbit app installed (no prior `coderabbitai` reviews
  in the repo): do not wait for it

The goal is to give pr-fix a complete picture on the first pass, eliminating
the push-then-react-to-new-comments cycle.

---

## Step 9: Assemble and Output Report

Present the following report in the terminal. Do NOT post to GitHub
automatically; the user can decide whether to post.

```markdown
# PR Review: {PR_TITLE}
{OWNER}/{REPO}#{PR_NUMBER} | {BASE_BRANCH} ← {HEAD_BRANCH}
{DRAFT WARNING if isDraft}
**PREMISE {PREMISE_VERDICT.verdict}: {PREMISE_VERDICT.headline}**

## Review Status
- **GitHub Copilot**: {Received N comments / Pending (timed out) / Failed}
- **CodeRabbit**: {Received N comments / Pending (timed out) / Not installed}
- **SonarQube Issues**: {N} queued for auto-fix
  *(PR-specific / branch-level / not configured / placeholder config detected)*
  Severity: Blocker: {N} | Critical: {N} | Major: {N} | Minor: {N} | Info: {N}
- **SonarQube Hotspots**: {M} queued for review *(omit line if M = 0)*
  Probability: HIGH: {N} | MEDIUM: {N} | LOW: {N}
- **CI checks**: {N} failing / all passing / BUILD FAILING (if Critical CI findings exist)
- **Agents run**: {list of agents that fired}
- **Agent findings**: {N} ({critical} Critical, {important} Important,
  {suggested} Suggested, {informational} Informational)

---

## Review Agent Findings ({N})

### Critical (must fix before merge)
- **[{agent}]** `{file}:{line}`: {description}
  *(Score: {score}: {rationale})*

### Important (should fix)
- **[{agent}]** `{file}:{line}`: {description}
  *(Score: {score}: {rationale})*

### Suggested (consider addressing)
- **[{agent}]** `{file}:{line}`: {description}
  *(Score: {score}: {rationale})*

### Informational (noted, low priority)
- **[{agent}]** `{file}:{line}`: {description}
  *(Score: {score}: {rationale})*

---

## Recommended Action

1. {First action, starting with Critical fixes}
2. {Second action}
...

---

## Post to GitHub?

To post this review as a PR comment, run:
  /pr-review post
Or confirm now and I will post it immediately.
```

---

Render a `HOLD` premise verdict with the same prominence as `BUILD FAILING`. An `OK`
verdict may render as a single quiet line. A `SKIP` verdict renders as a single quiet
line: "PREMISE SKIP: premise gate did not run." Individual premise findings from Agent M
appear in their scored tiers above, like any other agent's findings.

---

## Step 10: Next Steps Prompt

After the report is output, present exactly these options. Do not add
explanation; keep the prompt concise.

```text
Review complete. What would you like to do?

1. Post review to GitHub only
2. Run /pr-fix (gathers CI failures, review comments, SonarQube, coverage,
   and agent findings; fixes all in an isolated worktree)
3. Post to GitHub, then run /pr-fix
4. Done, no further action

Which option?
```

Do not proceed until the user responds. Record the choice as `NEXT_ACTION`.

---

## Step 11: Execute Next Steps

### Option 1 or 3: Post to GitHub

Get the HEAD commit SHA:

```bash
gh pr view "$PR_NUMBER" --repo "$OWNER/$REPO" --json headRefOid \
  --jq '.headRefOid'
```

Post the condensed review comment:

```bash
gh pr comment "$PR_NUMBER" --repo "$OWNER/$REPO" --body "$(cat <<'EOF'
### PR Review

{condensed report: Critical and Important findings only, with full
SHA-anchored file links:
https://github.com/{OWNER}/{REPO}/blob/{HEAD_SHA}/{file}#L{start}-L{end}}

{SonarQube summary line if findings exist}

{If COPILOT_STATUS=0: "Copilot review requested; see Reviewers section for results." Else: "Copilot review request failed; request manually via GitHub UI."}

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

Use the full 40-character SHA in every file link. Never use branch names;
they are mutable.

**Re-verify volatile state immediately before posting.** Findings about volatile PR state
(mergeability, head SHA, CI conclusions) have a short shelf life on actively-maintained PRs
and an even shorter one on bot-authored PRs that auto-rebase. The lag between analysis and
posting is enough for an automated agent to invalidate a conflict finding. When the PR author
is a known auto-rebasing bot (renovate, dependabot), re-fetch `headRefOid`,
`mergeStateStatus`, and `mergeable` right before posting; if a conflict finding has self-
resolved (now CLEAN/MERGEABLE), drop or soften it. Where a conflict finding is still emitted
on a bot PR, annotate it: "this bot auto-rebases its branches; the conflict may clear without
manual action."

After posting, if `NEXT_ACTION` is 3, continue to the fix workflow below.
If `NEXT_ACTION` is 1, stop here.

### Option 2 or 3: Run /pr-fix

If `PREMISE_VERDICT.verdict` is `HOLD`, interpose one confirmation before loading the
fix workflow:

```text
Premise gate flagged HOLD: {PREMISE_VERDICT.headline}.
/pr-fix would polish a change whose existence is in question.
Proceed with the fix anyway? (y/N)
```

Do not proceed to pr-fix unless the user confirms. If they decline, stop here.

Load `workflows/pr-fix.md` and execute it. Pass forward:

- `OWNER`, `REPO`, `PR_NUMBER`
- `HEAD_BRANCH` (the branch to check out in the worktree)
- `FINDINGS`: the full deduplicated, scored findings list from Step 7
- `SONAR_FINDINGS`: SonarQube findings from Step 4 (if any)
- `SONAR_HOTSPOTS`: security hotspots from Step 4f (if any)
- `PREMISE_VERDICT`: the Agent M verdict object `{verdict, headline}` from Step 5

The pr-fix workflow runs its own gather step for CI check failures,
review comments, and Codecov status (data that pr-review did not collect),
supplementing the FINDINGS and SONAR_FINDINGS already in context.

---

## Error Handling

| Situation | Action |
| --------- | ------ |
| `gh` not authenticated | Stop. Print: "Run `gh auth login` first." |
| PR not found | Stop. Verify the URL and repo access. |
| PR is closed | Stop. Note: "PR #{number} is closed. Provide an open PR URL." |
| PR is draft | Continue with a warning banner in the report header. |
| Copilot reviewer add fails | Log "Copilot: request failed; add manually via GitHub UI." Continue. |
| SonarQube MCP unreachable | Try the SonarCloud REST fallback (Step 4a) with `SONARQUBE_TOKEN` before skipping. Only if REST also fails: log "SonarQube: MCP offline and REST unreachable." Continue. |
| SonarQube project not found | Log "SonarQube: project not configured for this repo." Continue. |
| Large PR (> 500 lines) | See large-PR handling strategy in Step 5; never silently truncate. |
| Agent returns no findings | Include: "{Agent}: No issues found." in the relevant tier section. |
