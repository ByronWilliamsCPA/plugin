---
description: >
  Repo compliance coordinator. Audits any repository against the standards
  manifest, presents findings by severity, applies approved remediations, and
  runs the retrospective. Interactive mode: full audit-approve-remediate-PR
  flow. Scheduled mode: report-only for org-wide sweeps.
  Covers the API domain (API-001..005) for repos where api.servesApi is true;
  API checks are skipped silently for non-API repos.
  Triggers on: /repo-audit, repo audit, compliance check, standards audit.
tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "TodoWrite"]
---

Orchestrates a full compliance audit and optional remediation run against any repository.

## Invocation

```text
/repo-audit                          # interactive mode, current directory
/repo-audit /path/to/repo            # interactive mode, specified path
/repo-audit --scheduled              # report-only mode for cron trigger
```

## Mode Selection

- Default (no flag): interactive mode, see `workflows/interactive-mode.md`
- `--scheduled`: scheduled mode, see `workflows/scheduled-mode.md`

## Workflow

Follow the appropriate workflow file for the selected mode. Both modes share these steps:

1. Load `~/.claude/docs/standards-manifest.yaml`
2. Load target repo's `.claude/compliance-overrides.md` (if present)
3. Dispatch domain agents in parallel (see workflow file for agent list and prompts)
4. Merge findings, filter overrides, sort by severity
5. Run `compliance-retrospective` after all repos are processed

The retrospective also appends a structured entry to
`docs/compliance-reports/master-log.jsonl` and regenerates the
Markdown view. Fleet-wide synthesis runs weekly via the
`compliance-synthesis` agent; trigger an ad-hoc synthesis with
`/compliance-synthesis`.

## Local Repo Inventory

A pre-built catalog of all 44 repos across both orgs lives at:

- `~/.claude/docs/reference/github-repos.json`: structured compliance data (local only, gitignored)
- `~/.claude/docs/reference/github-repos.md`: human-readable index with refresh commands

The JSON contains a `review` object per repo with pre-fetched values for:
`branchProtection`, `codeql`, `scorecard`, `sonarcloud`, `codecov`, `reuse`, `dependabot`,
`ossfBadge`, `workflows`, `foundations`, `preCommit`, `toolchain`.

**When to consult it:** At the start of any compliance audit:

1. Load `_meta.idealEntry` as the compliance target. Every key in `idealEntry` is the
   expected value for a fully-compliant repo. Pass it to domain agents so they can diff
   the actual repo against the ideal rather than evaluating each field in isolation.
2. Look up the target repo slug (`org/name`) in `repos[]`. If found, extract the `review`
   object and pass it to each domain agent as pre-fetched context to skip redundant GitHub
   API calls and focus on local file verification.

In scheduled mode, use the catalog to pre-populate known state before cloning and
dispatching agents.

**Limitations:** The catalog is local-only (gitignored) and must be refreshed manually using
the commands in `github-repos.md`. Treat cached data as a starting hint, not a definitive
answer. Agents should still verify anything time-sensitive (CI runs, live Scorecard scores).
The `_meta.lastUpdated` field shows the refresh date; flag data older than 30 days as
potentially stale.

**Do not trust `repositoryType` alone for Python applicability.** The label drifts: repos
labeled `python-app` have been found to contain no code at all (corrected to `docs-only`).
Before applying any Python-domain check (TOOL-*, uv adoption), cross-check the label with a
live packaging-file probe (presence of `pyproject.toml`, `*.py` source, `uv.lock`,
`requirements.txt`, `poetry.lock`). When the probe and the label disagree, trust the probe
and note the drift in the audit summary.

**uv adoption is three-tier, not binary.** Asking "does this repo use uv" as yes/no
overstates adoption. The reproducibility-bearing artifact is the committed `uv.lock`, not the
presence of the `uv` command in a workflow. Classify each repo into one of three states:

- **full**: committed `uv.lock` at repo root + PEP 621 / PEP 735 layout (`[project]` /
  `[dependency-groups]`). This is the only PASSing state for uv adoption.
