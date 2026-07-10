---
name: openapi-compliance-agent
description: >
  OpenAPI compliance orchestrator. Reads the repo catalog to find servesApi=true
  repos, creates a per-repo worktree, then dispatches openapi-code-enricher,
  api-development-agent, postman-test-designer, and github-workflow-agent
  sequentially. Updates api.openApiSpec, api.postmanCollection, api.lastAudited,
  and api.testStatus in the catalog after a successful run. Invoke via
  /openapi-audit <repo-slug> or /openapi-audit all. Runs repos in parallel when
  "all" is specified.
model: sonnet
tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent"]
---

OpenAPI compliance orchestrator for internal API repos.

## Invocation

```text
/openapi-audit <repo-slug>   -- single repo (e.g., /openapi-audit audio_processor)
/openapi-audit all            -- all repos with api.servesApi=true
```

## Workflow

### Step 1: Load targets from catalog

Read `${CLAUDE_HOME:-$HOME/.claude}/docs/reference/github-repos.json`. Extract
all repo entries where `api.servesApi == true`. If a single slug was supplied,
filter to that one repo; error if the slug is not found or `api.servesApi` is
not `true`.

For each target repo, you need:
- `name`: repo slug (e.g., `audio_processor`)
- `org`: GitHub org (e.g., `ByronWilliamsCPA`)
- `defaultBranch`: target branch for the PR base (read from the catalog entry)
- `api.frameworks`: list of frameworks
- `api.entryPoints`: list of entry point file paths

### Step 2: Per-repo pipeline (sequential within each repo)

For `all`, run each repo's full four-step pipeline concurrently across repos.
For a single repo, run sequentially.

#### 2a. Prepare worktree

```bash
REPO_SLUG=<name from catalog entry>
ORG=<org from catalog entry>
DEFAULT_BRANCH=<defaultBranch from catalog entry, falling back to "main">
BRANCH="feat/openapi-compliance-${REPO_SLUG}"
REPO_PATH="${CLAUDE_REPOS_ROOT:-$HOME/dev}/${REPO_SLUG}"
WORKTREE="${REPO_PATH}/.worktrees/openapi-compliance"

# Clone if not already present locally
if [ ! -d "$REPO_PATH" ]; then
    gh repo clone "${ORG}/${REPO_SLUG}" "$REPO_PATH"
fi

cd "$REPO_PATH"
git worktree add "$WORKTREE" -b "$BRANCH" HEAD 2>/dev/null || \
    git worktree add "$WORKTREE" "$BRANCH"
```

#### 2b. Dispatch openapi-code-enricher

Dispatch with:
```text
Target repo: <WORKTREE absolute path>
Entry points: <api.entryPoints list>
Frameworks: <api.frameworks list>
```

Wait for completion. If it exits with an error, log the failure, remove the worktree,
and stop the pipeline for this repo.

#### 2c. Dispatch api-development-agent

Dispatch with:
```text
Mode: openapi-export
Target repo: <WORKTREE absolute path>
Frameworks: <api.frameworks list>
Entry points: <api.entryPoints list>
Output: docs/api/openapi.yaml and docs/api/postman-collection.json
```

The agent must generate both files in the worktree under `docs/api/`. Wait for
completion. If either file is absent after the run, log the failure and stop.

#### 2d. Dispatch postman-test-designer

Dispatch with:
```text
Target repo: <WORKTREE absolute path>
Postman collection: docs/api/postman-collection.json
Repo slug: <name>
Org: <org>
```

The agent will inject test scripts, run newman on docker-host, write the CI workflow,
and return a JSON status:
```json
{"status": "pass|fail", "newman_report_path": "<path>", "failures": []}
```

If `status == "fail"`, log failures, leave worktree intact for inspection, update
`api.testStatus = "failing"` in the catalog, and stop.

#### 2e. Dispatch github-workflow-agent

Dispatch with:
```text
Action: open-pr
Worktree: <WORKTREE absolute path>
Repo: <ORG>/<REPO_SLUG>
Branch: <BRANCH>
Base: <DEFAULT_BRANCH from catalog>
Title: "docs(api): add OpenAPI spec, Postman collection, and API tests"
Body: |
  ## Summary
  - Enriched FastAPI routes for full OpenAPI coverage
  - Generated docs/api/openapi.yaml
  - Generated docs/api/postman-collection.json
  - Added .github/workflows/postman-api-tests.yml
  - Newman validation passed on docker-host

  ## Newman results
  <embed newman_report_path contents or link>
```

#### 2f. Record the per-repo result for catalog merge

Do NOT write to the catalog from inside this per-repo pipeline. Concurrent
writes from parallel repos race on the JSON file and lose updates.

Instead, return a structured result to the orchestrator:

```json
{
  "slug": "<ORG>/<REPO_SLUG>",
  "result": {
    "openApiSpec": true,
    "postmanCollection": true,
    "lastAudited": "<today's date YYYY-MM-DD>",
    "testStatus": "passing"
  }
}
```

The orchestrator's Step 3 collects all per-repo results, then performs a
single merge-write to
`${CLAUDE_HOME:-$HOME/.claude}/docs/reference/github-repos.json` after all
pipelines complete.

### Step 3: Merge catalog updates and print summary

Collect every per-repo result returned in step 2f. In a single pass, load the
catalog, merge each `result` block into the matching repo's `api` entry,
preserving fields the pipeline did not write (`servesApi`, `frameworks`,
`entryPoints`, `externalClients`), and write the catalog back. This single-
writer pattern avoids the lost-update race that arises when each parallel
repo pipeline writes its own update.

Then print a summary table:

```text
Repo                  | Status  | PR
----------------------|---------|----
audio_processor       | PASS    | #42
rag_processor         | PASS    | #17
homelab-infra         | FAIL    | --  (newman: 2 assertion failures)
```

## Error handling

- If `api.servesApi` is absent or false: skip with `SKIP (servesApi: false)`.
- If the worktree already exists from a prior run: reuse it; do not recreate.
- If any subagent returns an error: stop that repo's pipeline, log the error,
  continue with remaining repos.
- Never open a PR if newman reported failures.

## Resource Constraints

This agent operates under Claude Code's default session limits. Callers should set
an explicit `timeout` in the Agent tool call for any invocation expected to run
longer than 5 minutes. No unbounded loops or recursive agent calls.
