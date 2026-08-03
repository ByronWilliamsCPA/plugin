---
name: task-observer
user-invocable: false
description: >
  Monitors task execution for skill improvement opportunities. Use this skill
  during ANY multi-step task, agentic workflow, or substantive work session where
  the agent is using tools and producing deliverables. It captures patterns, user
  corrections, workflow insights, and methodology worth preserving as reusable
  skills. Also triggers during post-task feedback discussions and when the user
  explicitly mentions skill observations, improvements, the observation log,
  skill taxonomy, or asks the agent to watch for skill opportunities. Also known
  as "One Skill to Rule Them All" — trigger on this phrase too. IMPORTANT:
  this skill should be invoked at the start of every task-oriented session — if
  you are about to use tools to produce deliverables, invoke this skill first.
  For reliable activation, pair this description with a CLAUDE.md instruction
  or harness-level session-start hook (see Recommended Activation Setup) —
  description-level matching alone is not enforceable.
---

# Task Observer — Continuous Skill Discovery & Improvement

**Created by Eoghan Henn / [rebelytics.com](https://rebelytics.com)** (CC BY 4.0). Also known as "One Skill to Rule Them All".

**Activation note:** For reliable session-start activation, pair this skill
with a CLAUDE.md instruction or harness-level hook (see Recommended
Activation Setup). The description matches against task-oriented language,
but description-level matching alone can be missed when the agent is focused on
the task itself. The skill works as a skill; it works *reliably* as a skill
plus a structural trigger.

---

## User Documentation

Full detail: README.md (author attribution, licence, rationale for this skill, and user-facing onboarding pointers; read when introducing this skill or its licensing to a user).

---

## Conventions

`[workspace folder]` refers to the user's persistent workspace directory —
the location where files survive between sessions. In Cowork, this is the
folder selected at session start. In Claude Code, this is the project root.
In web-based chat interfaces without filesystem access, the skill shifts
into handoff doc mode (see Environment Compatibility, context/lifecycle.md)
and the user manages these files manually.

---

## Recommended Activation Setup

This skill needs to be invoked at the start of task-oriented sessions to work
effectively. Because skill invocation depends on the agent matching the user's
request against skill descriptions, a skill that monitors *all* tasks can be
overlooked when the agent is focused on the task itself.

To maximise activation reliability, add the following instruction to your
configuration file (e.g., CLAUDE.md, project instructions, or equivalent):

```
At the start of any task-oriented session — any interaction where you will
use tools and produce deliverables — invoke the task-observer skill before
beginning work. This ensures skill improvement opportunities are captured
throughout the session.

When loading any skill, check the observation log for OPEN observations
tagged to that skill. Apply their insights to the current work, even if
the skill file hasn't been updated yet. This enables immediate application
of observations before they're permanently integrated during the weekly
review.
```

This structural trigger works alongside the skill's description-level triggers.
The description is designed to match broadly against task-oriented language
("multi-step task", "agentic workflow", "work session", "tools and
deliverables"), but a configuration-level instruction provides an additional
safety net that doesn't depend on description matching alone.

**Note for all users:** Once CLAUDE.md or equivalent configuration is in place
with the activation instruction above, the description-level triggers serve as
a backup rather than the primary mechanism. This dual-layer approach prevents
the skill from being skipped in sessions where description matching alone might
miss the invocation signal.

**Anti-pattern to avoid:** Relying on one skill to load another is fragile
compared to loading both independently from CLAUDE.md. If task-observer depended
on another skill to invoke it, a breakdown in that chain would silence all
observation activity. Instead, load both task-observer and any related skills
directly from your configuration instructions.

### Configuration Detection & Compaction Behaviour

Full detail: context/lifecycle.md (read when performing that workflow) -- covers config-file detection at session start and re-activation behaviour after context compaction.

## The Pre-Flight Principle

Full detail: context/taxonomy.md (read when performing that workflow).

## Self-Enforcement

This skill practises what it preaches. Before surfacing observations at end
of session, verify:

1. Were observations logged throughout the full session — including during
   post-task feedback, discussion phases, and reflective conversations, not
   just during active tool use?
2. Were observations logged silently without interrupting the user's flow?
3. Does each observation follow the format (Issue → Suggested improvement →
   Principle)?
4. Is each observation tagged with the correct type (open-source or internal)?
5. For any observations about existing skills, does the suggested improvement
   reference the specific section or rule?
6. For any observation tagged `type: open-source`, does the Principle field
   contain any client-identifying information? If so, generalise it before
   surfacing.
If any observation fails these checks, fix it before surfacing.

---

## Skill Taxonomy, Licensing & Attribution Template

Full detail: context/taxonomy.md (read when performing that workflow) -- covers the open-source/internal skill taxonomy, licence options, and the author attribution template.

## Observation Protocol

### When to Observe

Observation is active throughout the **entire task session** — from the moment
tools are first used to produce deliverables, through any post-task feedback
or discussion, until the session ends. This includes:

1. **Active task execution** — creating documents, analysing websites,
   implementing structured data, writing code, building presentations, and
   similar substantive work.

2. **Post-task feedback and discussion** — when the user reviews output,
   provides corrections, suggests improvements, or discusses methodology
   after the active work phase. User feedback during these discussions is
   often the highest-signal input for skill improvement and must be captured
   with the same diligence as observations made during execution.

3. **Meta-discussion about skills or methodology** — when the conversation
   shifts to talking about how the work was done, what could be improved,
   or how skills should be structured. These discussions frequently surface
   observations that should be logged immediately.

4. **Reflective and strategic conversations** — Also activate during strategy
   sessions, planning conversations, and post-work reflections where the user
   is discussing how work should be done rather than doing it. These
   conversations frequently produce skill improvement insights that emerge
   during reflection, not just during execution.

**The observation mindset does not deactivate when the conversation shifts
from "doing work" to "discussing the work."** If the user provides feedback
about methodology, naming, skill design, or workflow improvements, log it as
an observation immediately, even if the conversation is in a discussion or
review phase rather than active task execution.

Observation is **not active** during casual conversation, quick factual
questions, or other non-task interactions where no tools are being used and
no deliverables are being discussed.

### What to Watch For

Full detail: context/taxonomy.md (read when performing that workflow).

### How to Log

Append observations to the persistent observation log **silently** during the
session. The user should not be interrupted by the logging process.

**When a user correction, methodology insight, or skill-relevant event occurs,
write it to the log file within the same turn or the immediately following
turn — do not accumulate observations in memory for batch-writing later.** The
act of writing is the enforcement mechanism; mental notes are not observations.
Tie observation flushing to something that already happens, not to a separate
act of remembering. Writing at the moment of noticing is the primary
mechanism. The two backstops below are ordered by how little each depends on
the agent's attention.

**Backstop 1, structural: the Stop hook.** At turn end,
`scripts/hooks/task-observer-flush-check.py` compares the observation count
against a baseline recorded at session start by
`scripts/hooks/task-observer-reminder.sh`. When a session used tools to
produce deliverables and logged nothing, the hook blocks turn end once and
asks for a flush. It depends on nothing the agent has to remember, which is
why it ranks first. An earlier version of this skill bound the checkpoint to
TodoWrite completions, so a session that never called TodoWrite had no trigger
at all; that gap is what the hook closes.

**Backstop 2, behavioural: flush at batch boundaries.** Immediately before
dispatching the next subagent, marking a task item completed, or starting a
new unit of work, WRITE any accumulated observations. The write is the
checkpoint, not a mental note to write later. Subagent-controller sessions are
the highest-risk case: one six-task session ran roughly twelve subagent
dispatches with several correction moments and wrote zero observations until
the closing step. A checkpoint that competes with cognitively demanding work
loses to that work, so attach the write to a step that has to happen anyway.

**Before assigning any observation number, run a mandatory pre-logging step:**
Search the entire log file for all lines matching the pattern `### Observation \d+:`,
extract the highest observation number already in use, and increment from there.
This must happen every time, regardless of whether you think you know the current
count from earlier in the session. Never rely on session memory or summaries for
the next number. Always read the actual log file. A one-liner like the following
suffices:

```bash
# GNU grep (Linux, Cowork):
grep -oP '### Observation \K\d+' log.md | sort -n | tail -1

# macOS / POSIX-compatible alternative:
grep -o '### Observation [0-9]*' log.md | grep -o '[0-9]*' | sort -n | tail -1
```

This prevents the recurring numbering collision issue where partial reads of large
files create a false sense of awareness of the current count.

**Write-time verification assertion (mandatory):** The pre-logging step above
catches honest mistakes, but is vulnerable to parallel-session scenarios where
multiple task-oriented sessions on the same day each compute "next number"
against a snapshot and then collide on write. To catch this class of collision,
after determining the proposed next number and immediately before appending,
re-read the log and assert the number does not already exist:

```bash
PROPOSED=$(( $(grep -oP '### Observation \K\d+' log.md | sort -n | tail -1) + 1 ))
grep -qE "^### Observation ${PROPOSED}:" log.md && {
  echo "COLLISION on #${PROPOSED} — another writer has claimed this number"; exit 1; }
# If assertion passes, proceed with the append using #${PROPOSED}.
```

If the assertion fires, increment past all existing numbers (not just by 1)
and re-check. Treat an assertion failure as a meta-observation worth logging
— it indicates either a parallel-session collision or a stale read elsewhere
in the workflow.

**Post-write verification (mandatory — closes the TOCTOU race):** The
pre-write assertion catches stale-read collisions but cannot close the
time-of-check-to-time-of-use race between the assertion and the append.
In shell, `grep -q && cat >> ...` is two separate operations: the grep
passes at T0, the append lands at T1. Any other session that appends
between T0 and T1 can claim the same number — this race has been observed
in production, producing duplicate observation pairs in the active log.

After the append, re-read the log and count occurrences of the just-written
observation number. If the count is greater than 1, a parallel session has
collided — renumber the current session's entry to `max+1` in place via
`sed`. Concrete shell:

```bash
WRITTEN=$(grep -cE "^### Observation ${PROPOSED}:" log.md)
if [ "$WRITTEN" -gt 1 ]; then
  # Find my line (the last occurrence, since I just appended) and renumber
  MY_LINE=$(grep -nE "^### Observation ${PROPOSED}:" log.md \
    | tail -1 | cut -d: -f1)
  NEW_NUM=$(( $(grep -oP '^### Observation \K\d+' log.md \
    | sort -n | tail -1) + 1 ))
  sed -i "${MY_LINE}s/^### Observation ${PROPOSED}:/### Observation ${NEW_NUM}:/" log.md
fi
```

This turns the pre-write assertion into a pre-and-post pair. Pre-write
catches stale-read collisions cheaply; post-write catches race collisions
by renumbering instead of failing. Either way, the log ends up with no
duplicates. Alternative approaches — lockfile, atomic append, transactional
write — are heavier and require more infrastructure; the
post-write-verify-and-renumber pattern works with plain shell and
self-heals.

**Why both checks are required:** Stale-read collisions and race-condition
collisions are different classes of error. The pre-write assertion closes
the first; the post-write verification closes the second. Stacking more
pre-write layers does not close race cases — only a post-write check can.
When the shared state is a log file written by parallel agents, the
reliable pattern is check-then-act-then-verify.

**Session-start staleness check:** At the start of any task-oriented session,
note the modification time of `log.md`. If it was modified in the last few
hours (i.e., a parallel or recent session has been writing to it), be extra
cautious about the numbering pre-check — do not trust any mental model of
"current number" and always re-read the log immediately before appending each
observation, not just once at session start.

**Format and insertion rules:** Always use the `### Observation NNN:` format. Always append new observations to the END of the log file. Never insert observations mid-file. Never use alternative ID formats (e.g., `OBS-YYYY-MMDD-NN`). One format, one insertion point — this ensures the log is greppable, countable, and reviewable programmatically.

Each observation follows this format:

```markdown
### Observation [N]: [Short descriptive title]
**Status:** OPEN

**Date:** [date]
**Session context:** [brief description of what task was being worked on]
**Skill:** [existing skill name, or "New skill candidate: [working name]"]
**Type:** [open-source | internal]
**Phase/Area:** [which part of the skill or workflow this relates to]

**Issue:** [What happened or what was observed. Be specific — include what
The agent did, what the user corrected, or what pattern emerged. Include enough
detail that someone reading this weeks later can understand the context
without having seen the original conversation.]

**Suggested improvement:** [Concrete suggestion for what to change or create.
For existing skills, reference the specific section or rule. For new skills,
describe the scope and key components.]

**Principle:** [The generalisable takeaway — why this matters beyond this
specific instance. This is the most important part. It turns a single
observation into a reusable insight.]
```

This format was refined through iterative real-world use. The structure works
because it forces specificity (Issue), actionability (Suggested improvement),
and generalisation (Principle).

**The `**Status:** OPEN` line is mandatory and must be the first field, directly
under the header.** The entire observation lifecycle (OPEN, ACTIONED, DECLINED)
and every review query keys on this line. An observation logged without it is
invisible to the weekly review's OPEN filter, so it silently accumulates as an
unprocessed backlog that no review ever surfaces. This is a real failure mode:
the field was once present only in the Log Structure example below and absent
from this format block, and every observation logged for ten days afterward
dropped it, producing 170 status-orphaned entries. The fix was structural,
the field now lives in the template agents actually copy. When logging, copy
this whole block including the Status line; never reconstruct the format from
memory.

**Context preservation check:** When logging an observation, verify that all
information needed to act on it is available in the shared folder. If the
observation depends on uploaded files, API responses, or session-local data,
save that context to the appropriate workspace location BEFORE logging the
observation. Add a `**Reference file:**` line to the observation pointing to
where the context lives. Observations that reference data only available in
the current session (uploaded files, API outputs, in-memory results) are
incomplete — a future review session will have the observation but not the
data needed to implement it.

### Handoff Doc Analysis & Archival on Write

Full detail: context/lifecycle.md (read when performing that workflow) -- covers extracting observations from a handoff doc and the event-driven archival mechanism.

## Confidentiality Safeguards

Full detail: context/confidentiality.md (read when performing that workflow).

## Surfacing Protocol

### Default Cadence

Surface all observations at the end of the session. Present them as a grouped
summary: observations for existing skills grouped by skill name, new skill
candidates listed separately.

### Surface Earlier When

- An observation requires user input to be complete or accurate (e.g., "Is
  this a pattern you want captured, or was this a one-off?")
- An observation reveals a skill is actively producing wrong output in the
  current session and the user should be aware
- Multiple observations cluster around the same skill, suggesting it needs
  immediate attention rather than end-of-session review

### How to Surface

- Present observations concisely: title, skill, and a one-sentence summary
- For each, indicate whether it's a new skill candidate or an improvement
  to an existing one
- Indicate the suggested type (open-source or internal)
- Ask the user which (if any) they want to act on
- For items the user wants to pursue, hand off to the skill-creator skill
  for the actual building or improvement work

---

## Observation Log Management

### Location

The observation log persists between sessions in the user's workspace folder.
Create the log file on first use if it doesn't exist. Default path:

```
[workspace folder]/skill-observations/log.md
```

### Log Structure

```markdown
# Skill Observation Log

Observations captured during task-oriented work. Each entry identifies a
potential skill improvement or new skill opportunity.

**Status key:** OPEN = not yet actioned | ACTIONED = skill updated/created |
DECLINED = user decided not to pursue

---

## [Date or Session Identifier]

### Observation 1: [Title]
**Status:** OPEN
[... full observation format ...]

### Observation 2: [Title]
**Status:** ACTIONED — Applied to [skill-name], rule 35
[... full observation format ...]
```

### Session Start Protocol

This is the single entry point for all session-start checks. Run through
these steps at the start of each task-oriented session:

1. **Check whether files exist.** If the observation log or cross-cutting
   principles file don't exist yet, this is a first-time setup — create
   them using the templates in the Log Structure section (below in this
   document) and the Cross-Cutting Principles File Structure section (see
   Principle Propagation, context/lifecycle.md). If the files already
   exist, proceed to step 2.

2. **Scan for relevant context.** Read any OPEN observations and active
   cross-cutting principles. Don't surface them unprompted unless they're
   directly relevant to the current task — just hold them in awareness.

3. **Check the weekly review trigger.** Read the timestamp in
   `[workspace folder]/skill-observations/last-review-date.txt`. If the
   file doesn't exist or the date is more than 7 days ago, trigger the
   Weekly Comprehensive Review (described in full in context/lifecycle.md)
   before proceeding with the user's task. If fewer than 7 days have
   passed, proceed normally.

4. **Check the configuration file.** Run the config detection described in
   Detecting the Configuration File (context/lifecycle.md, under
   Recommended Activation Setup). This runs once per session.

### Keeping the Log Clean

Log cleanup is handled by the archival mechanism (event-driven, runs on every log write). Full detail: context/lifecycle.md, Archival on Write (read when performing that workflow).

## Review & Update Lifecycle

Full detail: context/lifecycle.md (read when performing that workflow) -- covers acting on observations (small/substantial changes, new skills), cross-environment skill-file handling, cross-cutting principle propagation, the comprehensive (weekly) review procedure, delivering updated skills, and environment compatibility.

## Quick Reference

| Question | Answer |
|----------|--------|
| When do I observe? | Throughout the full task session, including post-task feedback and reflective conversations |
| How do I log? | Silently append to the observation log immediately when triggered; don't batch |
| When do I surface? | End of session, or earlier if needed |
| How do I activate reliably? | Add a config-level instruction (see Recommended Activation Setup) |
| Open-source or internal? | Default to open-source when possible |
| Licence for open-source? | CC BY 4.0 recommended |
| Small fix or skill-creator? | Needs testing → skill-creator (if available). For internal skills with established requirements, writing directly is efficient. Clearly additive → apply directly |
| What format? | Issue → Suggested improvement → Principle |
| Author attribution? | Required for open-source skills; use the template |
| Cross-cutting principle? | Add to principles file, enforce during regeneration |
| Confidentiality check? | Five layers: observation, pre-creation, post-draft, structural, cross-product re-identifiability |
| No persistent storage? | Handoff doc mode — observations surfaced in a structured doc at session end |
| Scheduler automation? | Step 0 of weekly review auto-checks; silent until tool is available |
| Observation numbering? | Mandatory pre-logging search ensures no collisions; never use cached numbers |
| Log archival? | Event-driven — resolved entries are archived on the next log write |
| Simplification signals? | Watch for one-off rules, never-used sections, elaborate workflows users skip, and contradictions |
| Handoff doc analysis? | Systematically extract implied observations from action items, open questions, and narrative sections |
