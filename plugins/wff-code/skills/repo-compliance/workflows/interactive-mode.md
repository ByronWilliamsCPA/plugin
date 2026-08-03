# Interactive Mode Workflow

Full audit-approve-remediate-PR flow for a single target repo.

## Steps

### 1. Setup

```bash
# Resolve target repo path
TARGET_REPO="${1:-$(pwd)}"
cd "$TARGET_REPO"
git status  # confirm it is a git repo
```

Read `~/.claude/docs/standards-manifest.yaml`. Note its `last_updated` value as MANIFEST_VERSION.
Read `$TARGET_REPO/.claude/compliance-overrides.md` if it exists; extract the Check ID column.

**Load pre-fetched catalog data (if available):**
Read `~/.claude/docs/reference/github-repos.json` if it exists. Derive the repo slug from the target repo's `git remote get-url origin` output (format: `org/repo-name`). Find the matching entry in `repos[]` by `org` + `name`. If found, extract the `review` object. Attach it to each domain agent's prompt under the key `cachedReview` so the agent can skip redundant GitHub API calls. Include the catalog `_meta.lastUpdated` date; if it is older than 30 days, flag cached data as potentially stale.

**Load passing-agent cache (delta mode):**
Read `~/.claude/docs/compliance-reports/state/last-audited.json` if it exists.
Look up the entry keyed by the repo slug (format: `org/repo-name`).
If an entry exists and its `manifest_version` matches MANIFEST_VERSION AND the user did not pass `--force`:
- Set SKIP_DOMAINS to the list of domains in `clean_domains` for that entry.
- Print: `Delta mode: skipping clean domains from last audit (${audited_at}): ${SKIP_DOMAINS}`
- Do NOT dispatch agents for domains in SKIP_DOMAINS.
If no entry exists, or `manifest_version` differs, or `--force` was passed:
- Set SKIP_DOMAINS to empty (full audit).

### 2. Parallel Audit Dispatch

Use TodoWrite to track agent dispatch. Dispatch all domain agents in parallel using the Agent tool. Pass each agent the coordinator prompt template from SKILL.md populated with:
- Mode: audit
- Target repo: resolved absolute path
- Manifest checks: the subset for that domain (domain-relevant entries only, not the full manifest)
- Override entries: IDs from compliance-overrides.md
- cachedReview: only the fields relevant to that agent's domain (see domain field map below)

Domain-to-cachedReview field map (pass only these keys per agent). Key names
must match the `review` object schema in `docs/reference/github-repos.json`
exactly: `branchProtection`, `codecov`, `codeql`, `foundations`, `ossfBadge`,
`preCommit`, `releaseHealth`, `renovate`, `reuse`, `scorecard`,
`secretScanning`, `sonarcloud`, `templateDrift`, `toolchain`, `workflows`.
- `repo-foundations-auditor`: `foundations` (the `foundations` key applies to FOUND-* checks; REPO-* repo_settings checks are evaluated live via `gh api repos/<org>/<repo>` with no cachedReview key)
- `python-toolchain-auditor`: `toolchain`, `renovate`
- `pre-commit-auditor`: `preCommit`
- `devops-deployment-agent`: `workflows`, `reuse`
- `claude-docs-auditor`: (no relevant cachedReview keys; verifies CLAUDE.md files on disk)
- `ossf-compliance-auditor`: `scorecard`, `ossfBadge`, `codeql`, `secretScanning`
- `mkdocs-auditor`: (no relevant cachedReview keys; verifies mkdocs.yml on disk)
- `operations-posture-auditor`: (no relevant cachedReview keys; the catalog `review` schema describes repo and CI state, not deployed-system state. This agent gathers its own evidence via Bash and the `docs/operations/` attestation files.)
- `general-compliance-auditor`: full cachedReview (freeform review needs full context)