- **partial**: `uv` referenced in CI (`uv sync`, `astral-sh/setup-uv`) but no committed
  `uv.lock`. Flag as a distinct, non-passing finding. These often run `uv sync --frozen`
  against a lockfile that does not exist, so they are silently broken or non-reproducible
  today, and are the repos most in need of migration, not the ones to mark compliant.
- **none**: no uv references.

Manifest check CI-068 enforces "committed `uv.lock` + `--frozen`"; the partial state above is
the precise gap it does not yet name explicitly (see escalation notes for this review).

## Domain Agents

| Domain | Agent | Checks |
|--------|-------|--------|
| foundations | `repo-foundations-auditor` | FOUND-*, REPO-* (repo_settings: REPO-001 allow_auto_merge, REPO-002 delete_branch_on_merge; verified via `gh api repos/<org>/<repo>`) |
| toolchain | `python-toolchain-auditor` | TOOL-* |
| pre_commit | `pre-commit-auditor` | PC-* |
| ci | `devops-deployment-agent` (CI audit mode) | CI-* |
| claude_docs | `claude-docs-auditor` | CLAUDE-* |
| ossf | `ossf-compliance-auditor` | OSSF-* + live Scorecard/Badge API results |
| general | `general-compliance-auditor` | unclassified |
| mkdocs | `mkdocs-auditor` | MKDOCS-* (skipped when mkdocs.yml absent) |
| api | `openapi-compliance-agent` (via check-repo-compliance.py) | API-001..005 (applies_to: api_repos; skip when api.servesApi is false) |

### Pre-commit Domain: silent-skip wrapper defeats PC-* presence checks (obs 163)

Hook presence is necessary but not sufficient for PC-* compliance. The cookiecutter-python
template wraps required hooks (basedpyright, trufflehog, yamllint, markdownlint, bandit)
inside a local `qlty-check` shell shim using `command -v tool || echo "tool not installed -
skipping"` (or `|| true`) fallbacks. When the tool is absent the hook exits 0 and pre-commit
reports a pass, so PC-003/PC-005 presence checks succeed while zero enforcement happens.
During the PC-domain audit, grep hook `entry:` blocks for `|| echo`, `|| true`, or
`command -v ... ||` patterns and treat any silent-skip wrapper as equivalent to hook-absent
for PC-003/PC-005. This is a fail-open pattern, not a fail-closed gate.

### CI Domain Agent: Triage Notes

**CI-001: org delegation gap, elevated injection risk when local reusable workflows present**

When CI-001 fires because the repo maintains a local `reusable-*.yml` workflow layer (pattern: 7+ files matching `.github/workflows/reusable-*.yml`), annotate the finding with an elevated CI-028 risk note. Local workflow files introduce additional script injection surface that the shared org library handles centrally in org-delegating repos. Explicitly check all local `reusable-*.yml` files for `${{ github.event.* }}` inputs used directly in `run:` steps (S7630 pattern) as part of CI-001 triage; do not wait for the CI-012/SonarCloud gate to surface them.

Tag the finding: `[CRITICAL] CI-001 + elevated CI-028 risk: local reusable workflow layer found; script injection audit required.`

**CI-003c: Scorecard workflow trigger absence (distinct from absent or misconfigured)**

When the Scorecard API returns 0 scores or shows 74+ consecutive failures, check for CI-003c before assuming a configuration error: open `.github/workflows/scorecard.yml` (or equivalent) and verify it contains an `on.schedule.cron` entry. A `workflow_dispatch`-only workflow is syntactically valid and passes file-presence checks (CI-003) but never runs automatically, producing a sustained 0-score result that is indistinguishable from a broken workflow at the API level.

If `on.schedule.cron` is absent: emit `[CRITICAL] CI-003c: Scorecard workflow has no schedule trigger; add a weekly cron (e.g., \`0 1 * * 1\`) to enable automatic scoring.`

Run CI-003c first when Scorecard shows 0 scores; the one-line fix (adding a cron trigger) is far cheaper than diagnosing a configuration error that does not exist.

**CI-003d: required ruleset context names must match bare check-run names, not prefixed reusable-workflow names**

