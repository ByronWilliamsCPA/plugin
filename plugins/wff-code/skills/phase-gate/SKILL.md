---
name: phase-gate
description: >
  Evaluate phase readiness by analyzing scope completion and running quality gates.
  Use when transitioning between implementation phases, checking phase status,
  or validating that a phase is ready for completion.
version: 1.0.0
---

# Phase Gate Skill

Evaluate whether an implementation phase is complete and ready for transition to the next phase. Orchestrates scope analysis and quality gate review, then presents results for user approval.

## When to Use This Skill

- User says "is phase X done?", "check phase X", "phase gate", "ready for next phase"
- User invokes `/phase-gate` with a phase number
- Before creating a PR that represents phase completion
- When starting a new phase (to confirm the previous one is complete)

## Arguments

- `phase <N>` — Evaluate phase N (0-6). Required.
- `scope-only` — Run only scope analysis, skip quality gates
- `review-only` — Run only quality gates, skip scope analysis
- `plan` — Validate a proposed action plan against phase scope (for pre-implementation)

## Workflow

### Mode: Full Evaluation (default)

This is the primary workflow. It runs both scope analysis and quality review in parallel, then synthesizes results.

#### Step 1: Parse Phase Number

Extract the phase number from `$ARGUMENTS`. Valid values: 0-6. If missing, check the current git branch name for a phase indicator (e.g., `feat/phase-1-*`). If still unclear, ask the user.

#### Step 2: Dispatch Agents in Parallel

Launch both agents simultaneously using the Agent tool:

1. **scope-analyzer** agent:
   - Task: "Analyze phase {N} scope against docs/IMPLEMENTATION_PLAN.md. Check which deliverables are DONE, PARTIAL, NOT_STARTED, or UNCLEAR. Detect any scope creep on the current branch. Return only a JSON object with this exact shape (no surrounding prose): {\"deliverables\": [{\"id\": \"<name>\", \"status\": \"DONE|PARTIAL|NOT_STARTED|UNCLEAR\", \"detail\": \"<one sentence>\"}], \"scope_creep\": [\"<item>\"], \"verdict\": \"PASS|FAIL\"}. Example: {\"deliverables\": [{\"id\": \"scope-analyzer\", \"status\": \"DONE\", \"detail\": \"agent implemented and tested\"}], \"scope_creep\": [], \"verdict\": \"PASS\"}"
   - This agent reads the implementation plan and scans the source tree
   - Returns: `{"deliverables": [{"id": str, "status": "DONE"|"PARTIAL"|"NOT_STARTED"|"UNCLEAR", "detail": str}], "scope_creep": [str], "verdict": "PASS"|"FAIL"}` (per-item `detail` strings and the `scope_creep` array supply the evidence required by the rule in `.claude/rules/supervisor.md`)

2. **phase-reviewer** agent:
   - Task: "Run quality gates for phase {N}. Execute: ruff check, ruff format --check, basedpyright, pytest with coverage, bandit. Check the per-phase smoke test from docs/IMPLEMENTATION_PLAN.md. Return only a JSON object with this exact shape (no surrounding prose): {\"gates\": [{\"name\": \"<check name>\", \"status\": \"PASS|FAIL|BLOCKED\", \"detail\": \"<one sentence>\"}], \"coverage_pct\": <float>, \"verdict\": \"PASS|FAIL|BLOCKED\", \"blocker\": \"<required when verdict is BLOCKED>\"}. Use BLOCKED when runtime observation is unavailable per `.claude/rules/testing.md`. Example: {\"gates\": [{\"name\": \"ruff check\", \"status\": \"PASS\", \"detail\": \"0 issues\"}], \"coverage_pct\": 87.4, \"verdict\": \"PASS\", \"blocker\": \"\"}"
   - This agent runs the actual checks
   - Returns: `{"gates": [{"name": str, "status": "PASS"|"FAIL"|"BLOCKED", "detail": str}], "coverage_pct": float, "verdict": "PASS"|"FAIL"|"BLOCKED", "blocker": str}` (the `blocker` string is required when `verdict` is `BLOCKED`; empty otherwise)

#### Step 3: Synthesize Results

Combine both agent reports into a single summary for the user:

```markdown
## Phase {N} Gate Review: {Phase Name}

### Scope Status
- **Deliverables**: X/Y complete, Z partial, W not started
- **Scope creep**: {none detected / items listed}

### Quality Gates
- **Lint**: PASS/FAIL
- **Types**: PASS/FAIL
- **Tests**: PASS/FAIL (XX% coverage)
- **Security**: PASS/FAIL
- **Smoke test**: PASS/FAIL/MANUAL

### Verdict: {READY / NOT READY}

{If NOT READY: specific blockers}
{If READY: "Phase {N} is complete. Approve to proceed to Phase {N+1}?"}
```

#### Step 4: Wait for User Approval

**CRITICAL**: Do not begin any work on the next phase until the user explicitly approves.

**If NOT READY:**
- List the specific blockers from the phase-reviewer and scope-analyzer reports
- Offer to help address them: "Would you like help fixing these blockers?"
- Stop. Do not advance.

**If READY and user approves:**

1. **Invoke `finishing-a-development-branch` skill**
   - This presents the user with merge/PR/keep/discard options
   - Wait for the skill to complete fully (user has made and executed their choice)

2. **Offer phase N+1 transition** (only after finishing completes):
   ```text
   Phase {N} complete. Ready to start Phase {N+1}?

   This will run: /phase-gate phase {N+1} plan
   (validates the Phase {N+1} implementation plan and sets up a new worktree)

   Start Phase {N+1}? (yes / no)
   ```
   - If yes: invoke `/phase-gate phase {N+1} plan`
   - If no: stop — the user will start Phase {N+1} manually when ready
   - **Never auto-advance** — the offer must be dismissed explicitly

### Mode: Scope Only (`scope-only`)

Run only the scope-analyzer agent. Useful for checking progress mid-phase without running the full quality gate suite.

### Mode: Review Only (`review-only`)

Run only the phase-reviewer agent. Useful when scope is already confirmed and you just need to verify quality gates pass.

### Mode: Plan Validation (`plan`)

For pre-implementation validation and workspace setup. Validates the phase plan against scope, sets up an isolated worktree, then hands off to the execution skill.

1. **Locate the phase implementation plan:**
   - Check `docs/superpowers/plans/` for a plan file matching phase N (e.g. `*phase-{N}*` or `*phase{N}*`)
   - If not found, ask the user: "What is the path to the Phase {N} implementation plan?"

2. **Check for PROJECT-PLAN.md** (optional — large project path only):
   - If `docs/planning/PROJECT-PLAN.md` exists: read the Phase {N} acceptance criteria and branch name from it
   - If it does not exist: ask user for the phase description and use branch name `feat/phase-{N}-work`

3. **Launch plan-validator agent:**
   - Task: "Validate the implementation plan at {plan_path} against Phase {N} acceptance criteria. Check traceability — every plan task should map to a deliverable. Flag scope creep candidates and coverage gaps."
   - Present the traceability matrix to the user
   - Flag any scope creep or gaps

4. **Get user approval of the plan** before proceeding. If the user requests changes, update the plan and re-validate.

5. **Set up isolated worktree** (invoke `using-git-worktrees` skill):
   - Branch name: use the branch name from PROJECT-PLAN.md if available, otherwise `feat/phase-{N}-{slug}` where slug is derived from the phase name
   - After worktree is ready, confirm: "Worktree ready at {path}. Tests passing."

6. **Ask execution preference:**
   ```text
   Workspace ready. How would you like to execute Phase {N}?

   1. Subagent-Driven (recommended) — fresh subagent per task, two-stage review
   2. Inline Execution — execute tasks in this session with checkpoints

   Which approach?
   ```

7. **Invoke chosen skill** with the phase implementation plan path:
   - Option 1: invoke `subagent-driven-development` with the plan
   - Option 2: invoke `executing-plans` with the plan

## Examples

```bash
# Full phase gate evaluation
/phase-gate phase 0

# Check scope progress mid-phase
/phase-gate phase 1 scope-only

# Verify quality gates before PR
/phase-gate phase 0 review-only

# Validate implementation plan before coding
/phase-gate phase 1 plan
```

## Integration

This skill works with:

- **scope-analyzer** agent (`/.claude/agents/scope-analyzer.md`)
- **phase-reviewer** agent (`/.claude/agents/phase-reviewer.md`)
- **plan-validator** agent (`/.claude/agents/plan-validator.md`)
- Phase-gate behavioral rules in `CLAUDE.md`
- Implementation plan at `docs/IMPLEMENTATION_PLAN.md`
