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
PANEL_MODELS:          ["google/gemini-2.5-pro-preview", "openai/gpt-4o"]  # DRIFTED, see note below
CONSENSUS_LEVEL:       1
PREMISE_MERGED_PR_LOOKBACK:   10
PREMISE_STALENESS_HOLD_DAYS:  14
```

**`PANEL_MODELS` is flagged, not fixed.** `google/gemini-2.5-pro-preview` is stale against
standing guidance to avoid `-pro` model variants (`feedback_no_pro_models`); `openai/gpt-4o`
is not a `-pro` variant, but is stale for a separate reason, it predates OpenAI's current
flagship line and has not been re-verified as the best available cross-vendor choice. Neither
ID has been re-verified against the live OpenRouter roster, which churns independently of this
file. This was caught, not corrected: substituting a name from training data or from memory
carries the same risk as leaving the stale value in place, because an unverified replacement
can be just as wrong as the value it replaces, only more confidently wrong. Do not silently
swap in a plausible-looking model ID here. Before the next run that reaches Agent L, re-derive
the roster live (`pal listmodels`, or the `/panel` skill's own roster listing) and pick the two
highest-scoring non-pro, cross-vendor models, or bring the drift to the user as an explicit
decision. Leaving a flagged stale value beats asserting an unverified one as settled.

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

Fetch PR title/body/state/labels/branches/head SHA, the full diff, and the changed-file
list; then evaluate CI status (2c) against required-check membership and branch-state
attribution.

**Consumes:** `OWNER`, `REPO`, `PR_NUMBER` from Step 0.

**Produces:** `PR_TITLE`, `PR_BODY`, `BASE_BRANCH`, `HEAD_BRANCH`, `MERGE_STATE`,
`HEAD_SHA`, `PR_DIFF`, `CHANGED_FILES`, `CI_CHECKS`, and any CI-derived report-header
banners (`BUILD FAILING`, `BRANCH BEHIND`, transient-infrastructure note).

**Decisions the caller must make:** abort on `CLOSED` state; continue with a draft
warning on `isDraft`; retry once on an unsettled `mergeStateStatus` (`UNKNOWN`) before
defaulting conservatively to `BEHIND`; for each failing check, tier it by required-vs-
non-required membership, then by branch-state attribution (pre-existing on base,
transient infrastructure, or PR-introduced), including the phantom/never-reported
required-check case and the dangling-submodule case.

For the shared `mergeStateStatus` settle-and-reject idiom this step depends on, see
[context/github-api-idioms.md](../context/github-api-idioms.md).

**Full procedure (orchestrator runs this step; read when you reach it, not before):** [context/pr-metadata.md](../context/pr-metadata.md)

---

## Step 2d: Branch staleness (parallel with Step 2c, [context/pr-metadata.md](../context/pr-metadata.md))

Compute two objective staleness signals from the base/head compare: commits-behind
count and divergence age in days.

**Consumes:** `BASE_BRANCH`, `HEAD_BRANCH`.

**Produces:** `STALENESS = {commits_behind, age_days}`, consumed by Agent M (Step 5) as
a scan-intensity dial and a HOLD bias on confirmed regressions.

**Decision the caller must make:** non-blocking; on a failed compare call, default to
`{commits_behind: 0, age_days: 0}` and note staleness as unavailable rather than
blocking the workflow.

**Full procedure (orchestrator runs this step; read when you reach it, not before):** [context/pr-metadata.md](../context/pr-metadata.md)

---

## Step 2e: PR-overlap targeting (parallel with Step 2c, [context/pr-metadata.md](../context/pr-metadata.md))

Compare the current PR's changed files and newly-added symbols against recent merged
and open PRs, along two dimensions: file-path overlap and symbol overlap.

**Consumes:** `CHANGED_FILES`, `PREMISE_MERGED_PR_LOOKBACK`.

**Produces:** `CONTESTED_FILES` (file/overlapping_pr/pr_state/merged_at records) and
`SYMBOL_COLLISIONS`, both passed to Agent M (Step 5) for finding emission; do not emit
the collision finding directly from this step, Agent M is the sole emitter.

**Decision the caller must make:** classify each file overlap as a staleness/silent-
revert risk (merged PR postdating merge-base) or a collision/duplicate-work risk (open
PR); apply the dunder/`test_*`/hook-name exclusions before treating a symbol match as a
collision.

**Full procedure (orchestrator runs this step; read when you reach it, not before):** [context/pr-metadata.md](../context/pr-metadata.md)

---

## Step 2f: Supersession pre-check (only when MERGE_STATE is DIRTY or BEHIND)

For a stale PR, determine whether the base branch already contains the change before
running the full agent fleet.

**Consumes:** `MERGE_STATE`, `CHANGED_FILES`, `HEAD_SHA`, `BASE_BRANCH`.

**Produces:** a per-file IDENTICAL/DIFFERS classification, and for DIFFERS files a
merge-base-aware three-way classification (genuine conflict, branch-regresses-base, or
merely-behind-base).

**Decision the caller must make:** skip entirely when `MERGE_STATE` is `CLEAN`; when
most files are IDENTICAL, short-circuit to a superseded-PR report with a residual
salvage list instead of spawning the full agent fleet; only genuine conflicts and
branch-regresses-base findings are actionable, a merely-behind-base file is a
non-finding.

**Full procedure (orchestrator runs this step; read when you reach it, not before):** [context/pr-metadata.md](../context/pr-metadata.md)

---

## Step 3: Classify Changes (Haiku agent)

Analyze `CHANGED_FILES` and the first 50 lines of `PR_DIFF` to decide which review
agents activate and how much effort scales to the diff's surface.

**Consumes:** `CHANGED_FILES`, `PR_DIFF`.

**Produces:** the agent-activation set (which of Agents B-M fire), the docs-only,
lockfile-only, and trivial-change fast-path decision, size classification (Small,
Medium, Large), and any rename/path-boundary findings emitted before agent spawn.

**Decision the caller must make:** apply the docs-only and generated-lockfile-only
skip rules before the trivial-change fast path; do not read "report everything" as
"spawn every agent" on a near-zero-surface diff; verify config/infra behavioral
guarantees and reusable-workflow ref reachability where applicable.

For the shared renamed-file detection idiom (REST `previous_filename`, not GraphQL),
see [context/github-api-idioms.md](../context/github-api-idioms.md).

**Full procedure (pass this path to the dispatched agent in its brief; the orchestrator does not read it):** [context/change-classification.md](../context/change-classification.md)

---

## Step 4: Fetch SonarQube Findings (parallel with Step 5)

Detect the SonarCloud organization and project key, fetch PR-specific (falling back to
branch-level) issues and security hotspots, run the placeholder-config pre-flight
check, and detect the Qlty commit-status quality gate.

**Consumes:** repo owner/name, `HEAD_BRANCH`, `PR_NUMBER`.

**Produces:** `SONAR_FINDINGS`, `SONAR_HOTSPOTS` (stored for the fix workflow, not
included in the review report body), and the Qlty issue count with its `target_url`.

**Decision the caller must make:** route to the correct MCP tool prefix by org; fall
back to the SonarCloud REST API (with `SONARQUBE_TOKEN`) before skipping Sonar
entirely when the MCP server is unreachable; never let an un-enumerable Qlty queue
silently imply full coverage.

For the shared "unreachable MCP server is not an empty result set" idiom, see
[context/github-api-idioms.md](../context/github-api-idioms.md).

**Full procedure (orchestrator runs this step; read when you reach it, not before):** [context/quality-gates.md](../context/quality-gates.md)

---

## Step 5: Run Parallel Review Agents

Launch all applicable agents (per Step 3's activation set) simultaneously via the
Agent tool, each with its context inline.

**Consumes:** `PR_DIFF`, `CHANGED_FILES`, `CONTEXT_FILES` (full file content fetched
for files with more than 10 changed lines), `MERGE_STATE`, `STALENESS`,
`CONTESTED_FILES`, `SYMBOL_COLLISIONS`.

**Produces:** raw findings from Agents A (CLAUDE.md compliance), B (bug scan), C (git
history), D (prior PR comments), E (comment accuracy), F (silent failure/error
handling), G (test coverage), H (type design), I (security), J (PR description vs
diff), K (performance), L (architectural review via flexible panel), and M (premise
and regression gate, always active); Agent M also produces `PREMISE_VERDICT =
{verdict, headline}`.

**Decision the caller must make:** choose a large-PR handling strategy (per-file
chunking vs. hard stop at 500 lines) before spawning agents when the diff exceeds 500
lines; never silently truncate; instruct every agent not to dismiss findings as
trivial, since confidence scoring happens downstream in Step 6.

**Full procedure (pass this path to the dispatched agent in its brief; the orchestrator does not read it):** [context/review-agents.md](../context/review-agents.md)

**Execution hygiene applies to every shell command this workflow or its dispatched agents
run, not only the one block that currently quotes defensively** (the `&`-in-URL guard on
Agent M's commit-history fetch in [context/review-agents.md](../context/review-agents.md)).
Quote every variable interpolated into a `bash` command (`"$VAR"`, not `$VAR`) and every URL
containing `&`, `?`, or spaces; an unquoted expansion that is empty, multi-word, or contains a
shell metacharacter changes what actually runs, not just how it looks.

A sharper edge in the same family: **never use `pkill -f <pattern>` (or `pgrep -f`,
`killall`) from an orchestrator or dispatched agent shell.** `-f` matches against the FULL
command line, not just the process name, so a pattern that also appears in the invoking
shell's own command string (a heredoc, a quoted argument, the wrapper's own invocation) makes
`pkill -f` SIGTERM its own session before it ever reaches the intended target. This has
actually happened: a review agent starting a background test server and later killing it by
name-pattern matched its own shell and hung for over half an hour with no target actually
stopped. Kill by numeric PID only: capture it at spawn time (`cmd & pid=$!`) and kill that
(`kill "$pid"`), or resolve the PID via `ps`/`jobs -p` immediately before killing, never via a
loose pattern match.

---

## Step 6: Confidence Scoring (parallel Haiku agents)

Score every finding from Agents A-M on a 0-100 scale using a fixed rubric, then map
the score to a tier.

**Consumes:** all raw findings from Step 5, with a 10-line diff context window around
each.

**Produces:** a score and rationale per finding; tier assignment (Critical 75-100,
Important 50-74, Suggested 25-49, Informational 0-24) for the Step 9 report.

**Decision the caller must make:** apply the anchor examples and caps (PR-body process
hygiene capped at 49, doc-nit findings capped at 65, reachability-discounted findings
capped at Important) and the Agent C/D historical-context cap (20, lifted only by a
cited commit SHA or by Agent M's source); do not discard any finding regardless of
tier.

**Full procedure (pass this path to the dispatched agent in its brief; the orchestrator does not read it):** [context/finding-validation.md](../context/finding-validation.md#step-6-detail-confidence-scoring-parallel-haiku-agents)

---

## Step 6b: Clamp Confidence Scores

Mechanically enforce the caps that Step 6 only asks the scoring subagent to honor.
**This step is orchestrator-executed, not a subagent call:** run the filter below
directly, on the same JSON findings array that passes from Step 6 into Step 7. A
rubric hint in a Haiku agent's prompt is not an enforcement mechanism; this step is
the enforcement, independent of whether the Step 6 subagent applied its own cap.

**Consumes:** the scored findings array from Step 6 (`agent source, file, line,
description, score`, the same shape Step 7's dedup prompt receives below).

**Produces:** the same array with two caps mechanically applied: any process-hygiene
finding (Agent J's PR-body checks: unchecked acceptance-criteria checkboxes, missing
`Fixes #N` reference, missing motivation section, "changed but not mentioned in
description") scored above 49 is clamped to 49; any doc-nit finding (doc count
off-by-one, missing Bash permission allow rule, SKILL.md frontmatter gap, style or
vocabulary inconsistency) scored above 65 is clamped to 65.