When every open PR in a repo reports `mergeStateStatus: BLOCKED` despite every visible check passing, the cause is usually a required status-check context that no job publishes verbatim. A workflow that delegates to an org reusable workflow publishes its check run as `<calling-job> / <reusable-job>` (e.g., `Security Analysis / Security Gate Validation`), not the bare name. If the ruleset requires the bare context (`Security Gate Validation`), GitHub waits for a check run that never reports and blocks merge invisibly.

For each ruleset `required_status_checks` context, verify a check run with that exact name reports on a recent PR head:

```bash
gh pr checks <pr> --required          # shows which required contexts actually report
gh api repos/<org>/<repo>/commits/<sha>/check-runs --jq '.check_runs[].name'
```

Flag any required context that only exists in prefixed `caller / callee` form. Recommend the thin bare-named gate-job pattern (a local job named exactly the required context that depends on the reusable-workflow job), the same pattern repos already use for `ci-gate`. Do not trust an inline comment claiming the prefixed name matches the ruleset; diff the strings.

**CI-enforcement reality: a check that cannot report failure is not a gate (obs 184, 185)**

Two failure modes make a "required" CI gate non-enforcing while every presence check passes:

1. **App StatusContext that always reports SUCCESS.** The `qlty check` status context posted
   by the qlty.sh GitHub App always reports `state: SUCCESS` regardless of blocking-issue
   count; the "N blocking issues" text lives only in the description annotation, and GitHub's
   merge gate reads only `state`. Adding it to `required_status_checks` never blocks. qlty
   enforcement requires a GitHub Actions CheckRun: a workflow job that runs
   `qlty check --fail-level <level>` and exits non-zero. Same root cause as the CodeRabbit
   rate-limit SUCCESS pattern: third-party app StatusContexts cannot be trusted as hard gates
   because the app controls the state it posts. When auditing any required check, verify it can
   actually report `failure`, not just `success` with an annotation; prefer Actions CheckRuns
   over app StatusContexts.
2. **Required before the producing workflow exists.** Adding a context to
   `required_status_checks` before a workflow produces it puts every PR in permanent pending:
   the check never posts, the requirement is never satisfied, no PR merges. Sequence for any
   new workflow-based check: (1) add the workflow and let it produce at least one successful
   run, (2) confirm the exact check name from a real run via the Checks API (reusable-workflow
   callee jobs report as `<caller-job-id> / <callee-job-display-name>`), (3) only then add it to
   `required_status_checks`. A required check that never runs silently blocks all merges, worse
   than no required check.

**Dormant equivalent capability: evaluate delta-over-existing, not greenfield (obs 191)**

Before evaluating a NEW tool for a capability (license compliance, SBOM, vuln scanning),
grep the existing reusable workflows and the manifest for an existing or dormant equivalent:
disabled flags, warn-only gates, unused action inputs (e.g., a `deny-licenses` lever in
`dependency-review-action`, a `python-sbom.yml` license job, a REUSE/SPDX gate). Frame the
evaluation as the marginal gain over what already exists (including the cost of redundancy),
not as a blank-slate integration. Capabilities are often already present but disabled or
shallow.

**CI pinning exception list: slsa-github-generator requires tag refs**

Blanket SHA-pinning (zizmor `unpinned-uses`, Scorecard `pinned-dependencies`) must not be applied to every workflow ref. `slsa-framework/slsa-github-generator` reusable workflows are the canonical exception: they hard-fail with `Invalid ref ... Expected ref of the form refs/tags/vX.Y.Z` because the generator downloads its own prebuilt release binary by tag name, and Scorecard itself whitelists it. A SHA pin produces a runtime failure that surfaces only on the first real release, far from the pinning change.

When auditing or remediating Actions pinning, maintain an exception list (starting with `slsa-framework/slsa-github-generator` reusable workflows). Skip refs on that list instead of converting them, and require the inline comment convention `@vX.Y.Z # tag ref required: generator rejects SHA pins`. Verify a pin survives the tool's own validation path before standardizing it.

### Bash file-existence checks: handle 404 responses correctly

