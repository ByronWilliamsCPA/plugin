---
description: >
  Model and token usage reporting via ccusage. Summarizes per-project,
  per-model, and per-session token spend from local Claude Code transcripts,
  and checks the current five-hour billing block for loop safeguards.
  Also supports agents mode for per-agent usage, subagent tokens, and agent
  attribution via the agents-observe plugin.
  Triggers on: usage report, token usage, usage this week, how much have I
  used, model spend, cost report, five-hour block, usage blocks, agents mode,
  per-agent usage, subagent tokens, agent attribution, /usage-report.
tools: ["Bash", "Read"]
---

# Usage Report Skill

Summarize Claude Code model and token usage from local JSONL transcripts using
[ccusage](https://github.com/ryoppippi/ccusage). No daemon, no telemetry
backend; ccusage parses `~/.claude/projects/**/*.jsonl` on each run.

Background and tool selection rationale:
[usage-monitoring-survey.md](../../../docs/reference/usage-monitoring-survey.md).

## Invocation

```text
/usage-report [daily|weekly|monthly|session|blocks] [extra ccusage flags]
/usage-report agents [session-id]
```

Default mode when no argument is given: `daily` for the last 7 days, grouped
by project. Agents mode takes one optional argument, a session id (UUID),
instead of ccusage flags; see [Agents mode](#agents-mode).

## Workflow

1. If the mode is `agents`, stop here and follow the
   [Agents mode](#agents-mode) section below; ccusage has no `agents`
   subcommand and the rest of this workflow does not apply. Otherwise map
   the requested mode to a ccusage command (pin the version; do not use
   `@latest`):

   | Mode | Command |
   | --- | --- |
   | daily (default) | `npx -y ccusage@20.0.9 daily --instances --since <YYYYMMDD> --json` |
   | weekly | `npx -y ccusage@20.0.9 weekly --json` |
   | monthly | `npx -y ccusage@20.0.9 monthly --json` |
   | session | `npx -y ccusage@20.0.9 session --json` |
   | blocks | `npx -y ccusage@20.0.9 blocks --active --json` |

   For daily mode, compute `<YYYYMMDD>` first with a separate command:
   `date -d '7 days ago' +%Y%m%d` (GNU date); on BSD/macOS use
   `date -v-7d +%Y%m%d`. Substitute the literal result into `--since`;
   do not embed the `date` command inside the ccusage invocation.

2. Run the command with Bash. Append extra user-supplied flags only when they
   match documented ccusage reporting options: long-form `--flag` or
   `--flag value` where the value is alphanumeric, a date, or a simple path
   (a relative path containing no `..` components, or an absolute path under
   `~/.claude/` or `/tmp/`). Never pass `--config`: it points ccusage at an
   arbitrary local file and is not a reporting flag. Never interpolate free
   text into the command line; reject any argument containing shell
   metacharacters (`;`, `|`, `&`, `$`, `>`, `<`, `(`, `)`, backslashes,
   single or double quotes, backticks, newlines) and say why.

3. Summarize the JSON. Lead with totals, then the top contributors:
   - Total tokens (input, output, cache read, cache creation) and estimated
     cost for the period.
   - Top 5 projects by token volume (daily/monthly modes).
   - Per-model split: tokens and estimated cost by model id. Flag any result
     that contradicts the CLAUDE.md Model Selection policy (for example, Opus
     spend on read-only exploration work).
   - For `blocks`: current block elapsed/remaining time, tokens consumed,
     and burn rate.

4. Always state the cost caveat once: ccusage costs are estimates against API
   list pricing; on a Max subscription they are a relative spend signal, not
   a bill.

## Agents mode

Agents mode queries the agents-observe plugin REST API (v0.9.11) for
per-subagent token attribution parsed from session transcript JSONL files.
It complements ccusage: ccusage aggregates by model across all sessions;
agents mode shows which specific subagents drove spend within a session.
Pinned to agents-observe v0.9.11; on future plugin upgrades, re-verify port
4981 and the endpoint paths in steps 1-3 remain valid.

Port discovery: the default port is 4981, overridable with the
`AGENTS_OBSERVE_SERVER_PORT` env var. When the preferred port is busy at
container start, the plugin falls back to a Docker-assigned port and writes
the actual value to
`~/.claude/plugins/data/agents-observe-agents-observe/server-port`. If the
health check below is refused on the expected port, read that file and
substitute its port into every URL in steps 1-3.

Argument validation: a session id passed as an argument must match the UUID
pattern `[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}`
before use. Reject anything else and say why; never interpolate unvalidated
argument text into a curl command line. This mirrors the metacharacter
rejection rule in Workflow step 2.

### 1. Health check and wake

```bash
curl -s http://127.0.0.1:4981/api/health
```

Expected shape: `{"ok":true,"id":"agents-observe","version":"..."}`.

On connection refused, the container is stopped. Wake it with:

```bash
docker start agents-observe
```

Then retry the health check. If still down after the docker start, the
agents-observe plugin appears unavailable; see
[usage-monitoring-survey.md](../../../docs/reference/usage-monitoring-survey.md)
section 4 (Layer 3) for setup instructions.

### 2. List recent sessions

```bash
curl -s http://127.0.0.1:4981/api/sessions/recent
```

Returns an array of session objects, each with: `id`, `projectSlug`,
`startCwd`, `status`, `agentCount`, `eventCount`, `agentClasses`.

Select the session to inspect: default to the most recent session whose
`projectSlug` matches the current project. Accept an explicit session id
as a `/usage-report agents <session-id>` argument to override, validated
against the UUID pattern above before use.

### 3. Fetch per-subagent token stats

```bash
curl -s http://127.0.0.1:4981/api/sessions/<id>/transcript-stats
```

Returns a `subagents[]` array. Each entry has: `agentType`, `description`,
`model`, `inputTokens`, `outputTokens`, `cacheReadTokens`, `costCents`.
Also returns a `byModel[]` breakdown and a `summary` aggregated across the
root agent and all subagents.

### 4. Summarize

Report:

- Top 5 subagents by total tokens (inputTokens + outputTokens), each with
  agentType, description, model, and costCents.
- Delegation chain observed: root model -> subagent model(s).
- Policy flags: note any subagent whose model contradicts CLAUDE.md Model
  Selection policy. Expected: Explore subagents on `claude-haiku-*`; general
  subagents on `claude-sonnet-*`; Opus or Fable only when explicitly justified.

### 5. Caveats

- transcript-stats requires the session JSONL to still exist on disk. For
  deleted or cleaned transcripts the endpoint returns `file_not_found`. Query
  during or shortly after sessions, not on old history.
- Data is only present for sessions run while the agents-observe plugin was
  active. Sessions from before plugin installation have no subagent records.
- `sessions/recent` returns an unpaginated array with no limit parameter in
  v0.9.11; on installs with long session history the response grows
  unbounded. Pipe through `jq '.[0:20]'` when only recent sessions matter.

## Loop circuit breaker check

When invoked as part of `/loop` safeguards (see
`.claude/rules/loop-recipes.md`), run the `blocks` mode and report:

- tokens consumed in the active five-hour block,
- projected tokens at the current burn rate,
- a clear PASS/STOP line: STOP if the projection exceeds the block limit
  ccusage reports (or the user-specified budget passed as an argument).

## Output

Terminal summary only; do not write report files unless the user asks.
Keep the summary under 30 lines: totals, top projects, per-model table,
one caveat line.