**Decision the caller must make:** none. This is a mechanical, non-optional check:
run the filter, use its output as Step 7's input, and do not substitute judgment for
it regardless of what the Step 6 scoring agent returned.

```bash
jq '[.[] | if (.description | test("PRDesc: (Missing motivation section|Bug fix PR does not reference an issue number|changed but not mentioned in description|acceptance.criteria)"; "i")) then .score = ([.score, 49] | min) elif (.description | test("doc count|off-by-one|Bash permission|SKILL\\.md frontmatter|style/vocabulary|vocabulary inconsistency"; "i")) then .score = ([.score, 65] | min) else . end]' findings.json
```

Running this filter on an already-compliant array is a no-op; running it on a
subagent that ignored the Step 6 caps is what actually enforces them.

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

After Step 7's deduplication, validate the Critical tier before the report is
assembled, to catch false positives before they reach the user.

**Consumes:** deduplicated Critical-tier findings (score 75-100) with a 15-line diff
context window per finding.

**Produces:** resolved or downgraded Critical findings (moved to Informational or
Important with a rationale appended); an updated `FINDINGS` list.

**Decision the caller must make:** apply the evidence ladder in order, stop as soon as
a finding resolves: empirical CI evidence first, then empirical local execution (only
when the checkout already matches `HEAD_SHA`), then primary-source verification for
third-party-tool and cross-repo claims, and only then cross-model consensus via the
`/panel` skill engine (7b-1 for general Critical findings, 7b-2 at level 2 for security
findings from Agent I). Treat convergence among your own dispatched agents as zero
additional evidence when their claim depends on state outside the diff.