When a domain agent uses `gh api repos/<org>/<repo>/contents/<path> --jq '.<field>'`
to test for file presence, the 404 case is a trap: the GitHub API returns
`{"message":"Not Found","status":"404"}` and `--jq '.name'` on that response
returns the literal string `null`, not an empty string. Bash tests like
`[ -n "$result" ]` then evaluate `null` as truthy and report the file as
PRESENT when it is actually absent. Symptom: a foundation file check reports
all required files present even on a freshly initialized repo with only
`README.md`.

Robust patterns:

- Use `--jq '.<field> // "NOT_FOUND"'` and test against the sentinel:
  `if [ "$status" != "NOT_FOUND" ] && [ "$status" != "null" ]; then ...`
- Or check the HTTP status directly with `--silent`:
  `gh api "..." --silent 2>/dev/null && echo PRESENT || echo ABSENT`

Apply to any new bash check in this skill or in domain agent prompts that
calls `gh api ... --jq` and tests for non-empty output.

### API Domain: applies_to Conditional

Before dispatching API-domain checks, read `api.servesApi` from the target
repo's catalog entry. The canonical catalog path is
`${CLAUDE_HOME:-$HOME/.claude}/docs/reference/github-repos.json`; inside this
repo it is also reachable at the relative path `docs/reference/github-repos.json`.
Both refer to the same file (the `~/.claude` location is a symlink installed
by `setup.sh`). If `api.servesApi` is absent or `false`, skip all API-*
checks without raising FINDINGs; log `SKIP (api.servesApi: false)` in the
audit summary. API-* checks run only for repos where `api.servesApi: true`.

API-001 through API-003 are evaluated by `scripts/check-repo-compliance.py` via
the GitHub Contents API. API-004 and API-005 read from the catalog directly
(fields set by the openapi-compliance-agent after a successful run).

## Type and Visibility Evaluation

Before dispatching domain agents, read the target repo's entry in
`docs/reference/github-repos.json`:

1. Look up the entry by matching `org` + `name` fields in the `repos[]` array.
2. Read `repositoryType` from the entry.
3. Load `_meta.typeProfiles[repositoryType]` to get the type profile.
4. Read `isPrivate` from the entry. If absent, default to `false` (treat as public): skip
   loading the visibility profile, set `Scorecard API skip: false`, and leave `exemptChecks`
   and visibility `exemptWorkflows` empty.
5. If `isPrivate` is `true`, load `_meta.visibilityProfiles.private` to get the visibility
   profile. If `_meta.visibilityProfiles.private` is absent or null, treat it as an empty
   profile: no additional exemptions, no `scopedNotes`, no `Scorecard API skip`.
6. Merge visibility exemptions with type exemptions (union of both sets): combine
   `exemptWorkflows` from both profiles, combine `exemptChecks` from the visibility profile
   with the per-repo override entries from `.claude/compliance-overrides.md`. Pass
   `exemptChecks` (from the visibility profile) and override check IDs (from
   `compliance-overrides.md`) as separate coordinator prompt fields; do not collapse them
   so domain agents can log `EXEMPT (private repo)` vs `OVERRIDE` with distinct audit trails.
   #ASSUME both sources use identical check ID formats (e.g., `OSSF-001`); verify if adding
   a new profile type.

Pass the following to each domain agent in the coordinator prompt:

```yaml
Repository type: <repositoryType>
Repository visibility: <public|private>
Exempt workflows (do not raise FINDING for absence): <merged exemptWorkflows from type + visibility profiles>
Exempt hooks (do not raise FINDING for absence): <exemptHooks list from type profile>
Exempt check IDs (log EXEMPT, not FINDING): <exemptChecks from visibility profile, if private>
Scorecard floor: <scorecardFloor from type profile, or 7.0 if not overridden>
Scorecard target: <scorecardTarget from type profile, or 8.5 if not overridden>
Scorecard API skip: <true if private repo, false otherwise>
```

