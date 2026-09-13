# PR metadata: fetch, staleness, overlap, and supersession

This covers the detailed procedure for Step 2 (Fetch PR Metadata, including the
2c CI-status sub-procedure), Step 2d (Branch staleness), Step 2e (PR-overlap
targeting), and Step 2f (Supersession pre-check) of `workflows/pr-review.md`.
The spine keeps each `## Step 2...` heading with a short orchestration stub;
the full procedure for each lives here.

For the shared GitHub API idioms this content depends on (mergeStateStatus
settle-and-reject, renamed-file detection via REST `previous_filename`,
bot-login matching), see
[context/github-api-idioms.md](../context/github-api-idioms.md); this file
keeps its own text and only points at the shared file where content
overlaps.

---

## Step 2 detail: Fetch PR Metadata

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

Store as `CI_CHECKS`. GitHub's check `state` is not a two-value success/failure
signal: besides `SUCCESS`, `PENDING` (queued or in progress) and `EXPECTED`
(a required context that has not started yet, functionally the same as
PENDING for this purpose) are not-yet-decided, and `NEUTRAL` and `SKIPPED` are
decided-but-not-a-failure (a condition legitimately did not apply, or a job
was intentionally skipped, e.g. by a path filter). Treating any of these five
as "failing" manufactures a false CI finding on a check that never actually
failed. Classify a check as failing, and run the branch-state logic below,
only when `state` is one of: `FAILURE`, `ERROR`, `ACTION_REQUIRED`,
`CANCELLED`, `STALE`, `TIMED_OUT`, `STARTUP_FAILURE`. Everything else
(`SUCCESS`, `PENDING`, `EXPECTED`, `NEUTRAL`, `SKIPPED`) skips this branch
entirely; `EXPECTED` specifically is handled separately by the
phantom/never-reported check below, which is where a required context stuck
at `EXPECTED` forever belongs, not here.

**Required-vs-non-required tiering (decide tier before branch-state attribution).**
A failing check is a fact; whether it BLOCKS merge is a separate fact, and the tier
should follow the second. Before assigning a tier, determine whether the failing check
is a required status context. A check failing on an `UNSTABLE` (mergeable) PR is
non-required and does not block merge; only `BLOCKED`, or membership in
branch-protection `required_status_checks`, indicates a gate that does. Fetch the
required set once:

```bash
REQUIRED=$(gh api "repos/$OWNER/$REPO/branches/$BASE_BRANCH/protection/required_status_checks/contexts" \
  2>/dev/null | jq -r '.[]')
if [ -z "$REQUIRED" ]; then
  # The rulesets LIST endpoint returns only summary fields (id, name, target,
  # enforcement); it has no `rules`/`parameters`, so a jq scan against it can
  # never find `required_status_checks`. Fetch each branch ruleset's detail
  # endpoint and read the field at its actual nested path:
  # .rules[] where .type == "required_status_checks", then
  # .parameters.required_status_checks[].context.
  REQUIRED=$(gh api "repos/$OWNER/$REPO/rulesets?targets=branch" --jq '.[].id' 2>/dev/null \
    | while read -r rid; do
        gh api "repos/$OWNER/$REPO/rulesets/$rid" 2>/dev/null \
          --jq '.rules[]? | select(.type=="required_status_checks") | .parameters.required_status_checks[].context'
      done)
fi
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
  remediation is a re-run, not a code change. A docs-only diff that fails a
  code-analysis check (Bandit, SonarCloud, security-analysis) is a strong tell for
  this class, since such a diff cannot cause that failure. A config-only diff is
  NOT automatically in this class: it can change the analysis tool's own settings,
  workflow inputs, dependencies, or scan paths, any of which can cause a real
  failure; only treat a config-only diff as a tell when the changed file is
  unrelated to the failing analysis tool's configuration or inputs. (CodeQL was
  retired fleet-wide 2026-09; it should no longer appear as a check at all, see
  ci-fix guidance on legacy SARIF/code-scanning checks.)
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

## Step 2d detail: Branch staleness (parallel with Step 2c)
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

## Step 2e detail: PR-overlap targeting (parallel with Step 2c)
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

### Dimension 3: filename-derived identity keys

Path overlap and symbol overlap both miss a third collision class: two PRs adding DIFFERENT
files to the same directory whose framework derives an identity key FROM the filename rather
than from its content (migration directories are the canonical case, but any append-only,
sequentially-numbered artifact directory qualifies). Two files with distinct paths and no
shared symbol name can still collide on the derived key once both land, and the collision is
invisible to both prior dimensions because neither compares paths across PRs. When
`CHANGED_FILES` adds a file to such a directory, list sibling filenames on `BASE_BRANCH` and
on each PR in the comparison set, extract the derived key from each (the leading sequence
number, timestamp, or ID segment the framework actually parses), and compare keys, not paths.
Record a match as a `SYMBOL_COLLISIONS`-shaped entry so Agent M emits it through the same
`Premise/Collision` path.

### Merge order, not just a warning

A collision finding that names two colliding PRs but not an order is only half useful: when
this step runs across a batch of open PRs (multiple `/pr-review` passes, or a user asking
"what order should these merge in"), emit a recommended merge order alongside each collision,
with the reason per edge, for example "land #{n} first: it owns the shared definition/copy
that this PR would otherwise duplicate." Working a colliding batch in the right order can
reduce a semantic conflict to a positional one (a change that becomes a clean no-op once the
PR it depended on has already landed); working it in the wrong order can force the same
conflict to be resolved twice. Also flag any contested artifact that cannot be three-way
merged (pixel baselines, generated lockfiles, generated clients): those force a
regenerate-after-both-land constraint regardless of order.

### Scale the lookback to branch staleness

`PREMISE_MERGED_PR_LOOKBACK` is a fixed count (default 10) applied uniformly regardless of how
stale the current branch is. A branch that has been open and diverging for weeks needs a
longer merged-PR lookback than a same-day branch, because the fixed default window can slide
past merges the stale branch never saw, silently narrowing the comparison set exactly when
staleness makes a collision most likely. Scale the effective lookback by `STALENESS.age_days`
(Step 2d) before running the merged-PR query: widen `--limit` proportionally, or switch to a
date-bounded query (merged PRs since the branch's divergence date) rather than a fixed count,
when `age_days` exceeds `PREMISE_STALENESS_HOLD_DAYS`.

---

## Step 2f detail: Supersession pre-check (only when MERGE_STATE is DIRTY or BEHIND)
For a stale PR, the first question is "does the base branch already contain this?" not
"is this code good?" A byte-level comparison against the base costs a couple of git
commands and can invalidate the entire premise of the review before the agent fleet
runs. Skip this step when `MERGE_STATE` is `CLEAN` (the up-to-date-with-base state;
`mergeStateStatus` has no `MERGEABLE` value, that belongs to the separate `mergeable` field).

This workflow never checks the repo out locally (see Design Principles in
`SKILL.md`); `git diff` against `origin/$BASE_BRANCH` assumes a local clone
with that ref fetched, which this workflow does not have. Compare content via
the GitHub API instead: fetch each file's blob at both SHAs and diff the
downloaded text, never a local ref.

```bash
BASE_SHA_TIP=$(gh api "repos/$OWNER/$REPO/branches/$BASE_BRANCH" --jq '.commit.sha')
for f in {CHANGED_FILES}; do
  base_content=$(gh api "repos/$OWNER/$REPO/contents/$f?ref=$BASE_SHA_TIP" --jq '.content' 2>/dev/null | base64 -d 2>/dev/null)
  head_content=$(gh api "repos/$OWNER/$REPO/contents/$f?ref=$HEAD_SHA" --jq '.content' 2>/dev/null | base64 -d 2>/dev/null)
  if [ "$base_content" = "$head_content" ]; then
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

**Diff direction between two diverged tips alone is not enough to declare a regression.**
Comparing base tip to head content directly conflates "this branch changed it" with "base
changed it later"; a DIFFERS file on a stale branch can look like it re-adds
deliberately-removed content when in fact the branch never touched the file relative to
the merge-base and a merge would cleanly take base's version. Classify each DIFFERS file
against the merge-base, not against the base branch's current tip, using only `gh api`
(no local `git merge-tree`, which needs a local clone this workflow does not have):

```bash
MERGE_BASE=$(gh api "repos/$OWNER/$REPO/compare/$BASE_BRANCH...$HEAD_SHA" --jq '.merge_base_commit.sha')
BRANCH_CHANGED=$(gh api "repos/$OWNER/$REPO/compare/$MERGE_BASE...$HEAD_SHA" --jq '.files[].filename')
BASE_CHANGED=$(gh api "repos/$OWNER/$REPO/compare/$MERGE_BASE...$BASE_SHA_TIP" --jq '.files[].filename')
```

For a DIFFERS file `f`:
- `f` is in `BASE_CHANGED` but NOT in `BRANCH_CHANGED`: (c) merely-behind-base, a
  non-finding; the branch never touched this file since diverging, and a merge cleanly
  takes base's version (this is what the byte-content comparison above already flagged as
  DIFFERS, since base moved but the branch did not).
- `f` is in `BRANCH_CHANGED` but NOT in `BASE_CHANGED`: the branch is the only side that
  touched the file since the merge-base; a genuine regression would require base to have
  since removed something the branch re-adds, which cannot be true here. Non-finding for
  this check (Agent M's own regression scan, Step 5, still covers this file independently).
- `f` is in BOTH: both sides touched the file since diverging. This is bucket (a) or (b),
  a genuine conflict or regression candidate; hand it to Agent M's per-commit regression
  scan (Step 5) rather than resolving it here, since distinguishing "branch re-adds
  something base deliberately removed" from "both made unrelated, compatible edits"
  needs the line-level commit history Agent M already fetches.

Only (a) and (b) are actionable; (c) is a non-finding.
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
