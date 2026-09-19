# Task Observer -- Lifecycle Reference

Reference content for `task-observer` covering the review/update lifecycle: activation edge cases, archival mechanics, the mechanism used to act on observations, cross-environment skill-file handling, cross-cutting principle propagation, the comprehensive (weekly) review procedure, delivering updated skills, and environment compatibility. Read this file when performing one of those workflows; it is not loaded on every invocation of the skill.

---

## Detecting the Configuration File

At session start, the skill should check whether a configuration file
(CLAUDE.md, project instructions, or equivalent) exists and contains the
activation instruction. This detection serves two purposes:

1. **For users who already have the config:** Confirms the dual-layer
   activation is working. No action needed.

2. **For users who don't have the config:** The skill was activated via
   description matching alone, which is less reliable. Surface a brief
   suggestion to add the config-level instruction for more consistent
   activation in future sessions.

The detection approach depends on the environment:

- **Environments with file system access** (desktop tools, terminal-based
  tools): Check for a CLAUDE.md or equivalent file in the workspace root.
  If found, scan it for a task-observer activation instruction. If the file
  exists but doesn't mention task-observer, suggest adding the instruction.
  If no config file exists at all, suggest creating one.

- **Environments without file system access** (web-based chat): Check
  whether the system prompt or project instructions contain a task-observer
  activation instruction. If not, suggest that the user add one to their
  project settings or paste the instruction at the start of future sessions.

This check runs once at session start and does not repeat. Keep the
suggestion brief — one or two sentences, not a full tutorial.

## Compaction Behaviour