**Exemption rule:** If a workflow filename appears in the merged `exemptWorkflows`, log
`EXEMPT (infrastructure type)` or `EXEMPT (private repo)` for its absence; use the
source that triggered the exemption in the label. Same for `exemptHooks`. For check IDs in
`exemptChecks`, log `EXEMPT (private repo)` instead of FINDING.

**Exemption label tiebreaker:** When a workflow filename appears in both the type profile
and the visibility profile `exemptWorkflows`, label the exemption with the type source
(e.g., `EXEMPT (infrastructure type)`) and omit the visibility label; type takes precedence
for labeling.

**Scorecard evaluation:** Use the type profile's `scorecardFloor` and
`scorecardTarget` when they exist; fall back to `idealEntry.scorecard.floor`
(7.0) and `idealEntry.scorecard.target` (8.5) otherwise. When `Scorecard API skip: true`,
skip the live `api.securityscorecards.dev` lookup entirely; the public API does not
index private repos and will return no data. Do not raise a FINDING for a missing score.

**Private repo scoped notes** (from `visibilityProfiles.private.scopedNotes`): Include
these as informational context in the audit report, not as FINDINGs. They explain
limitations (e.g., GitHub PVR unavailable) rather than compliance gaps.

**Examples:**
- Repo `homelab-infra` has `repositoryType: "infrastructure"` and `isPrivate: true`
  - Type profile exempts `release.yml`, `release-sign.yml`, `sbom.yml`, `coverage.yml`, `python-compatibility.yml`, `reuse.yml`
  - Visibility profile additionally exempts `codeql.yml` (GHAS required) and check IDs `OSSF-001`, `OSSF-006`
  - Absent `release.yml` is logged as `EXEMPT (infrastructure type)`, absent `codeql.yml` as `EXEMPT (private repo)`
  - OSSF-001 finding is suppressed with `EXEMPT (private repo: badge API is public OSS only)`

## Coordinator Prompt Template

When dispatching each domain agent, include in the prompt:

```yaml
Mode: <audit|remediation>
Target repo: <absolute path>
Manifest checks for this domain:
<paste ONLY the check entries whose ID prefix matches this agent's domain,
 not the full manifest. E.g., CI-* only for devops-deployment-agent.>
Override entries (skip these check IDs):
<paste entries from compliance-overrides.md, or "none">
Repository context:
  type: <repositoryType>
  visibility: <public|private>
  exempt_workflows: <merged list from type + visibility profiles>
  exempt_hooks: <list from type profile>
  exempt_check_ids: <list from visibility profile exemptChecks, or empty>
  scorecard_floor: <floor>
  scorecard_target: <target>
  scorecard_api_skip: <true|false>
Cached review data (domain-scoped):
<paste only the cachedReview keys relevant to this agent's domain. Key
 names must match the `review` schema in docs/reference/github-repos.json
 exactly (branchProtection, codecov, codeql, foundations, ossfBadge,
 preCommit, releaseHealth, renovate, reuse, scorecard, secretScanning,
 sonarcloud, templateDrift, toolchain, workflows):
  repo-foundations-auditor: foundations (the foundations key applies to FOUND-*
    checks; REPO-* repo_settings checks are evaluated live via
    gh api repos/<org>/<repo> with no cachedReview key)
  python-toolchain-auditor: toolchain, renovate
  pre-commit-auditor: preCommit
  devops-deployment-agent: workflows, reuse
  claude-docs-auditor: (no relevant cachedReview keys; verify on disk)
  ossf-compliance-auditor: scorecard, ossfBadge, codeql, secretScanning
  mkdocs-auditor: (no relevant cachedReview keys; verify on disk)
  general-compliance-auditor: full cachedReview>
```

For the `ossf-compliance-auditor` specifically, also include:

```html
Repo slug: <owner/repo GitHub slug>
Scorecard API skip: <true if private, false if public>
```

The OSSF agent queries live APIs (Scorecard REST API, Best Practices Badge API, GitHub API) using the repo slug. It will produce FINDING blocks both for OSSF-* manifest checks and for Scorecard checks that score below 4, even when those checks have no manifest entry. When `Scorecard API skip: true`, the agent must skip the Scorecard REST API call and suppress score-based FINDINGs; it should still evaluate local file checks (SECURITY.md content, workflow presence) that do not require the API.

