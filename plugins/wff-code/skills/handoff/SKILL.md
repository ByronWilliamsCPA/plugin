---
name: handoff
description: >
  Generate a structured handoff document AND a paste-ready kickoff prompt for
  session continuity. Auto-activates on: handoff, session end, context handoff,
  end of session, switch context, next session, wrap up session
allowed-tools:
  - Read
  - Write
  - Bash
  - Glob
---

# Handoff Skill

Capture current session state so the next session resumes without context loss.
This skill produces **two** artifacts, by design:

1. **Kickoff Prompt**: a short, paste-ready block printed to chat. This is the
   thing you copy into the new session. It is budgeted small (target <= 200
   words) so it seeds a fresh session without re-bloating its initial context.
2. **Full Handoff Doc**: saved to `~/.claude/logs/handoffs/handoff-<ts>.md`, a
   gitignored, durable runtime path (never committed; survives worktree removal
   and `/close-clean`). The new session reads it ON DEMAND via the prompt path.

The split resolves the tradeoff: the new session starts from the lean prompt and
pulls the full doc only on demand. Do not paste the full doc into the session.

## Invocation

```text
/handoff
```

## Workflow

### 1. Gather state

```bash
git branch --show-current
git status --short
git log --oneline -10
git diff --stat
```

Also capture, from the conversation and tools: the original goal of the
session, in-progress TODO items, current test state (pass/fail counts and the
names of any failing tests), and the verbatim text of any active error. These
feed the template fields below; gather them now so the doc is complete.

### 2. Write the full handoff doc

Write to the durable, gitignored runtime path (never committed; survives
worktree removal and `/close-clean`). Run `mkdir -p ~/.claude/logs/handoffs`,
then write `~/.claude/logs/handoffs/handoff-$(date +%Y%m%d-%H%M).md`.

The template's required fields are a **superset of the CLAUDE.md "Compact
Instructions" preserve-list**, so a handoff is never weaker than an autocompact
summary. Every field is mandatory; write "none" rather than dropping a heading.

```markdown
# Session Handoff: {date}

## Goal / Intent
[The WHY. One or two sentences: what this session set out to achieve and the
problem behind it. This is the highest-value anti-context-loss field, so it
leads.]

## Current State
[Active branch; uncommitted/staged changes (notable unstaged work named);
test state with pass/fail counts and specific failing test names; any active
error message quoted VERBATIM, not paraphrased.]

## What Was Done
[Completed items, each with the file:line it touched.]

## What Remains
[Incomplete items, ordered by priority. For each, state the GOAL (required);
add the assumed MECHANISM only if flagged as an assumption.]

## Key Decisions
[Each decision with its rationale: "chose X over Y because ...", not just "chose
X". Architecture/design choices belong here with the reasoning, not the bare
verdict.]

## Dead Ends / Rejected Approaches
[What was tried and ruled out, and why. Prevents the next session from
re-spending budget rediscovering a known dead end.]

## User Corrections / Constraints
[User-specific corrections made this session ("no, do it this way instead") and
any standing constraints the next session must honor.]

## Files Touched
[path:line for each, with one phrase on WHY it matters. Not a bare
`git diff --stat` dump.]

## How to Resume
[The single immediate next action, then subsequent steps with exact commands.
Specific enough to follow without this conversation.]

## Gotchas
[Non-obvious context: workarounds, known issues, assumptions. Tag anything not
verified against live source as `[VERIFY]`.]
```

Keep the full doc complete but lean: mirror the Compact Instructions "do not
preserve" list. No raw tool-call logs, no pasted command output, no exploratory
detours that did not inform the result. Summarize conclusions, not transcripts.

### 3. Emit the kickoff prompt

Append a `## Next-Session Kickoff Prompt` section to the doc, AND print the same
block to chat so it can be copied immediately. Budget: <= ~200 words. It must be
self-contained enough to orient the new session even if the full doc is never
opened:

```markdown
## Next-Session Kickoff Prompt

Resuming work on {repo} (branch `{branch}`). Goal: {one-line goal}.

First, refresh state before acting (the handoff is a snapshot, treat What
Remains as a hypothesis):
    git fetch --all && git status --short && git log --oneline -5

Immediate next action: {the single most important next step}.
Hard constraints: {any standing user constraint, or "none"}.
Full handoff (read on demand for detail): ~/.claude/logs/handoffs/handoff-<ts>.md.
```

### 4. Self-verify (pre-flight, mandatory)

Re-read the output and check it against the rules before reporting. A skill that
produces prose deliverables must verify its own output.

Use a portable check, not `grep -nP '\x{2014}'`: on a grep build without working
`-P` the pattern errors and an `|| echo "no em-dash"` fallback reports clean on
the failure (a false pass). Python cannot false-pass:

```bash
HANDOFF_FILE=~/.claude/logs/handoffs/handoff-...md   # the file written in step 2
python3 - "$HANDOFF_FILE" <<'PY'
import sys
text = open(sys.argv[1], encoding="utf-8").read()
problems = []
if "\u2014" in text:  # em-dash (escaped so this file stays em-dash-free)
    problems.append("em-dash present (replace with comma, semicolon, or colon)")
required = [
    "Goal / Intent", "Current State", "What Was Done", "What Remains",
    "Key Decisions", "Dead Ends", "User Corrections", "Files Touched",
    "How to Resume", "Gotchas", "Next-Session Kickoff Prompt",
]
problems += [f"missing section: {h}" for h in required if f"## {h}" not in text]
print("FAIL:\n  " + "\n  ".join(problems) if problems else "self-check OK")
PY
```

Fix any em-dash (replace with comma, semicolon, colon, or restructure), add any
missing section, and confirm the kickoff prompt is within budget before
declaring the handoff complete.

### 5. Report

Print the kickoff prompt to chat and report the full doc's path so it can be
referenced. Tell the user to paste the kickoff prompt (not the full doc) into
the new session.

## Authoring rules (load-bearing digest)

- **Separate GOAL from MECHANISM** for every prescribed action; the goal is
  required, the mechanism is an optional, clearly-flagged assumption.
- **Distinguish verified from speculative**: tag any field name, flag, endpoint,
  or identifier not checked against live source as `[VERIFY]`.
- **Quote counts and tallies verbatim** from the source (Obs 276); if the source
  is internally inconsistent, state the discrepancy rather than resolving it.
- **Add a consumer trace to every file:line edit spec** (Obs 414): name the gate
  or script that actually reads the artifact, so the next session does not harden
  a dead path.

> Full author standards (paste-correct artifacts, coupled-invariant checklists,
> durable-artifact checks, supersession banners) and the orphaned-branch /
> stash git-forensics procedure: see
> [`context/handoff-quality-standards.md`](context/handoff-quality-standards.md).

## Consuming a handoff (pre-flight digest)

Before acting on any handoff:

- **Re-verify current state** (`git fetch --all`, `gh pr list`): branches and PRs
  advance after a handoff is written. Treat "What Remains" as a hypothesis and
  diagnose current state first.
- **Verify identifiers before building**: confirm every check ID, path, flag, or
  function name named in the doc still exists in live source.
- **Treat completed-fix claims as hypotheses** when a live symptom contradicts
  them; the live system wins.

> Full consumer pre-flight (multi-session claim/lock, re-resolving pinned refs,
> schema probes): see
> [`context/handoff-quality-standards.md`](context/handoff-quality-standards.md).
