# SonarQube and Qlty quality-gate detail

This covers the detailed procedure for Step 4 (Fetch SonarQube Findings) of
`workflows/pr-review.md`: organization and project-key detection, PR-specific
issue and hotspot fetches with branch-level fallbacks, the SonarCloud
pre-flight placeholder-config check, storage of findings for the fix
workflow, and the Qlty commit-status detection for the other configured
quality gate. The spine keeps the `## Step 4` heading with a short
orchestration stub; the full procedure lives here.

For the shared "unreachable MCP server is not an empty result set" idiom
this content depends on, see
[context/github-api-idioms.md](../context/github-api-idioms.md); this file
keeps its own SonarQube-specific REST fallback text and only points at the
shared file where the general idiom applies.

---

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
entirely. Check the variable is actually set before spending a call on it; an unset
token is not the same failure as an unreachable server and should be reported
distinctly ("SonarQube: REST fallback unavailable, `SONARQUBE_TOKEN` is not set" versus
"SonarQube: unreachable"):

```bash
if [ -z "${SONARQUBE_TOKEN:-}" ]; then
  echo "SonarQube: REST fallback unavailable, SONARQUBE_TOKEN is not set"
else
  ISSUES_HTTP=$(curl -s -o /tmp/sonar_issues.json -w '%{http_code}' -u "${SONARQUBE_TOKEN}:" \
    "https://sonarcloud.io/api/issues/search?componentKeys={KEY}&organization={ORG}&pullRequest={N}")
  HOTSPOTS_HTTP=$(curl -s -o /tmp/sonar_hotspots.json -w '%{http_code}' -u "${SONARQUBE_TOKEN}:" \
    "https://sonarcloud.io/api/hotspots/search?projectKey={KEY}&pullRequest={N}")
  # A non-2xx status means the fallback failed (bad token, wrong key, rate limit);
  # do not treat the response body as findings in that case.
fi
```

Both endpoints require authentication: an anonymous request returns "Project doesn't
exist" even for a valid key, so the `-u "${SONARQUBE_TOKEN}:"` form is mandatory and the
curl path covers BOTH issues and hotspots. Note the issues endpoint's parameter is
`componentKeys`, not `projects`; `projects` is not a recognized parameter for
`/api/issues/search` and is silently ignored by the API, which would otherwise return
an unfiltered (or empty, depending on token scope) result set that looks like "no
issues" rather than "malformed request." Check `$ISSUES_HTTP`/`$HOTSPOTS_HTTP` for a
2xx status before treating the body as findings; a non-2xx status is a fetch failure,
not an empty result, and should be reported as such. Only if both MCP and REST fail
should the workflow skip Sonar.

### 4b. Resolve project key

Check in order:

1. `.sonarlint/connectedMode.json` → `projectKey`
2. `sonar-project.properties` → `sonar.projectKey`

If not found, use `search_my_sonarqube_projects` to list projects and match
by repo name.

### 4c. Pre-flight SonarCloud configuration check

Before fetching findings, inspect `sonar-project.properties` AND its
`.template` variant for placeholder values (a repo mid-setup can carry either
name, and checking only the first misses the second entirely):

```bash
for f in sonar-project.properties sonar-project.properties.template; do
  gh api "repos/{OWNER}/{REPO}/contents/$f" \
    --jq '.content' 2>/dev/null | base64 -d 2>/dev/null
done
```

If any of these patterns appear, emit a **Critical** finding in the report:

- `sonar.organization=your-org` or `sonar.organization=your_org`
- `sonar.projectKey=your-project` or similar placeholder
- `sonar.host.url` pointing at `localhost`

Message: "SonarCloud configuration contains placeholder values; CI quality
gate will fail. Update `sonar-project.properties` with the real organization
and project key before merge."

This prevents the silent "SonarCloud: not configured" skip that delays
findings until a later push. Doing this check before 4d/4e also means a
placeholder config is reported as a real finding rather than silently
producing the same empty result the "not yet analyzed" fallback below
expects.

### 4d. Fetch PR-specific issues

```text
search_sonar_issues_in_projects(
  projects: [PROJECT_KEY],
  pullRequest: PR_NUMBER   ← PR-specific analysis only
)
```

An empty result here is ambiguous: it means either "the PR has not been
analyzed yet" or "the PR was analyzed and has zero issues," and the two
must not be conflated silently, one is a fallback case and the other is
success. Disambiguate before falling back:

```text
list_pull_requests(project: PROJECT_KEY)
```

If `PR_NUMBER` appears in that list, the PR has been analyzed and an empty
issues result means zero issues; report it as such and do not fall back to
branch-level. Only when `PR_NUMBER` is absent from the list should the
fallback run:

```text
search_sonar_issues_in_projects(
  projects: [PROJECT_KEY],
  branch: HEAD_BRANCH
)
```

Note in the report whether results are PR-specific or branch-level, and
if branch-level, that the fallback fired because the PR is not yet
registered in SonarCloud rather than because it has an empty finding set.

### 4e. Fetch PR-specific security hotspots

Security hotspots are a completely separate queue from issues in SonarCloud.
`search_sonar_issues_in_projects` never returns them; this explicit call is
required. Skipping it is the most common reason hotspots go unreviewed.

```text
search_security_hotspots(
  projectKey: PROJECT_KEY,
  pullRequest: PR_NUMBER
)
```

The same not-yet-analyzed-versus-zero-hotspots ambiguity applies here.
Reuse the `list_pull_requests` check from 4d rather than treating an empty
result as automatic grounds for falling back: only fall back to
branch-level when `PR_NUMBER` is absent from that list.

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

### 4f. Store SonarQube findings and hotspots for the fix step

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

### 4g. Qlty findings (other configured quality gate)

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