## Remediation Verification

**Validate bot-managed configs with the official validator before declaring an issue fixed.**
When remediating any bot-consumed config (`renovate.json`, `dependabot.yml`,
`.coderabbit.yaml`, `.trivyignore` plus its workflow, semantic-release config), run the
tool's official validator on the FULL resulting file before merge, not just the hunk being
changed:

- Renovate: `npx --package renovate renovate-config-validator` (at the same major version as
  the self-hosted instance)
- semantic-release: `uvx --from python-semantic-release semantic-release --noop version`
- dependabot, coderabbit: their respective CLI / dry-run paths

Fixing the error named in a bot's issue proves the report is addressed, not that the file is
valid: validators check the whole contract, while error reports only surface the first
breach. A config that fixes the reported error and still has a second invalid option will
re-halt all dependency PRs on the bot's next run.

**Validate manifest edits against the self-consistency test, not just YAML parse.** After any
edit to `docs/standards-manifest.yaml`, run the repo's own consistency gate, not just a YAML
parser:

```bash
python3 -m pytest tests/unit/test_manifest_consistency.py -o addopts="" -q
```

(The `-o addopts=""` override skips the unrelated 80% coverage gate.) The manifest carries
invariants the schema does not encode, and a parse-only check passes the
semantically-wrong-but-syntactically-valid case. Specific invariant: suggested-tier checks
always set `override_eligible: true`, because the field is inert at that tier; copying
`override_eligible: false` by analogy with a critical security check parses cleanly but fails
the consistency test.

## Re-verify Prior Audit Mode

Audit branches produced by automated audits (`claude/repo-audit-*`) go stale relative to
`main`. To decide whether such a branch is still actionable, do NOT check it out and do NOT
trust commit ancestry (squash-merge breaks ahead/behind counts). Instead run a content-level
delta against `origin/main`:

1. Read the machine-readable findings from the branch without checkout:
   `git show <branch>:findings.csv` (or `findings.json`).
2. For each finding (id, files, evidence columns), re-check the evidence against current main
   with `git grep <pattern> origin/main -- <files>` or `git show origin/main:<file>`.
3. Classify each finding as resolved or still open; emit a resolved/open delta table.
4. Recommend merge-docs-and-file-issues (if open findings remain) vs delete-as-stale (if all
   resolved).

Machine-readable findings with file+evidence columns make audits cheaply re-verifiable months
later without re-running the full audit. Triage always runs against `origin/main` via
`git show` / `git grep`, never against the stale checked-out branch. This also applies to
any audit finding or remediation that depends on release tags or version refs: confirm tag
state via `git ls-remote --tags origin` first, because a local clone may have zero tags
fetched and "no tags" presented silently as ground truth produces remediations built on a
false premise.

## Audit Grounding and Verification

The audit reasons from whatever it measures, so a polluted measurement produces a confident
wrong conclusion. Apply these grounding rules before relaying any count, status, or finding.

### Read authoritative remote files via the Contents API, not WebFetch

When you need the exact content of a file on a GitHub repo at HEAD (a sibling repo's manifest,
a workflow you do not have cloned, an upstream config), use the Contents API, not WebFetch on
the `blob` URL. GitHub `github.com/.../blob/...` URLs serve an HTML rendering; WebFetch
converts that HTML to Markdown and garbles code-block structure and whitespace. The Contents
API returns the raw bytes (base64-encoded) and works on private repos when `gh` is authed:

```bash
gh api repos/<owner>/<repo>/contents/<path>?ref=main \
  | python3 -c "import sys,json,base64; print(base64.b64decode(json.load(sys.stdin)['content']).decode())"
```

Pair it with a targeted `grep` to audit exactly what a file contains without cloning. This is
the same authority as `git show origin/main:<file>` for repos you do have cloned.

### Catalog-less fallback (obs 106)

