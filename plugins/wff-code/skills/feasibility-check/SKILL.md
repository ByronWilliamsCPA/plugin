---
name: feasibility-check
description: Lightweight single-agent feasibility gate between brainstorming and writing-plans. Produces GO/CONDITIONAL GO/DEFER decision in under 5 minutes.
user-invocable: true
---

# Feasibility Check

## Overview

Lightweight feasibility gate to run after brainstorming produces a spec and before
invoking writing-plans. Dispatches one Sonnet agent with the spec as context. Output is
a GO / CONDITIONAL GO / DEFER decision with brief rationale.

**Announce at start:** "I'm using the feasibility-check skill."

**When to use:** After brainstorming produces a spec, before writing-plans.

**When to skip:** Pure documentation or configuration changes, bug fixes with a clear
root cause, or features estimated under 2 hours of work.

**Save output to:** `docs/superpowers/feasibility/<feature-slug>-feasibility.md`

## Agent Prompt

Dispatch one Sonnet agent with the full spec as context and this prompt:

> You are performing a lightweight feasibility check for a new feature.
>
> Feature spec: {spec_content}
>
> Answer these four questions concisely (1-3 sentences each):
>
> 1. **Core assumption**: What is the single most critical assumption this feature
>    depends on? Is it verifiable before implementation starts?
> 2. **Blocking dependencies**: Are there external systems, APIs, or permissions that
>    must exist before this can be built? List them or write "None".
> 3. **Minimum buildable version**: What is the smallest piece of this that delivers
>    user value and can be shipped independently?
> 4. **Verdict**: Choose one: GO (build as scoped), CONDITIONAL GO (build MVP only;
>    list conditions), DEFER (list what must exist first).

## Output Format

Save to `docs/superpowers/feasibility/<feature-slug>-feasibility.md`:

```markdown
---
title: "Feasibility: <Feature Name>"
schema_type: common
status: published
owner: core-maintainer
purpose: "Feasibility assessment for <feature-slug>."
tags:
  - planning
---

# Feasibility: [Feature Name]

**Date:** YYYY-MM-DD
**Verdict:** GO | CONDITIONAL GO | DEFER

## Analysis

**Core assumption:** [answer]

**Blocking dependencies:** [answer or "None"]

**Minimum buildable version:** [answer]

## Verdict rationale

[1-2 sentences explaining the verdict]
```

## Verdict definitions

| Verdict | Meaning | Next step |
| --- | --- | --- |
| GO | Build as scoped | Proceed to writing-plans |
| CONDITIONAL GO | Build MVP only | writing-plans scoped to MVP; conditions documented |
| DEFER | Prerequisite missing | Resolve blocking dependencies; re-run feasibility |

## Sources

- Best-practice review (2026-04-11): `docs/development/best-practice-review/synthesis-report.md`
- Claude Code sub-agents: <https://code.claude.com/docs/en/sub-agents>