**Full procedure (orchestrator runs this step; read when you reach it, not before):** [context/finding-validation.md](../context/finding-validation.md#step-7b-detail-validate-critical-findings)

---

## Step 8: Wait for Copilot and CodeRabbit Reviews

Before assembling the final report, poll for async reviewer results so that
pr-fix (if selected) can address everything in a single pass.

**Polling target:** Copilot and CodeRabbit review submissions on the PR. Match
Copilot with the full alternation described in the "Bot login suffix" note below,
not the bare `copilot-pull-request-reviewer` string: review submissions arrive as
`copilot-pull-request-reviewer[bot]`, so an exact-equality filter on the
unsuffixed login matches nothing and the poll can never succeed.

```bash
# Poll every 30s for up to 5 minutes (10 attempts)
for i in $(seq 1 10); do
  REVIEWS=$(gh api repos/{OWNER}/{REPO}/pulls/{PR_NUMBER}/reviews \
    --jq '[.[] | select(.user.login | test("^(Copilot|copilot-pull-request-reviewer(\\[bot\\])?|coderabbitai(\\[bot\\])?)$")) | .user.login] | unique')
  COPILOT_DONE=$(echo "$REVIEWS" | grep -ci "copilot" || true)
  CODERABBIT_DONE=$(echo "$REVIEWS" | grep -ci "coderabbitai" || true)
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

**The Review Coverage and External Claims Dereferenced blocks below are required
report fields, not optional decoration. Assembling and emitting the final report
without either block is a failure of this step, full stop: a bot's green check or
empty result is exactly as consistent with "the review never ran" (rate-limited,
scope-excluded, never-analyzed branch) as with "the review ran and found nothing,"
and this step exists to stop conflating the two. If a Review Coverage row cannot be
populated from data already gathered earlier in this run (Step 1's Copilot check,
Step 4's Sonar fetch, Step 5's agent dispatch, Step 8's bot polling), go gather it
before emitting the report; do not emit a row you did not verify and do not omit the
row. If the External Claims table cannot be confirmed as run (Agent J item 7, from
Step 5), go confirm it before emitting the report. Refuse to output the report until
both blocks are populated from data actually gathered, not inferred or guessed.**

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

## Review Coverage (required; do not omit)
*A count of what was actually examined, not a pass/fail label. A reviewer or gate
that never ran gets a row reading `0` with a `never ran` reason, never an omitted
row: an omitted row is indistinguishable from a clean pass, which is the exact
failure this block exists to close.*

| Reviewer / Gate | Examined | Status |
| --- | --- | --- |
| GitHub Copilot | {N review comment bodies fetched} | {ran / never ran / rate-limited / timed out} |
| CodeRabbit | {N review comment bodies fetched} | {ran / never ran / rate-limited / timed out} |
| SonarQube Issues | {N issues fetched from the queried project/PR} | {ran / not configured / MCP+REST both unreachable} |
| SonarQube Hotspots | {M hotspots fetched} | {ran / not configured / MCP+REST both unreachable} |
| CI checks | {N checks enumerated via gh pr checks} | {ran / unavailable} |
| Agent {A..M, one row per agent Step 3 activated} | {N steps executed, or N findings emitted, whichever this run actually produced} | {completed / timed out / errored / skipped by Step 3} |

---

## External Claims Dereferenced ({N})
*Required. Agent J item 7 (Step 5) dereferences external citations found in the PR
body or diff, token scopes, regulatory citations, log-level claims, a generated
artifact's provenance, against live state. This table's presence is mandatory even
when it is empty: an empty table ("No external claims found in PR body or diff.")
is a valid, complete result. A MISSING table means the check never ran, and must
never be reported as if nothing was found.*

| Claim | Location | Retrieval method | Result |
| --- | --- | --- | --- |
| {quoted external claim} | {file:line, or "PR body"} | {gh api path / doc fetch / other command actually run} | {confirmed / contradicted: actual value} |

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

Render a `HOLD` premise verdict with the same prominence as `BUILD FAILING`. Render an
`UNRESOLVED` verdict (Agent M produced no parseable verdict after one retry) with that
same prominence: its outcome is unknown, not clean, and must fail closed like `HOLD`,
not fail open like `SKIP`. An `OK` verdict may render as a single quiet line. A `SKIP`
verdict renders as a single quiet line: "PREMISE SKIP: premise gate did not run."
Individual premise findings from Agent M appear in their scored tiers above, like any
other agent's findings.

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

If `PREMISE_VERDICT.verdict` is `HOLD` or `UNRESOLVED`, interpose one confirmation
before loading the fix workflow (an `UNRESOLVED` verdict means Agent M's outcome is
unknown, not clean, and gates identically to a confirmed `HOLD`):

```text
Premise gate flagged {PREMISE_VERDICT.verdict}: {PREMISE_VERDICT.headline}.
/pr-fix would polish a change whose existence is in question.
Proceed with the fix anyway? (y/N)
```

Do not proceed to pr-fix unless the user confirms. If they decline, stop here.

Load `workflows/pr-fix.md` and execute it. Pass forward:

- `OWNER`, `REPO`, `PR_NUMBER`
- `HEAD_BRANCH` (the branch to check out in the worktree)
- `FINDINGS`: the full deduplicated, scored findings list from Step 7
- `SONAR_FINDINGS`: SonarQube findings from Step 4 (if any)
- `SONAR_HOTSPOTS`: security hotspots from Step 4f ([context/quality-gates.md](../context/quality-gates.md)), if any
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
| SonarQube MCP unreachable | Try the SonarCloud REST fallback (Step 4a, [context/quality-gates.md](../context/quality-gates.md)) with `SONARQUBE_TOKEN` before skipping. Only if REST also fails: log "SonarQube: MCP offline and REST unreachable." Continue. |
| SonarQube project not found | Log "SonarQube: project not configured for this repo." Continue. |
| Large PR (> 500 lines) | See large-PR handling strategy in Step 5; never silently truncate. |
| Agent returns no findings | Include: "{Agent}: No issues found." in the relevant tier section. |