The catalog (`standards-manifest.yaml`, `github-repos.json`) is an optimization, not a hard
dependency. If either file is absent (e.g., a fresh machine or a research fork), proceed in
catalog-less mode: run domain checks from first principles using the
FOUND-/TOOL-/PC-/CI-/OSSF- check families, default `repositoryType` to a generic profile, and
default visibility from `gh repo view --json isPrivate`. Do not error or stall on a missing
catalog; treat the catalog loads in "Local Repo Inventory" and "Type and Visibility
Evaluation" as conditional, consistent with the stated limitation that the catalog is "a
starting hint, not a definitive answer."

### Anchor field counts to the field, not a substring (obs 105)

When counting or inventorying manifest fields (severity tiers, `override_eligible`, domains),
anchor to the field position rather than substring-matching, because config VALUES collide
with field NAMES. `grep -oE 'severity:\s*"?[a-z]+'` falsely counts `fail-on-severity: high`
(a dependency-review VALUE) as a severity TIER. Use an anchored regex
(`grep -nE '^\s+severity:\s*(critical|important|suggested)\s*$'`) or a real YAML parser. The
manifest's active tiers are critical / important / suggested; there is no `high` or `blocker`
tier. Counts that drive calibration judgments must come from the anchored field or the audit
reasons from a polluted denominator.

### Configured vs executing vs effective (obs 90, 177)

Config presence proves intent, not operation. For any check asserting a tool or bot is
"active," separate three states explicitly: (1) configured (config file present), (2)
executing (durable artifacts exist), (3) effective (the outcome it should produce is present).
Detect execution by durable artifacts (branch-name prefixes, generated issues/labels, workflow
run history), never by config presence or an assumed bot login. Specifics:

- **Renovate health:** A `renovate.json` with `pinDigests: true` is inert if the bot has auth
  errors or is not installed. Verify by (1) Renovate app installed at org level (app
  installations API), (2) Dependency Dashboard issue body free of `ERROR`/`unhandledRejection`
  lines, (3) recent SHA-to-SHA bump PR as proof, not config-file presence alone.
- **Bot identity breaks under self-hosting:** self-hosted Renovate/Dependabot run under a
  user/PAT identity, so author-based filters (`renovate[bot]`) silently miss them. The reliable
  signal is the artifact signature: head-branch prefix `renovate/` and the Dependency Dashboard
  issue, regardless of author.

### Paginate before reporting counts (obs 178)

Unpaginated GitHub list endpoints cap at one page (default 30); `length` of one page is an
upper-bounded sample, not a total. `gh api repos/<r>/dependabot/alerts --jq length` returned
30 for a repo with 56 open alerts (a 46% undercount that would understate severity). Any check
that surfaces a count from a GitHub list endpoint (alerts, PRs, issues, workflow runs) must use
`--paginate` with an explicit state filter (`?state=open&per_page=100`). Never report `length`
of a single unpaginated page as a total.

### Enumerate every ecosystem before declaring a vuln scan clean (obs 180)

A vulnerability scan's completeness is bounded by its ecosystem coverage, not its database. A
Python-only SBOM/scan reports false-clean on a repo whose real exposure is npm packages in a
frontend `package-lock.json` (or a container base image, or Go/Ruby/Cargo). Discover every
dependency ecosystem present (Python lockfiles, npm/yarn/pnpm lockfiles, Go, Ruby, Cargo,
container base images) and scan each before declaring "0 findings." Reconcile against an
independent multi-ecosystem source (Dependabot alerts) as the backstop; single-ecosystem CI
gates miss cross-ecosystem surfaces.

### Scope a tool swap from its active config, not its feature set (obs 133)