When a session context compacts mid-task, the CLAUDE.md structural trigger
is *intended* to re-invoke task-observer on the resumed session, on the
theory that the same activation instruction fires again because the
resumed session reads CLAUDE.md anew. **In practice this is not reliable.**
Multiple sessions, including two consecutive same-mechanism failures logged
within a single session, show logging staying dark across an entire
post-compaction stretch, sometimes for hours and dozens of tool calls,
only reconstructed retroactively at `/close`. Treat compaction as a
session-start event, not a continuation: on the first turn after a
compaction, re-read the log, re-establish the Stop-hook baseline from the
current count (a missing or stale baseline should be treated as "unknown,
assume unflushed," not skipped), and write one observation covering the
pre-compaction stretch before continuing the task. Observations from
before and after compaction still append to the same log file with
continuous numbering; only the automatic re-trigger is unreliable, not the
log's continuity.

This is still the primary reason the CLAUDE.md structural trigger exists:
description-level triggers alone would not reliably guarantee re-invocation
on a resumed session, because the resumed session's opening message may
not match task-observer's trigger phrases even when the ongoing task is
task-oriented. The structural trigger's presence reduces the risk; it does
not eliminate the need to verify logging resumed.

**Carried context needs re-verification before it is acted on.** A detail
that survives a summary, a subagent report, or the compaction itself has
been through a lossy channel and is not itself evidence about the
repository or the task state. One session was about to publish a
correction to a PR body based on a remembered detail from earlier context
("a fix agent shortened four contracts' pinned fields"); a direct diff
check showed the diff had never touched that field at all. Before acting
on any specific carried claim, especially when acting means publishing a
correction or a public statement: re-derive it from the primary source,
the diff, the file, the API response.

---

## Handoff Doc Analysis

When a handoff doc arrives for observation logging, extract observations
systematically from both explicit and implicit sources:

1. **Log all explicitly stated observations first.** These are easy to
   surface and should be logged without filtering.

2. **Then systematically analyse the full document.** Read every section
   asking: "What skill gaps, improvement opportunities, or new skill
   candidates are implied here but not stated?" Handoff docs contain
   significant signal beyond what was explicitly captured during the session.

3. **Pay special attention to:**
   - Action items (each one may imply a missing skill or workflow)
   - Open questions (unresolved ambiguity often signals a decision framework gap)
   - The "work completed" narrative (patterns across work items may reveal meta-skills)
   - Session notes (reflective insights about process, not just content)

4. **Log the additional observations with clear attribution.** Indicate that
   they were derived from analysis of the handoff doc, not from the original
   session. This preserves the distinction between stated and derived insights.

## Archival on Write

The observation log is kept lean through archival that runs at the start of
each comprehensive review (Step 1), not on every log write. A normal task
session that only appends observations never triggers archival, so the
active log grows unbounded between reviews; one active log reached 1.3 MB
and 461 resolved entries before a review finally cleared it. This is
expected; it is why review cadence (see Comprehensive Review below, and the
backlog-size trigger in the Session Start Protocol) matters.

**Defining "from a previous update":**
The phrase "from a previous update" means entries whose status was already
resolved in a *previous SESSION or prior log write*, not entries marked
ACTIONED or DECLINED in the current session. Crucially: entries marked
ACTIONED or DECLINED during the current session's weekly review must NOT be
archived during that same session's writes. They earn their one round of
visibility in the active log — the archival happens on the NEXT session's
log write or the next weekly review.

**Archival Timing During Weekly Reviews:**
The weekly review performs archival in two phases:

1. **Step 1 (at review start):** Archive entries from previous sessions.
   Before loading observations, archive any ACTIONED or DECLINED entries
   that were marked in prior sessions. This clears old resolved items.

2. **Step 6 (after marking ACTIONED):** Do NOT archive immediately. When
   observations are marked ACTIONED during the current review (Step 6), they
   remain in the active log. Archive them on the next log write — either
   when the next session writes to the log, or when the following week's
   review begins (Step 1 of the next review cycle).

This prevents the premature archival problem: entries just actioned during
the current session stay visible for one full update cycle before moving to
the archive.

**Archive File Structure:**
Move resolved entries to an archive file at:

```
[workspace folder]/skill-observations/archive/log-[date].md
```

where `[date]` is today's date in `YYYY-MM-DD` format.

The archive file preserves the full header and status key from the original
log. After archiving, the active `log.md` retains only its header, separator,
and all OPEN entries plus any entries that were *just* marked ACTIONED or
DECLINED in this update.

**Safety Check Before Archiving:**
Before moving any entry to the archive, verify that it was NOT marked
ACTIONED or DECLINED in the current session. If it was, keep it in the
active log. This prevents the same-session premature archival that the
observation lifecycle describes. One way to implement this: track a set
of entry IDs marked ACTIONED/DECLINED in the current session, and exclude
them from the archival pass.

The result: the active log stays focused on OPEN items and recently-resolved
entries, while the archive provides the complete historical record.

---

## Acting on Observations

This skill identifies WHAT to build or improve. This section covers HOW —
specifically, the cross-context decision framework for choosing between
direct application, skill-creator handoff, and new-skill creation.

**Trigger gate (when):** Observations are acted on only in three contexts:

1. **The comprehensive review** — scheduled mode preferred, in-session
   fallback if no scheduled review has run in 7+ days. See
   "## Comprehensive Review (scheduled or fallback)" for the procedure.
2. **Explicit user requests during a task session** — "update X skill",
   "act on observation #N now", "apply this rule to the skill". The user
   is naming the action; the agent executes within the framework below.
3. **In-session correction when a skill is producing wrong output and
   the user should be aware** — surface immediately rather than wait
   for the next review.

Observations are NOT applied during normal task sessions outside these
contexts. Mid-task work produces observations only; those observations
get applied at the next review or by request. The default is log,
don't act.

**Mechanism framework (which):** When acting in any of those contexts,
the rest of this section guides the choice between applying changes
directly to the skill file, handing off to the skill-creator for
substantial restructuring, or creating a new skill from scratch.

### Small Changes

If the improvement is clearly additive, low-risk, and doesn't require testing
to verify it works, it can be applied directly to the skill:

- Adding a new rule or anti-pattern to an existing list
- Clarifying existing wording that proved ambiguous
- Adding a note or edge case to an existing section
- Fixing a factual error

Examples: Adding a new anti-pattern to a skill's anti-patterns list.
Clarifying that inline code comments should be context-aware within their
own document.

After creating or updating any skill file, always present it using `present_files` so the user can review and install it directly from the conversation.

### Substantial Changes (Use Skill-Creator if Available)

If the change could affect the skill's behaviour in ways that need
verification, hand off to the skill-creator if available:

- Restructuring phases or workflows
- Adding new capabilities or sections
- Changing core methodology or decision frameworks
- Any change where "does this actually work better?" is a genuine question

However, match the rigour of the skill creation process to the complexity and
audience. Skill-creator is valuable for open-source skills that need testing,
for skills with complex logic, or when the design isn't yet clear. For internal
skills where requirements are established in conversation, writing directly is
more efficient.

If skill-creator is not available, use the observations as a specification
and make the changes directly — but flag them to the user as substantial
changes that may need manual review.

Examples: Restructuring a skill to make an automated workflow the primary
path instead of a secondary option. Adding an entirely new setup phase to
a skill that previously started with content work.

### Creating New Skills

Use the skill-creator for new skills when available. Provide the
observation(s) as context — they contain the intent, scope, and initial
design thinking needed to get started efficiently. Without skill-creator,
the observations serve as a detailed brief for building the skill manually.

When creating a new skill, determine its type early:

- If it's open-source, strip out any client-specific details and generalise
- If it's internal, include all relevant specifics freely
- If uncertain, default to open-source — strip out specifics and generalise,
  then let the user decide whether any internal details need to be added


## Task-Oriented Sessions — Observation vs Action

Skill development and iteration work happens in multiple environments: in Cowork with persistent storage, in Claude Code with project directories, and in web-based chat without file system access. Cross-environment coordination is essential to prevent regressions — a skill updated in one environment can silently omit content from another if the wrong base file is used.

### Skill file locations — read-only mount vs workspace copy

When working with skills, understand the distinction between the **live file** (the authoritative source) and **workspace copies** (working drafts or staged updates):

1. **The live file is read-only in Cowork.** In Cowork, the live skill file is mounted read-only at `.claude/skills/{skill}/SKILL.md`. You can read it, but you cannot edit it directly — the file system will reject write attempts with `EROFS` (Read-Only File System). This is intentional: it prevents accidental overwrites of the canonical version.

2. **Read from the live file, not cached memory.** Always start skill edits by reading the current live file — not from a workspace copy, a prior draft, or a memory-based reconstruction. This is the only way to guarantee your updates are based on the current canonical content.

3. **Stage edits in the workspace folder.** Write updated versions to `[workspace folder]/skill-updates/[date]/[skill-name]/SKILL.md`. This separation keeps the read-only mount clean and gives you a clear staging area for review before the user replaces the live file.

4. **After staging, present the file for user review.** Always use `present_files` to show the updated skill so the user can review changes and upload directly. Do not attempt to write directly to the mounted skills directory — that will fail with a permission error.

5. **Before overwriting or replacing any existing staged or workspace copy of a skill, diff it against the live file.** If they differ, the workspace copy is stale and your edits must be rebased on the live version — otherwise you risk silently dropping content added by another session. This rule is also codified in CLAUDE.md under "Skill Editing — Always Start From the Live File" as a cross-environment guard. The concrete failure mode: a Claude Code session produced an updated skill that was based on a stale snapshot and silently omitted two substantial sections added to the live skill earlier the same day. The regression was caught only because a pre-merge diff against the mount revealed the missing content.

### Task-session skill updates — stage in the workspace

When a task session produces a skill update (through weekly review, direct improvement, or observation-driven changes), follow this workflow:

1. Read the live file at `.claude/skills/{skill}/SKILL.md`
2. Make all edits to that content
3. Save the complete updated file to `[workspace folder]/skill-updates/[today]/[skill-name]/SKILL.md`
4. Use `present_files` to show it to the user for review
5. The user uploads the file to install it

**Path pinning:** In Claude Code, `[workspace folder]/skill-updates/[today]/[skill-name]/`
resolves to the absolute `~/.claude/skill-observations/skill-updates/YYYY-MM-DD/[skill-name]/`,
not a path relative to the current project. This is deliberate: a
project-relative path would land inside a git working tree that concurrent
sessions push commits into and merge PRs from, and a staged skill draft has
no business being tracked there. Record the baseline hash of each source
file (e.g. `sha256sum`) alongside the staged copy: a stale baseline (the
live file changed after you read it but before you staged your edit) is
otherwise undetectable at install time.

This keeps the mount clean, stages updates for review, and gives you a clear separation between read-only source and working copy.

**Cross-environment note:** Claude Code now shares the same skills as Cowork via the anthropic-skills capability. The "always start from the live file" rule applies in both environments. In Claude Code, the live file is surfaced by the capabilities system; in Cowork, it's the read-only mount at `.claude/skills/{skill}/SKILL.md`. The diff-before-overwrite requirement applies regardless of which environment produced the update.

---
---

## Principle Propagation

When an observation reveals a general principle — something that applies not
just to the skill being improved but to skills in general — it should be
propagated across the skill library, not just applied to the one skill that
triggered it.

### The Cross-Cutting Principles File

Cross-cutting principles are tracked in a persistent file alongside the
observation log:

```
[workspace folder]/skill-observations/cross-cutting-principles.md
```

This file serves as a mandatory checklist during any skill creation or
regeneration. Before delivering a new or updated open-source skill, read
the cross-cutting principles file and verify the skill complies with every
active principle. This is what turns general principles from good intentions
into enforced standards.

### How It Works

1. During a skill update, an observation reveals a principle that applies
   broadly — not just to the skill being worked on
2. Log it as an observation with `Skill: All skills` and surface it to the
   user
3. If the user approves it as a cross-cutting principle, add it to the
   cross-cutting principles file
4. From that point forward, every skill creation or regeneration includes
   a compliance check against the full list of active principles

### Propagation Timing

The user decides when and how to propagate each principle:

- **Immediate propagation** — for principles important enough to warrant
  updating all existing skills right away (e.g., a confidentiality rule)
- **Opportunistic propagation** — for principles that can be applied the
  next time each skill is updated or regenerated (e.g., adding a licence
  statement)

### Cross-Cutting Principles File Structure

```markdown
# Cross-Cutting Principles

Principles that apply to all skills. This file is read as a mandatory
checklist during any skill creation or regeneration.

---

## Active Principles

### 1. [Principle title]
**Added:** [date]
**Applies to:** [all skills | all open-source skills | all skills with rules]
**Requirement:** [what the principle requires]
**Propagation:** [immediate | opportunistic]
**Status:** [active]
```

---

## Comprehensive Review (scheduled or fallback)

The comprehensive review cross-checks all open observations against all
skills, propagates cross-cutting principles to skills that don't yet
comply, and applies the improvements that don't need user input. There
are two ways it runs.

**Preferred mode — scheduled autonomous review.** A user-defined recurring
task (typical cadence: Monday/Wednesday/Friday mornings) registered with
the agent's scheduling system. This is preferred because it picks up open
observations on a regular cadence without depending on the user being
mid-session at exactly the right moment, and because the user is not
present, the review applies the non-escalated observations autonomously.

**Fallback mode — in-session 7-day trigger.** If no scheduled review is
registered (or none has run successfully in the last 7 days), a
comprehensive review fires automatically at the start of the next
task-oriented session. The fallback is a safety net for users who haven't
set up scheduled reviews — either because the environment doesn't support
scheduling or because they haven't done it yet.

### Trigger Mechanism

**Scheduled mode** runs via the user's chosen scheduling tool — no in-skill
trigger required.

**Fallback mode** is triggered by step 3 of the Session Start Protocol
(see Observation Log Management). The fallback fires when both of the
following are true:

- No scheduled review task is registered, OR the most recent successful
  scheduled review was more than 7 days ago.
- The in-session timestamp at
  `[workspace folder]/skill-observations/last-review-date.txt` is also
  more than 7 days old (or missing).

Independently of that date check, a backlog-size trigger also applies (see
Session Start Protocol step 3): a review that only checks the clock can sit
silently on a backlog of well over a thousand open observations, so an OPEN
count past roughly 150, or a cluster of 5+ observations sharing a skill or
failure keyword, surfaces the review as overdue on its own.

When the fallback fires, inform the user that the comprehensive review is
running and walk through Step 0 (recommend scheduling) before Step 1.

### Interactive vs Scheduled Runs — Approval Policy

The approval behaviour depends on who is present:

**Interactive sessions (user present):** Always ask the user before applying
or declining observations. Present observations grouped by skill with a one-
sentence summary each, and wait for explicit approval (blanket "apply all" or
selective). This preserves the collaborative feel and lets the user catch
observations they disagree with before any staging occurs.

**Scheduled autonomous runs (user not present):** Apply observations
autonomously by default. The safety net is the staging-plus-upload pattern:
updates go to `skill-updates/YYYY-MM-DD/{skill-name}/SKILL.md` and only
become live when the user explicitly uploads them. Nothing can silently
break because nothing is live until the user approves upload.

**Escalate without applying (report only) when any of these apply:**

1. **New skill creation.** Naming, scope, type (open-source vs internal),
   and licence are decisions that benefit from user input. Note the
   candidate in the report; don't create the skill.
2. **Removing or substantially restructuring existing content.** Any edit
   that deletes a section, replaces it with something smaller, or reshapes
   core methodology risks dropping institutional memory. Flag and report.
3. **An observation that flags its own uncertainty.** Phrases like "not
   sure if...", "this might be...", "worth discussing..." in the
   Suggested Improvement field are the observation asking for user input.
   Respect that.
4. **Conflicting observations.** Two observations that point in opposite
   directions, or where the integration path isn't obvious, should be
   surfaced rather than resolved autonomously.
5. **A recurrence of an already-documented rule.** If the target skill's
   text already covers the observation's fix correctly and the observation
   is reporting a recurrence anyway, do not apply a prose edit; reclassify
   it as an ENFORCEMENT-GAP and report it for a mechanical-gate decision
   instead (see Disposition under Step 3).

Scheduled runs that escalate should still apply every non-escalated
observation before producing the report. A scheduled review that
produces 0 applied updates is functionally a report generator, which
wastes the scheduling.

### Review Steps

**Step 0 — Recommend scheduled review setup**

Before running the in-session fallback, check whether scheduled autonomous
reviews are set up. If not, surface a recommendation to the user — but
respect prior declines.

1. Check for the suppression marker at
   `[workspace folder]/skill-observations/scheduled-review-decline.txt`.
   If it exists and was last updated less than 30 days ago, AND the
   in-session fallback has not fired multiple times in that window, skip
   the recommendation. Proceed to Step 1.

2. Check whether a scheduled review task is registered. The signal is
   either a presence check via the platform's scheduling tool (preferred)
   or the existence of
   `[workspace folder]/skill-observations/scheduler-registered.txt`. **Do
   not trust the marker's mere presence as proof the review is running:**
   cross-check its age against `last-review-date.txt`. A marker can persist
   for weeks after the scheduled job silently stops firing (an 11-day
   overdue gap was observed with the marker still present); if the gap
   between the marker's age and the actual review cadence is wide, surface
   "scheduled review appears registered but dormant" instead of staying
   silent. If the cross-check confirms the scheduled review is actually
   running, no recommendation needed; skip to Step 1.

3. If no scheduled review is registered AND no recent decline marker
   exists (or the marker is stale because the fallback keeps firing),
   make an active recommendation:

   > "I notice you don't have a recurring skill review scheduled. The
   > task-observer recommends running this review on a cadence — e.g.,
   > Monday/Wednesday/Friday mornings — so it doesn't depend on you
   > being mid-session at the right moment. Want help setting one up?"

   - **If the user says yes:** walk through registering a scheduled task
     using the platform's scheduling capability. In Cowork, invoke the
     `create-shortcut` skill and its `set_scheduled_task` tool. In
     terminal-based environments, use cron or an equivalent scheduler.
     Use task name `weekly-skill-review` (or similar) and a sensible
     default cadence; let the user pick the day(s) and time. Once
     registered, read the draft task description at
     `[workspace folder]/skill-observations/scheduled-task-draft.md` and
     pass it as the task prompt. On success, write today's date to
     `[workspace folder]/skill-observations/scheduler-registered.txt`.
   - **If the user says no or defers:** write today's date to
     `[workspace folder]/skill-observations/scheduled-review-decline.txt`
     to suppress the recommendation for 30 days. Proceed to Step 1 and
     run the in-session fallback.

4. If no scheduling capability is available in the current environment,
   skip the recommendation silently and proceed to Step 1. Do not surface
   the recommendation in environments where the user couldn't act on it.

5. **Audit runtime-writing scripts for path drift.** Any script under
   `scripts/` that writes a shared task-observer runtime file (`log.md`,
   `available-skills.md`, `cross-cutting-principles.md`, and similar) must
   resolve paths via `${HOME}/.claude/skill-observations`, never a path
   derived from the script's own location: `generate-skills-manifest.sh`
   drifted this way and wrote a stale duplicate tree. Any find-and-replace
   step in an install or patch script should assert a nonzero match count
   and fail loudly otherwise: `apply-task-observer-patches.sh`'s Patch 1
   was silently a no-op for its entire life because it targeted a
   placeholder string that never matched upstream's actual placeholder,
   leaving the real placeholder unsubstituted throughout the installed
   SKILL.md. (Fixing the patch script itself is separate work, outside
   these four skill files.)

The 30-day suppression isn't permanent. If the in-session fallback keeps
firing within the suppression window — a signal that the recurring need
is real and the one-time decline was situational — the recommendation
re-surfaces on the next firing.

**Step 1 — Load observations and principles**

Read the observation log at `[workspace folder]/skill-observations/log.md`.
Extract all observations with status OPEN. Also read
`[workspace folder]/skill-observations/cross-cutting-principles.md` and
extract all active principles.

If there are no OPEN observations and all principles are already propagated,
skip the review, update the timestamp, and proceed with the session. Inform
the user briefly: "Weekly skill review: no open observations or outstanding
principles. All skills are current."

**Step 2 — Inventory all skills**

Use `[workspace folder]/skill-observations/available-skills.md` from the system prompt to identify all skills. In
environments where this tag is not present, use the skills directory or
equivalent listing mechanism to discover available skills.

For each skill, read its SKILL.md file at the location provided. Exclude
built-in platform skills from being updated — only update custom skills
created by the user.

**Known system skills (read-only, cannot be replaced by the user):**
docx, pdf, xlsx, pptx, skill-creator, schedule. This list may grow as the
platform evolves — if a skill update fails because the user cannot overwrite
the file, add it to this list.

**Custom skills** (owned by the user, can be replaced) are everything else
in the skills directory that isn't on the system list above.

**Step 3 — Cross-check observations against every skill**

For each OPEN observation, evaluate whether it is relevant to each skill. Do
NOT rely solely on the observation's own "Skill" field — observations may
contain general principles that apply more broadly than the original context
suggested. Consider both the specific "Suggested improvement" and the general
"Principle" fields. Build a mapping of skill → [relevant observations].

**If the review is interactive (user present):** The presentation format
depends on scale.

- **Under roughly 50 OPEN observations:** Present ALL of them to the user in
  a single message, grouped by skill. For each observation, show the
  number, title, and a one-sentence summary. Flag any observations that are
  ambiguous, risky, or require a judgment call as 'Needs your input'. All
  other observations are treated as straightforward and can be applied
  without individual discussion.
- **Above roughly 50 OPEN observations:** Presenting every entry
  individually is unworkable: one review faced 1,341 OPEN observations
  totalling roughly 410,000 words. Run a synthesis-first pass instead:
  partition the OPEN observations by target skill into word-budgeted
  slices, dispatch one subagent per slice to cluster its observations into
  themes and check each theme against the current skill text for existing
  coverage (see Disposition below), then present the consolidated themes,
  not the raw observations, for approval, grouped by skill.

**Disposition: Already-Covered vs Enforcement Gap.** When a theme's
proposed fix is checked against the current skill text and found already
present, do not simply close it as ALREADY-COVERED. First ask whether the
observation is reporting a *recurrence* of that already-documented rule. If
it is, the recurrence is evidence that prose was not the binding
constraint; reclassify the theme as ENFORCEMENT-GAP and design a
mechanical gate (a hook, a validator, a CI check, a post-write assertion)
rather than applying a text edit that will not change behaviour. Reserve
ALREADY-COVERED for a genuine one-off match with no recurrence pattern.
These are different outcomes and must not be merged (cross-cutting
principle #3, cross-cutting-principles.md).

**If the review is scheduled autonomous (user not present):** Skip the user-facing present step. Apply the approval policy from "Interactive vs Scheduled Runs" above: apply every non-escalated observation and record the escalated ones (new-skill candidates, removal/restructuring, self-flagged uncertainty, conflicting observations, recurrence-driven enforcement gaps) in the review report without applying them. Proceed directly to Step 4.

**Step 4 — Cross-check cross-cutting principles against every skill**

For each active cross-cutting principle, check whether each skill already
complies. Flag any skills that do not yet implement the principle.

**Step 5 — Apply updates**

In interactive runs, wait for user confirmation (blanket "apply all" or selective approval) before creating updates. In scheduled autonomous runs, proceed directly to applying all non-escalated observations. For each skill that has relevant observations or non-compliant principles, create an updated version of its SKILL.md. When editing:

- Integrate the insight into the appropriate section of the skill (don't just
  append a list of observations at the bottom)
- Preserve the skill's existing structure, voice, and author attribution
- Make the improvement feel native to the skill, not bolted on
- If an observation suggests a new phase, step, anti-pattern, or checklist
  item, place it where it logically belongs

**Routing observations that target system skills:** When an observation
targets a system skill (see the known system skills list in Step 2), do NOT
skip it. Instead, route the improvement to a **complementary skill** — a
user-owned skill named `{system-skill}-extras` (e.g., `docx-extras`) that
layers additional guidance on top of the system skill. If the complementary
skill doesn't exist yet, create it. The complementary skill should:
- State which system skill it extends
- Contain only the delta — the additional rules, anti-patterns, or guidance
  not present in the system skill
- Be loaded alongside the system skill (add a note to CLAUDE.md or
  equivalent configuration if needed)

This ensures observations targeting system skills are still actionable,
even though the system skill files themselves cannot be modified.

**Important:** Do not edit skill files in place. Save updated versions to the
workspace folder for user review and manual replacement (see Delivering
Updated Skills below).

**Step 6 — Mark observations as ACTIONED**

After successfully creating an updated skill based on an observation, update
that observation's status in `log.md` from OPEN to ACTIONED. Add a brief note
about which skill(s) were updated, e.g.:

`ACTIONED — Applied to [skill-name] (weekly review [date])`

Note: the standard archival-on-write mechanism (see "Archival on Write" in
the Observation Protocol) will automatically archive these newly-resolved
entries on the next log write. No separate archival step is needed here.

**Step 7 — Update timestamp**

Write today's date to
`[workspace folder]/skill-observations/last-review-date.txt`.

**Step 8 — Present summary and user action items**

Present each updated skill file using `present_files`, then show the user a summary following the format in Delivering Updated Skills above. The user can install updated skills directly from the conversation using the upload button on each presented file.

### Constraints

- Do not modify observation entries beyond their status field
- Do not create new skills — only update existing ones. If an observation
  suggests a new skill, note it in the summary for the user to action
  separately via the skill-creator
- If an observation seems relevant but you're unsure how to integrate it,
  skip it and note the uncertainty in the summary
- Treat observations marked "internal" with the same rigour as "open-source"

---

## Delivering Updated Skills to the User

When the weekly review (or any other process) produces updated skill files,
they are delivered to the user through the conversation using `present_files`.
Cowork's UI includes an upload button on presented skill files that allows
the user to install them directly into their capabilities — no manual file
copying needed.

### Delivery Process

1. Save each updated SKILL.md to the workspace folder for record-keeping:

   ```
   [workspace folder]/skill-updates/[date]/[skill-name]/SKILL.md
   ```

   (See Path pinning under Task-session skill updates for the absolute path
   this resolves to in Claude Code, and for the baseline-hash requirement.)

2. Present each updated skill file using `present_files` so the user can
   review it inline and install it directly via the upload button.

3. Present the user with a summary using this format:

   ```
   ## Weekly Skill Review Complete — [date]

   The following skills have been updated based on [N] open observations
   and [N] cross-cutting principles.

   ### Updated Skills

   **[skill-name]**
   - Changes: [1-sentence summary of what changed]
   - Observations applied: #[N], #[N]

   [repeat for each updated skill]

   ### Observations Actioned
   [list of observation numbers and titles marked ACTIONED]

   ### Skipped (needs manual review)
   [any observations that couldn't be applied, with reasons]
   ```

### Keep-Two Rule

The `skill-updates/` directory uses a rolling retention policy: for any
given skill, keep only the two most recent date directories. When a skill
appears in more than two date directories, delete the oldest copies. This
prevents the workspace from accumulating stale update history while still
keeping a short rollback window.

3. Do not proceed with other work until the user has acknowledged the
   summary. The user does not need to replace the files immediately, but
   they should be aware of what's pending.

---

## Environment Compatibility

The observation methodology works in any environment where the agent can interact
with users during task-oriented work. The persistence mechanism is what varies.

### With Persistent Storage

In environments with file system access (desktop tools with workspace folders,
terminal-based tools with project directories, or similar), the full workflow
applies as described: observations are logged to a persistent file, the cross-
cutting principles file is read during skill regeneration, and the log carries
over between sessions automatically.

### Without Persistent Storage

In environments without file system access (web-based chat, etc.), observations
cannot be persisted between sessions. Use this handoff doc template at session
end to surface all observations in a portable, structured format:

```text
## Decisions Made
[numbered list of decisions]

## Observations Logged
[full observation entries in standard format]

## Cross-Cutting Principles (current)
[any principles that were active or newly added]

## Action Items
[what needs to happen next, with enough context to resume]

## Working Artifacts
[any drafts, analyses, or intermediate work products in full]
```

This is less seamless than the persistent-storage workflow, but the core value
— systematically capturing insights that would otherwise be lost — is
preserved. The observation format and surfacing protocol are identical in both
environments.

---
