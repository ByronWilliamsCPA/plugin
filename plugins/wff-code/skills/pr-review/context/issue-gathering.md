# Issue Gathering (Step 1)

Full procedure for `workflows/pr-fix.md` Step 1, "Gather all issues (run sources
in parallel)". Covers the three heaviest of the six parallel sources: 1a (CI
check failures), 1b (review comments), and 1c (SonarQube findings). Sources 1d,
1e, and 1f are short enough to stay inline in the workflow file; they are not
duplicated here.

## 1a. CI check failures

Use GitHub MCP `pull_request_read` method `get_check_runs`.

For each check with `conclusion` not `success`, `neutral`, or `skipped`, do the
following. `skipped` is a job that intentionally did not run (a path filter, an
`if:` condition that evaluated false); it is not a failure and needs no fix, and
counting it as one manufactures a finding for a check that never actually ran. A
`null` conclusion means still in progress, not failed; if `get_check_runs`
returns any, treat those as not-yet-decided and skip them here rather than
folding them into the failing set.

- Record: check name, conclusion, run URL
- **Identify failing step name first (reduces log noise):**

  ```bash
  gh run view {RUN_ID} --repo {OWNER}/{REPO} \
    --json jobs \
    --jq '.jobs[] | select(.conclusion=="failure") | {job:.name, steps:[.steps[]|select(.conclusion=="failure")|.name]}'
  ```

  The failing step name alone often identifies the fix (e.g., "Verify committed
  OpenAPI spec is current" => regenerate and commit spec; "Validate PR title" => retitle).
  Use the step name to target the log grep rather than scanning the full log.

- Fetch failed job log, filtering known audit noise:

  ```bash
  gh run view {RUN_ID} --repo {OWNER}/{REPO} --log \
    | grep -A30 "{failing_step_name}" \
    | grep -viE "harden|stepsecurity|systemd|sudo|node\.js|deprecat"
  ```

  Repos using `step-security/harden-runner` with `egress-policy: audit` produce
  extensive audit output (systemd/DNS/sudo lines) that buries the actual failure.
  Targeting the failing step name avoids scanning 100 lines of infrastructure noise.

- Classify by check name pattern:

| Pattern in check name | Type | Fix approach |
| --- | --- | --- |
| Test, pytest | Test failure | Read output, fix test or impl |
| ruff, lint, Quality | Lint | `ruff check --fix`; manual for unfixable |
| format | Format | `ruff format` |
| basedpyright, type | Type-check | Fix annotations |
| Bandit, Security, security-analysis | Security | Fix flagged patterns |
| Dead Code, vulture | Dead code | Remove (confidence >= 90%) |
| Link, lychee | Links | Fix broken doc links |
| REUSE, License | License | Add/fix headers |
| Compatibility | Py version | Fix 3.10+ incompatibilities |
| SBOM | SBOM | Fix dependency declarations |
| SonarCloud | Quality gate | Defer to Step 1c |
| qlty | Quality gate | Defer to `context/quality-gates.md`'s Qlty procedure (pr-review Step 4, not the 1c summary below, which covers SonarQube only and never reads qlty findings); enumerate locally if the qlty CLI is available (see Step 5b) |
| Reusable workflow startup_failure (0 jobs, no logs, "workflow file issue") | Workflow-load failure | Not a step failure; diagnose at file/reference level. Check `uses:@<sha>` reachability via `gh api repos/<owner>/<repo>/compare/<default>...<sha>`; if `diverged` (orphaned by a squash-merge), re-pin to a SHA reachable from the reusable repo's default branch that contains the file and exposes the same `workflow_call` inputs. `contents?ref=<sha>` serves dangling commits, so existence checks mislead; use `compare`. Validate cheaply with `workflow_dispatch` on a throwaway branch (startup validation runs at load time, before job `if:`). When a failure appears after an edit, confirm causation by reverting the suspected change on the current base before committing to a fix direction. |
| Failing reusable-workflow check (job renders as `<workflow> / <job>`, caller uses `uses: org/repo/...@<ref>`) and the FIX is to the workflow body | Wrong-ref fix risk | Before authoring a fix, resolve the running definition. For a workflow consumed via `uses: ...@<sha>`, the running body is whatever that SHA resolves to; it is NOT necessarily the reusable repo's default branch. Read the caller's pinned ref and `gh api compare` it against main AND any open-PR branch heads to identify which definition actually runs and will become canonical. A fix landed on the wrong ref (e.g. main, when the caller pins a diverged in-flight rework branch) is cosmetic, will not clear the observed failure, and can collide with an open rework PR of the same file. Fix the ref that runs. |
| GitGuardian | Secrets | Alert user only, never auto-fix |
| Docs, Build & Deploy | Doc build | Fix markdown/config |
| Core Validation, PR Validation | PR rules | Fix commits, description, etc. |
| attestation verify / HTTP 5xx during tool install (e.g. `gh attestation verify` -> 500 installing Qlty CLI) | Transient infra | Remediation is a re-run, not a code change. Check UNSTABLE vs BLOCKED first (advisory checks need no action). `gh run rerun` is permission-blocked in review sessions (HTTP 401); fall back to a user UI "Re-run failed jobs" click or a heavyweight empty-commit retrigger. |
| pip-audit / osv-scanner / trivy / license / SBOM-drift / cert-expiry showing a NEW finding that was green at session start | External / newly-disclosed | Classify by input-provenance, not timestamp: if the failing STEP consumes the dependency tree or external/time-based state rather than the diff, it is not a session regression even though it appeared mid-session. Confirm the same step also fails on the base branch (or the advisory ID postdates the branch's last green run). Surface distinctly; prefer a version bump over an ignore/suppress entry per the Unfixed-CVEs policy. |

**Identify the failing STEP, not just the job, before classifying.** A job named
"Code Quality Checks" going red on a YAML-only diff is impossible at the linter level;
drilling to the failing step (e.g., "Dependency vulnerability scan" / pip-audit) reveals
the real, often diff-independent, cause.

**Establish causation before naming a cause.** The failing-step-name and scanner-exit-
code rules above both exist to serve one goal: know what actually failed before deciding
why. Do not name a cause from the first alarming line a log grep returns, and do not
write a grep that can only confirm a hypothesis already formed, since a search for the
term you expect to find will find it whether or not it is the real cause. Use the jobs
API's own structured per-step conclusion (`.jobs[].steps[].conclusion`) as the oracle for
WHAT failed, then read only that step's output, or its artifact, for WHY. When two or
more checks share a display name, resolve each to its `workflow_name` and failing step
via the jobs API before classifying or tiering either; the name alone cannot
disambiguate them, and attributing a finding to the wrong sibling check misdirects the
fix.

**For an auth-suspected failure, read the input echo before assuming a missing secret.**
GitHub renders a masked `name: ***` in an Actions log only for a registered, NON-EMPTY
secret (an unset secret prints nothing after the colon). A masked `***` is therefore
positive evidence the secret is present and non-empty; look downstream for the real error
rather than chasing a "secret not pulled" hypothesis. Diagnose from the actual error line,
not the assumed cause. One known cause of a claude-code-action failure that mimics an auth
problem: a dangling symlink into a submodule. If a `.claude/...` path symlinks into
`.submodules/` and the reusable's checkout omits `submodules: recursive`, the action aborts
with `ENOENT ... statx '.claude/...'`; the fix is to add `submodules: recursive` to the
checkout, not to touch the secret.

**A scanner's exit code is a verdict, not a diagnosis.** Tools invoked with a file-output
format (`osv-scanner --output=report.json`, `trivy --output`, `bandit -o report.json`)
write findings to an artifact and print only a summary plus exit code to stdout. Grepping
the log then surfaces only whichever noise IS printed (filtered/disputed advisories,
"Exit code: 1"), which actively misleads diagnosis toward the wrong cause. When the failing
step is a security/quality scanner: (1) detect `--output`/`-o`/`--format json` in the
step's args and, if present, download the report artifact (`gh run download -n <artifact>`)
and parse it; (2) if the artifact is absent (upload skipped because the scan step aborted
the job first), reproduce the scan locally against the worktree lockfiles with the same
config and read the result there. Treat "Exit code: 1" with no visible finding in the log
as a signal to go to the artifact or local reproduction, never as the finding itself.

See also [context/github-api-idioms.md](github-api-idioms.md) ("Scanner exit
codes: a verdict, not a diagnosis") for the cross-workflow version of the
scanner-artifact rule above.

**GitGuardian findings are history-scoped and incident-stateful, not tree-scoped.** The
table above marks GitGuardian "Alert user only, never auto-fix" for a different reason
than the usual code-review caution: the check cannot be cleared by iterating code in the
current tree. GitGuardian scans every commit in the PR's history, not just the tip, so
removing a flagged literal at HEAD does nothing if it was introduced earlier; the secret
has to be removed at its point of introduction (an autosquash fixup into the introducing
commit, or a full history rewrite). Separately, the GitHub App check reflects unresolved
incident state on GitGuardian's own dashboard: once an incident triggers, a fresh scan of
clean code does not auto-close it, only a dashboard action (resolve or ignore) or a
history rewrite does. Recognize the shape early: if the net PR diff has no literal
secret and the check is still red, further force-pushes will not clear it; hand the
dashboard action to the user rather than iterating. The check is typically non-required,
so the PR stays mergeable while this is pending.

## 1b. Review comments

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

**Filter out (non-actionable):**

- Resolved threads (`is_resolved: true`)
- Bot summary comments without inline suggestions (CodeRabbit walkthrough, etc.)
- Pure praise or acknowledgment

**Keep (actionable):**

- Unresolved threads with change requests
- Copilot suggestions (code blocks with `suggestion` markers)
- CodeRabbit inline suggestions
- Human change requests
- Bug reports, mismatch callouts, missing item flags

See also [context/github-api-idioms.md](github-api-idioms.md) ("Reviewer bot
identity: Copilot has two logins, not one") for the cross-workflow version of
the classifier rule above and the CodeRabbit rate-limit trap.

## 1c. SonarQube findings

**Abridged summary; `pr-review` Step 4 is authoritative.** The five steps below
are the happy path only, and they cover SonarQube exclusively; this summary does
not read or enumerate Qlty findings despite the CI-failure table above naming
"Step 1c" as where qlty defers to (that pointer means `context/quality-gates.md`'s
Qlty procedure under pr-review Step 4, not this SonarQube-only summary). The full
procedure lives in `workflows/pr-review.md` Step 4 (substeps 4a through 4g) and
covers cases this summary omits, including the pre-flight configuration check,
security hotspots, and the Qlty gate. If the two ever disagree, `pr-review` Step 4
wins. Read it rather than this list whenever detection does not succeed on the
first attempt.

1. Detect org from `.sonarlint/connectedMode.json` `sonarCloudOrganization`
   or `sonar-project.properties` `sonar.organization`
2. Route: `byronwilliamscpa` --> `mcp__sonarqube__`,
   `williaby` --> `mcp__sonarqube-williaby__`
3. Resolve project key from config files or `search_my_sonarqube_projects`
4. Fetch: `search_sonar_issues_in_projects(projects: [KEY], pullRequest: PR_NUMBER)`
5. Fall back to branch issues if PR not analyzed

**A SonarQube MCP server that fails to connect is not "no findings".** Both
servers are Docker-backed and routinely unreachable. A connection failure must be
recorded as `SONAR_FINDINGS: unavailable` and surfaced, never collapsed into an
empty finding set, or the fix run reports a clean quality gate it never actually
queried.

**Token discovery (safe form):** When checking for a SonarCloud token, check
specific known variable names by existence only -- never `env | grep`:

```bash
[ -n "$SONARQUBE_TOKEN" ] && echo "found SONARQUBE_TOKEN" \
  || ([ -n "$SONAR_TOKEN" ] && echo "found SONAR_TOKEN" || echo "not found")
```

If `SONAR_FINDINGS` already in context from pr-review, skip this step.

For each finding, record: file, line, rule key, message, severity.
Call `show_rule` for any unfamiliar key to get remediation guidance.

See also [context/github-api-idioms.md](github-api-idioms.md) ("An unreachable
MCP server is not an empty result set") for the cross-workflow version of the
MCP-unavailable rule above.