When evaluating replacing or removing a tool, read the tool's active configuration (ignore
lists, strictness, enabled rule subset) to determine the ACTUAL enforced behavior before
mapping replacements, rather than assuming the tool's full advertised capability. A repo
nominally "running darglint" may, via its `[tool.darglint]` ignore list, enforce only the
excess/mismatch direction (DAR102/202/302/402), which narrows the replacement requirement and
exposes coverage gaps in candidates (Ruff's pydoclint port omits the DOC1xx argument family).
Also disambiguate adjacent tools that occupy different concerns (coverage vs consistency,
format vs lint) so only the correct one is swapped.

### Dead config: settings defined but never consumed (obs 64)

A config setting that exists but is never read is worse than no config: it misleads operators
into believing a value is tunable when changing it has no effect. For services using a Settings
class (Pydantic Settings especially), cross-reference every defined setting against grep
evidence that it is read at least once in application code. Flag settings with no consumer as a
dead-config finding.

### Broaden migration greps to lock/TOML/install references (obs 101)

A migration sed pass keyed on `grep -rln "poetry "` (trailing space) catches command
invocations but silently misses `poetry.lock` filename mentions, `[tool.poetry.group.*]` TOML
block headers, and `pip install poetry` setup steps. Run two passes: trailing-space for
commands, no-trailing-space for filename/config references; diff the file lists and review the
delta. Use the broader no-trailing-space pattern as the post-pass verification command.

### Renovate tag-comment scheme mismatch (obs 301)

When Renovate reports "Could not determine new digest" for a github-tags dependency and the
SHA pin is valid, cross-check the version comment against actual upstream tag names via
`gh api repos/<owner>/<repo>/tags --jq '.[].name'`. Renovate uses the version comment as its
datasource lookup key; a `v`-prefix mismatch (`# v1.1.0` comment vs `1.1.0` actual tag, or
vice versa) silently breaks digest resolution. The fix is always in the comment, not the SHA.

### Linter onboarding: baseline-violation triage (obs 148)

Onboarding a new linter onto a legacy codebase always produces a baseline violation count
(pydoclint found 2284 across 149 files on one repo); that count is a debt snapshot, not a
blocker. When violations exceed the migration threshold: (1) record the per-directory
histogram in the PR body as a baseline, (2) open a follow-up issue tagged `tech-debt` with
the counts, (3) note any already-clean directories as quick wins. The migration PR is correct
even with violations present: it establishes the config + hook and defers bulk remediation.
Do not conflate "is the tool wired correctly" with "is all existing code clean."

### Baseline pre-commit against main before attributing failures (obs 92)

Repos with known pre-commit debt fail `pre-commit run --all-files` on a feature branch for
reasons that pre-date the branch. Before attributing a pre-commit failure to the current
change, stash the changes and re-run on clean `main` to confirm the failures are pre-existing.
Note pre-existing failures in the PR description rather than fixing them in an unrelated PR's
scope; only the hooks specific to the change need to pass cleanly.

### Defang secret-shaped strings in audit docs (obs 270)

Documentation about a secret pattern reproduces the secret pattern, and scanners cannot
distinguish evidence from leakage. When quoting secret-shaped strings (placeholder keys,
masked tokens, default passwords) as finding evidence, break the detector pattern the way
malware samples are defanged (`api-xxxx[masked]`, not a format-length-exact placeholder), or
reference `file:line` instead of reproducing the value. Per-commit scanners (GitGuardian)
catch quoted findings in new doc files even when diff-based scanners pass. Defang at write
time, never allowlist after the trip.

### Verify shared-component breakage against sibling consumers (obs 275)

When a handoff or issue claims a shared component (reusable workflow, org template) is broken
for N consumers, the first verification step is to sample run history across 3-5 OTHER
consumers (`gh run list -R org/repo --workflow=X`). One sibling succeeding against the same
component version falsifies the "shared component is broken" hypothesis and points to a
caller-side cause (caller passes an input the reusable no longer defines; caller's permission
grant is below what the reusable's jobs request). Differential diagnosis beats deep-dive.

### Catalog entries are audits, not roster rows: stub, never fabricate (obs 207)

Catalog entries that carry a populated `review` block encode a completed audit. When
reconciling the catalog against the live fleet, add a never-tracked repo as an explicit stub
(identity fields from the API plus a `review._status` marker like "not yet audited; run
repo-compliance to populate") and tell the user the stub needs an audit pass. Never copy a
neighbor's review block as a template: that fabricates unverified branch-protection / scorecard
state. Confirm round-trip formatting fidelity (load/dump diff empty) before programmatic edits,
especially on a shared clone with concurrent uncommitted edits.
