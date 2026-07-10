---
name: premise-interrogation
description: Pre-spec gate that interrogates demand and scope before any spec or plan is written. Use when a user proposes building something and you are tempted to start specifying; this skill holds the pen back and challenges whether the thing should be built at all, who the user is, what the real problem is, and what the cheapest test of the premise would be. Triggers on premise interrogation, challenge the premise, office hours, grill me, interview me, should we build this, is this the real problem, validate the idea, idea refine.
user-invocable: true
---

# Premise Interrogation

> **Adapted from upstream concepts, authored fresh.** This skill merges the
> `office-hours` (YC-style premise challenge) concept from
> [`garrytan/gstack`](https://github.com/garrytan/gstack) (MIT), the
> `grilling` / `grill-me` concept from
> [`mattpocock/skills`](https://github.com/mattpocock/skills) (MIT), and the
> `interview-me` / `idea-refine` concept from
> [`addyosmani/agent-skills`](https://github.com/addyosmani/agent-skills) (MIT),
> all retrieved 2026-06-18 via our skills survey
> (`docs/tool-evals/skills-repos-survey-2026-06.md` and
> `docs/tool-evals/skills-deep-dive-2026-06.md`). This is not a verbatim port: it is written to
> our conventions (no em-dashes; Pattern B tool-invoked; cross-referenced to our
> own brainstorming, feasibility-check, and writing-plans skills). The gstack
> `{{PREAMBLE}}` macro is stripped.

## Overview

Most wasted engineering starts with a premise nobody challenged. The request
arrives ("we need a dashboard", "build an export feature"), and the instinct is
to start specifying the thing as asked. Premise interrogation inserts a gate
before that: it challenges demand and scope while no code, spec, or plan exists
yet, when changing direction costs one conversation instead of one sprint.

The distinction from `brainstorming` is deliberate. Brainstorming moves toward a
spec; it assumes the thing is worth building and helps shape it. Premise
interrogation holds the pen back: it asks whether the thing should be built at
all, who the user actually is, whether the stated problem is the real problem or
a symptom, and what the cheapest test of the premise would be. It is the step
**before** brainstorming.

## When to Use

- A user proposes building a feature, product, or system and you are about to
  start specifying it
- The demand behind a request is unstated or assumed ("the team wants this")
- The request names a solution rather than a problem ("add a Kanban board")
- The cost of building the wrong thing is more than a day of work
- Someone says "just build X" and X has never been tested cheaply

## When NOT to Use

- The premise is already validated: a prior interrogation passed, real users are
  asking, or the demand is measured. Skip straight to `brainstorming`.
- The work is mechanical or obvious (a bug fix, a rename, a clear one-line change)
- The user has explicitly de-scoped premise discussion ("I know it's risky, build
  the prototype anyway")
- You are mid-implementation; this is a pre-spec gate, not a stop-work order. Use
  `doubt-driven-development` for in-flight decisions instead.

## The Interrogation Protocol

Work through all four axes. Do not stop at the first satisfying answer; the
premise survives only when every axis has a defensible answer, not just one.
Surface the questions to the user; do not answer them on the user's behalf.

### Axis 1: Demand (who actually asked)

```text
- Who specifically asked for this? Name them, not a role.
- How many distinct people or accounts have asked, unprompted?
- What do they do today to solve this without the feature? Walk the
  current workaround step by step.
- How painful is that workaround on a 1-to-10 scale, and who said so?
- Is the demand pull (users asking) or push (we think they'll want it)?
```

If the only answer is "we think users will want it", that is push demand. Push
demand is not disqualifying, but it must be named, because push demand is what
the cheapest-test axis exists to de-risk.

### Axis 2: Problem (symptom or root)

```text
- What is the underlying problem, stated without naming any solution?
- Is the requested thing the problem, or a symptom of a deeper one?
  ("We need a status dashboard" may be a symptom of "nobody trusts the
  current status email.")
- If this exact feature shipped and worked perfectly, what would still
  be broken?
- Has anyone solved this problem a different way already, inside or
  outside the org?
```

The "what would still be broken" question is the highest-yield one. A premise
that leaves the real pain intact after a perfect build is the wrong premise.

### Axis 3: Scope (smallest test of the premise)

```text
- What is the smallest version that tests the premise, not the smallest
  version that ships? These differ.
- Can the premise be tested with no code at all? (a manual run, a
  spreadsheet, a Wizard-of-Oz mock, a landing page, a concierge process)
- What is the single riskiest assumption, and does the smallest version
  exercise it?
- What would a "no, this premise is wrong" result actually look like, in
  observable terms?
```

A smallest version that cannot return a "no" is not a test; it is a foregone
conclusion dressed as one. Insist on a falsifiable result.

### Axis 4: Cost of being wrong

```text
- If we build this and the premise was wrong, what did we spend?
  (engineer-weeks, opportunity cost, maintenance tail)
- Is the decision reversible? How expensive is the unwind?
- What is the cost of the cheap test from Axis 3, by comparison?
- Given that ratio, is building-first or testing-first the cheaper path
  to certainty?
```

The cheap test almost always wins on this ratio. When it does not, name why
explicitly; that is itself a finding worth recording.

## Handoff

If the premise survives all four axes, hand off down the pre-build chain:

1. `brainstorming` (vendored): shape the validated premise into a spec.
2. `feasibility-check`: a sub-5-minute GO / CONDITIONAL GO / DEFER gate between
   brainstorming and planning.
3. `writing-plans`: turn the spec into a step-by-step implementation plan.

If the premise does not survive, the output is not a plan; it is a recommendation
(do not build, build something smaller, or run the cheap test first) plus the
specific axis that failed. Hand the user that finding and stop. A failed premise
interrogation that prevents a sprint of wasted work is a success, not a dead end.

## Anti-Rationalization

| Excuse for skipping | Reality |
|---|---|
| "The user already decided, my job is to build it" | The user decided on a solution under their own assumptions. Surfacing a wrong premise is service, not obstruction. They can still say "build it anyway." |
| "Interrogating the premise is slow" | One conversation now versus one sprint later. The gate is minutes; the wrong build is weeks. |
| "Asking 'should we build this' is not my place" | It is precisely the place of a pre-spec gate. You are not vetoing; you are making the demand and cost legible before anyone commits. |
| "It's obviously a good idea" | Obvious-good-idea is exactly the state where nobody checks demand. Run Axis 1; "obvious" rarely survives "who specifically asked." |
| "We can always change direction later" | Later is after the spec, the plan, and half the code. Direction is cheapest to change before the pen touches paper. |
| "There's no cheap test for this" | There almost always is (mock, manual run, landing page, concierge). "No cheap test exists" is usually "I stopped at the first idea." |
| "Brainstorming covers this" | Brainstorming assumes the thing is worth building and shapes it. This gate runs before that assumption is granted. |

## Red Flags

- You are writing acceptance criteria and no axis has been answered yet
- The request names a solution and you never restated the underlying problem
- Axis 1 answers are all roles ("the users", "the team"), never named people
- The "smallest version" you proposed is the smallest shippable build, not the
  smallest premise test
- No falsifiable "the premise is wrong" outcome was defined
- The premise was rubber-stamped: every axis got a one-line affirmative and the
  interrogation moved straight to brainstorming

## Pre-Flight Verification

Before declaring the premise validated and handing off, re-read this skill's
protocol and `.claude/rules/writing.md`, then confirm:

- [ ] All four axes (demand, problem, scope, cost-of-wrong) were asked, surfaced
      to the user, and answered, not assumed on the user's behalf
- [ ] Axis 1 names specific people or accounts, not roles
- [ ] The underlying problem was stated without naming a solution
- [ ] A smallest-version-that-tests-the-premise was defined, distinct from the
      smallest shippable build, and it can return a "no"
- [ ] The cost-of-being-wrong was compared against the cost of the cheap test
- [ ] The premise was genuinely challenged, not rubber-stamped: at least one axis
      produced a real objection, a revision, or an explicit defensible answer
- [ ] On survival, the handoff names `brainstorming` -> `feasibility-check` ->
      `writing-plans`; on failure, the output is a recommendation plus the failed
      axis, and work stops