Agents to dispatch simultaneously (skip any whose domain is in SKIP_DOMAINS):
- `repo-foundations-auditor` (FOUND-* checks, plus REPO-* repo_settings checks via `gh api repos/<org>/<repo>`) -- domain: `foundations`
- `python-toolchain-auditor` (TOOL-* checks) -- domain: `toolchain`
- `pre-commit-auditor` (PC-* checks) -- domain: `pre_commit`
- `devops-deployment-agent` in CI audit mode (CI-* checks) -- domain: `ci`
- `claude-docs-auditor` (CLAUDE-* checks) -- domain: `claude_docs`
- `ossf-compliance-auditor` (OSSF-* and SCORECARD:* checks) -- domain: `ossf`
- `general-compliance-auditor` (all checks as negative filter, freeform review) -- never skipped
- `mkdocs-auditor` in audit mode (MKDOCS-* checks; skipped automatically when no mkdocs.yml is present in the project root) -- domain: `mkdocs`
- `operations-posture-auditor` (OPS-* checks; applies_to `deployed_repos`. Skipped ONLY when the catalog `isDeployed` flag is explicitly `false`; absent, `null`, and non-boolean values still dispatch it so it emits the UNKNOWN finding) -- domain: `operations`

> Note: REPO-* checks carry `domain: repo_settings` in the manifest but are produced by `repo-foundations-auditor`, which is dispatched under `domain: foundations`. A `SKIP_DOMAINS` entry of either `foundations` or `repo_settings` therefore skips the REPO-* checks, and any retrospective grouping should treat `repo_settings` findings as belonging to the foundations agent.

### 3. Merge and Present Findings

Collect all FINDING blocks. Filter out any finding whose ID is in the override list. Sort by severity: Critical first, then Important, then Suggested. Present unclassified candidates in a separate section.

**Renovate-health aggregation:** After sorting, identify findings whose manifest check carries `check_family: renovate-health`. Read that tag from `docs/standards-manifest.yaml` as the single source of truth; do not hardcode an ID list (the family membership is maintained in the manifest). If 2 or more renovate-health findings are present for this repo, regardless of their individual severities, prepend this callout at the top of the Important section:

```text
[RENOVATE-HEALTH] 2+ Renovate-structure checks failed: Renovate process is not
ideally structured for this repo. Findings below include all renovate-health
checks surfaced to the Important section for this run. Individual severities
retained for manifest fidelity.
```

Move any renovate-health findings that are currently Suggested to the top of the Suggested section with an `[elevated: renovate-health aggregate]` tag so they are visible without changing their manifest-recorded severity. The tag is a display annotation only: it must not alter the finding's `severity` field or its ID, because downstream domain agents and the retrospective read the FINDING block's severity directly. The callout surfaces the cluster; approval options A/B/C/D remain unchanged so the user retains control over remediation.

When rendering the report template (`templates/compliance-report.md`), set `renovate_health_triggered` to `yes` when this 2-or-more aggregation fired and `no` otherwise, so the template's Renovate-health aggregate line is populated rather than shipping the raw placeholder.

Present findings in this format:

```html
COMPLIANCE AUDIT: <repo-name>
Standards version: <manifest last_updated>
Overrides applied: N

CRITICAL (N findings)
  [FOUND-001] SECURITY.md absent from project root
  [CI-005] 6 action refs use mutable tags instead of SHA pins

IMPORTANT (N findings)
  [FOUND-005] .worktrees/ absent from .gitignore
  ...

SUGGESTED (N findings)
  ...

UNCLASSIFIED CANDIDATES (N items, for retrospective review)
  [candidate] .editorconfig absent; proposed domain: foundations, severity: suggested
  ...
```

### 4. Approval Loop

Ask: "Which findings would you like to remediate? Options:
  A) All critical and important
  B) All critical, important, and suggested
  C) Select specific check IDs (comma-separated)
  D) Skip remediation (report only)"

Wait for user response. Parse the selection into an approved findings list.

### 5. Remediation Dispatch

For each approved finding, route to the owning domain agent in remediation mode. Use the same coordinator prompt template with Mode: remediation and only the approved findings list.

Dispatch agents by domain in dependency order:

1. `repo-foundations-auditor` (foundations: no dependencies)
2. `python-toolchain-auditor` (toolchain: no dependencies)
3. `pre-commit-auditor` (pre_commit: depends on toolchain being correct)
4. `devops-deployment-agent` CI audit mode (ci: no dependencies)
5. `claude-docs-auditor` (claude_docs: no dependencies)
6. `ossf-compliance-auditor` (ossf: no dependencies)
7. `mkdocs-auditor` in remediate mode (mkdocs: no dependencies; skipped automatically when no mkdocs.yml is present)
8. `operations-posture-auditor` in remediation mode (operations: no dependencies; skipped ONLY when `isDeployed` is explicitly `false`. Absent, `null`, and non-boolean values must still dispatch the agent so it emits the UNKNOWN finding; treating an undeclared flag as a skip reinstates the silent-skip defect this domain was built alongside, and all 45 catalog entries currently carry `isDeployed: null`). Its remediations are attestation scaffolds under `docs/operations/`, never live changes to a deployed system, a database role, or a vendor console. It must never rotate a credential, alter a database grant, or push a managed-service config; those are operator actions. It emits ACTION lines describing the scaffold it wrote and the operator step still required.

Collect ACTION lines from each agent and present a summary of all changes made.

### 6. Open PR

```bash
cd "$TARGET_REPO"
git add -A
git commit -m "chore(compliance): apply standards alignment from repo-compliance audit

Remediations applied:
<list check IDs that were remediated>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"

git push -u origin HEAD

gh pr create \
  --title "chore(compliance): standards alignment $(date +%Y-%m-%d)" \
  --body "$(cat <<'EOF'
## Compliance Remediations

Applied by the repo-compliance system against standards manifest v<version>.

### Changes Made
<list of ACTION lines>

### Checks Resolved
<list of check IDs>

### Remaining (not approved for this run)
<list of skipped findings>
EOF
)"
```

### 7. Retrospective

Dispatch `compliance-retrospective` with: session date, target repo path, all domain findings, all unclassified candidates.

After it writes the lessons-learned doc, print:
"Retrospective written to docs/compliance-reports/lessons-learned/<date>.md; review before the next scheduled run."

### 8. Update Passing-Agent Cache

After the retrospective completes, update `~/.claude/docs/compliance-reports/state/last-audited.json`:

```python
import json, os, datetime

cache_path = os.path.expanduser(
    "~/.claude/docs/compliance-reports/state/last-audited.json"
)
# Bootstrap the state directory; first-run write would otherwise raise
# FileNotFoundError because ~/.claude/docs/compliance-reports/state/ does
# not exist on a fresh install.
os.makedirs(os.path.dirname(cache_path), exist_ok=True)
cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}

# Determine which domains produced zero findings in this run.
# A domain is clean only if it was dispatched AND returned no FINDINGs.
# Skipped domains (SKIP_DOMAINS) retain their clean status from the prior entry.
prior_clean = cache.get(REPO_SLUG, {}).get("clean_domains", [])
dispatched_clean = [d for d in DISPATCHED_DOMAINS if DOMAIN_FINDINGS[d] == 0]
# Merge: prior clean domains + newly confirmed clean; remove any that had findings
newly_dirty = [d for d in DISPATCHED_DOMAINS if DOMAIN_FINDINGS[d] > 0]
merged_clean = sorted(set(prior_clean + dispatched_clean) - set(newly_dirty))
# Invariant: general-compliance-auditor is never skipped (see dispatch list
# in Step 2). Strip `general` from clean_domains so a clean general run on
# this cycle does not cause the agent to be skipped on the next cycle.
merged_clean = [d for d in merged_clean if d != "general"]

cache[REPO_SLUG] = {
    "manifest_version": MANIFEST_VERSION,
    "audited_at": datetime.date.today().isoformat(),
    "clean_domains": merged_clean,
    "open_findings": [f["id"] for f in ALL_FINDINGS]
}

with open(cache_path, "w") as f:
    json.dump(cache, f, indent=2)
```

Print: `Cache updated: ${REPO_SLUG} -- clean domains: ${merged_clean}`
