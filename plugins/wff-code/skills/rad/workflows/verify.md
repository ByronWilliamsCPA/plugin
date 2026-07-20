---
argument-hint: [--strategy=tiered] [--budget=balanced] [--scope=changed-files] [--explain] [--apply-fixes=review]
description: Intelligent tiered verification of code assumptions using multiple AI models based on risk levels.
allowed-tools: Bash(git:*), Read, Grep, Skill
---

# Assumption Verification Workflow

Systematically verify code assumptions using multi-model AI analysis with intelligent routing based on risk levels.

## Task Overview

Analyze code for assumption tags and route them to appropriate AI models.
Model names come from the current roster in
`.claude/skills/panel/data/models.csv`; the tiers below name capability
bands, not fixed models:

- **#CRITICAL:** → premium models from the roster
- **#ASSUME:** → panel selection of cost-effective models from the roster
- **#EDGE:** → fast batch processing with a fast roster model

## Arguments

- `--strategy`: `tiered` (default), `uniform`, `critical-only`
  - **tiered**: Use appropriate model for each risk level
  - **uniform**: Same model for all assumptions
  - **critical-only**: Only process #CRITICAL tags

- `--budget`: `premium`, `balanced` (default), `free-only`
  - **premium**: Allow paid models for all tiers
  - **balanced**: Paid for critical, free for others
  - **free-only**: Only use free models

- `--scope`: `current-file`, `changed-files` (default), `all-files`
  - **current-file**: Focus on file in current context
  - **changed-files**: Git diff to find modified files
  - **all-files**: Scan entire project

- `--explain`: Show model selection reasoning (flag)

- `--apply-fixes`: `auto`, `review` (default), `none`
  - **review**: Stage fixes for manual review with `git add -p`
  - **auto**: Apply non-critical fixes automatically with backup
  - **none**: Only report, no fixes applied

## Implementation Steps

### 1. Collect Assumptions by Scope

Based on scope parameter:

```bash
# Changed files (default)
git diff --name-only HEAD
git diff --name-only --cached

# All files
find . -type f \( -name "*.py" -o -name "*.js" -o -name "*.ts" \) \
  ! -path "*/node_modules/*" ! -path "*/.git/*"
```

Search for assumption patterns:
- `#CRITICAL:` - Production blockers, security, payments
- `#ASSUME:` - Standard assumptions, state management, APIs
- `#EDGE:` - Edge cases, browser compatibility, performance

### 2. Categorize and Route Assumptions

**Critical Assumptions (Premium Models)**:

Route each category to a premium reasoning model from the current roster in
`.claude/skills/panel/data/models.csv`:

- Payment/Financial → premium reasoning model
- Security/Auth → premium reasoning model
- Concurrency/Race → strong free reasoning model, or premium if budget allows
- Database/Transactions → strong free reasoning model

**Standard Assumptions (Panel Review)**:

Use `Skill("panel")` in tiered-review mode at level 1 (three free models,
$0.50 cap), batching the assumptions of one category into a single prompt:

```text
Skill("panel")(
  mode:   "tiered-review",
  level:  1,
  domain: "code_review",
  prompt: "Analyze these code assumptions for [category]. For each, state
           whether it holds, and name the defensive programming pattern or
           error handling the code should add if it does not.

           {assumptions with file, line, and surrounding code}"
)
```

**Edge Cases (Fast Models)**:

Batch process via `Skill("panel")` in flexible panel mode with a one-model
roster, picking a fast, cheap model from
`.claude/skills/panel/data/models.csv`.

Precondition for all three tiers: `OPENROUTER_API_KEY` must be set. If it is
not, degrade to single-model verification with the
`doubt-driven-development` skill and tag the output `VERIFIED-SINGLE-MODEL`
so downstream readers know decorrelation was not achieved.

### 3. Execute Verification Strategy

**Tiered Strategy**:
1. Process critical assumptions individually with premium models
2. Batch standard assumptions by category with free models
3. Bulk process edge cases with fast models

**Critical-Only Strategy**:
1. Only process #CRITICAL: tagged assumptions
2. Use premium models exclusively
3. Skip standard and edge cases

**Uniform Strategy**:
1. Use same model for all assumptions
2. Model selection based on budget parameter

### 4. Generate Verification Report

Create comprehensive report with:

- **Summary**: Count of assumptions by category and processing time
- **Critical Issues**: Must fix before deploy (❌ BLOCKING status)
- **Standard Issues**: Should fix before PR (⚠️ REVIEW status)
- **Edge Cases**: Can defer to backlog (💡 NOTE status)
- **Model Usage**: Explanation of model selection (if --explain used)
- **Cost Summary**: Estimated costs and free vs paid model usage
- **Next Steps**: Actionable checklist for fixes

### 5. Apply Fixes (If Requested)

Based on `--apply-fixes` parameter:

- **review**: Stage fixes for manual review with `git add -p`
- **auto**: Apply non-critical fixes automatically with backup
- **none**: Only report, no fixes applied

## Verification Prompts

### For Critical Assumptions

```markdown
You are a senior security engineer reviewing production-critical code. You have NO knowledge of the original developer's intent.

## Code Context
File: [filename]:[line]
Assumption: [assumption text]
Category: [payment/security/concurrency]

## Task
1. Assume worst-case production conditions: high load, slow networks, unreliable services
2. Identify race conditions, timing dependencies, security vulnerabilities
3. Generate defensive code with proper error handling
4. Provide specific, actionable fixes

Focus on production failures, not theoretical issues.
```

### For Standard Assumptions

```markdown
You are a code reviewer focused on preventing bugs. Analyze this assumption under production stress conditions.

## Code Analysis
[code context]

Identify: state management issues, async timing problems, error handling gaps, validation missing

Generate: defensive programming patterns, proper error handling, validation logic
```

## Success Criteria

- All assumptions found and categorized
- Appropriate model used for each risk level
- Concrete fixes for critical issues
- Cost-effective use of premium models (≤10% of total calls)
- Clear next steps for developer

## Error Handling

If no assumptions found:

```markdown
# Assumption Verification Report

## Summary
No assumption tags found in scope. Start using RAD methodology:

```javascript
// #CRITICAL: payment: Transaction assumed synchronous
// #VERIFY: Add timeout and retry logic
```text

See RAD methodology context for complete guidance.
```
