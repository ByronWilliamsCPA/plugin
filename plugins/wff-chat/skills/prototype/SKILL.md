---
name: prototype
description: Builds a deliberately throwaway prototype to answer exactly one question, then discards it. Use when you need to resolve a single uncertainty (is this approach viable, will this library do X, how slow is this path) before committing to a real implementation. Triggers on prototype, throwaway prototype, spike, proof of concept, answer one question, quick experiment.
user-invocable: true
---

# Prototype

> **Adapted concept.** Built from the [`mattpocock`](https://github.com/mattpocock)
> `prototype` concept (MIT License), retrieved 2026-06-18 via
> `docs/tool-evals/skills-deep-dive-2026-06.md`. Authored fresh against our
> standards: em-dashes removed; mapped to our `spike/` branch convention
> (`.claude/rules/git-workflow.md`), where time-boxed exploratory branches carry
> reduced gates and are never merged to main. This skill is the discipline layer
> on top of that branch type: it forces the single-question framing the branch
> convention assumes.

## Overview

A prototype is not a first draft of the real thing. It is an experiment that
answers one question and then dies. The value is the answer, not the code.

The moment a prototype has more than one question to answer, it stops being a
prototype and becomes an unplanned implementation with no tests, no error
handling, and no review. That is the failure this skill exists to prevent.

The discipline is simple to state and hard to hold: name one question, timebox
it, cut every corner to answer it, write down the answer, then throw the code
away.

## When to Use

- You face a single, nameable uncertainty that blocks a real decision (viability,
  feasibility, performance characteristic, API behavior, integration shape).
- The answer is cheaper to get by building a stripped-down version than by reading
  docs or reasoning about it.
- You are willing to discard the result regardless of how it turns out.

## When NOT to Use

- **You already know the answer.** If you can predict the result, you are not
  prototyping, you are procrastinating on the real work. Skip to implementation.
- **The work is production-bound.** If the output is meant to ship, it is not a
  prototype. Use `test-driven-development` on a `feat/` branch from the start.
  Calling production work a "prototype" to skip tests and review is the anti-pattern.
- **You cannot state one question.** No single question means no prototype. See
  the Pre-Flight step; if the question will not compress to one sentence, you are
  building, not prototyping.
- **More than one question.** Two questions means two prototypes, run in sequence,
  each discarded before the next. Do not bundle them.

## The Five-Step Protocol

```text
Prototype cycle:
- [ ] Step 1 QUESTION: wrote the single question in one sentence
- [ ] Step 2 TIMEBOX: set a hard time limit before writing code
- [ ] Step 3 BUILD: built the minimum to answer it, cut every corner
- [ ] Step 4 RECORD: wrote the answer down where it survives the code
- [ ] Step 5 DISCARD: deleted the prototype, decided the rewrite path
```

### Step 1: QUESTION, name the one thing

Write the question in a single sentence. If you need two sentences or an "and,"
you have two questions. Pick one.

```text
QUESTION: "Can the streaming parser handle a 2 GB file without
           loading it all into memory?"
```

A question this compact is falsifiable: the prototype either answers yes or no.
A vague aim ("explore the parser") has no end condition and will not die on time.

### Step 2: TIMEBOX, set the limit first

Set the limit before writing code, not after you are already deep. A timebox set
mid-build always expands to fit the work already done. Typical prototypes run 30
minutes to a few hours. If the honest estimate is "a day or more," the question
is too big; decompose it or accept this is real work, not a prototype.

### Step 3: BUILD, cut every corner

The only goal is the answer. Everything else is waste.

- No tests. The prototype is the test.
- No error handling. Let it crash; a crash is often the answer.
- Hardcode freely: paths, credentials placeholders, sample data, magic numbers.
- No abstractions, no reuse, no naming care. One file is fine.
- Do not wire it into the real codebase. Keep it isolated so discarding is clean.

If you find yourself adding a config option or a second code path "while I'm here,"
stop. That is scope leaking past the one question.

### Step 4: RECORD, capture the answer

The answer must outlive the code. Write it where you will find it after the
prototype is gone: a note in the relevant doc, an ADR if it settled an
architecture decision, a comment in the issue, or a line in the eventual `feat/`
branch's plan.

```text
ANSWER: Yes. Streaming parser held steady at ~40 MB RSS on the 2 GB file.
        Throughput ~180 MB/s. Viable. Proceed with the streaming design.
```

Record the answer even when it is "no." A disproven approach is a successful
prototype: it saved you from building the wrong thing.

### Step 5: DISCARD, throw the code away

Delete the prototype. This is the step that gets skipped, and skipping it is how
prototypes become production by accident.

The findings carry forward; the code does not. Rewrite the real implementation on
a `feat/` (or `fix/`) branch with tests, error handling, and review, informed by
what you learned. Cherry-picking prototype code into the real branch defeats the
purpose: you inherit all the cut corners and none of the discipline.

## Mapping to a `spike/` Branch

Our `spike/` branch convention (`.claude/rules/git-workflow.md`) is the natural
home for a prototype. The two line up directly:

| Prototype discipline | `spike/` branch rule |
| --- | --- |
| Cut every corner; no tests, no error handling | Waived gates: coverage thresholds, OpenSSF baseline files, docstring coverage |
| Keep the safety floor | Retained gates: linting, type check, secrets detection, pre-commit hooks |
| Timeboxed, dies on schedule | Two-week maximum lifespan, then graduate or delete |
| Never promote prototype code to production | Do not merge spike branches to main |
| Findings carry forward, code does not | Cherry-pick or rewrite findings into a proper `feat/` branch |

Create the branch with the spike prefix so the reduced gate set applies and the
lifespan clock is explicit:

```bash
git checkout -b spike/streaming-parser-memory
```

When the question is answered, do not open a PR from the spike branch. Record the
answer (Step 4), delete the branch (Step 5), and start the real work on a fresh
`feat/` branch.

## Common Rationalizations

| Rationalization | Reality |
| --- | --- |
| "The prototype works, let's just ship it" | It has no tests, no error handling, and hardcoded values. Rewrite on a `feat/` branch with tests. Shipping the prototype is the exact failure this skill prevents. |
| "It would be wasteful to throw away working code" | The code was never the deliverable; the answer was. The "waste" is the price of the cut corners, paid now instead of in production debugging. |
| "I'll just add tests to the prototype later" | "Later" inside a prototype's structure means retrofitting tests onto code built to be untestable. A clean rewrite is faster and you already know the design. |
| "I don't have time to write the question down" | If you cannot spend one sentence naming the question, you do not yet know what you are building. That sentence is the cheapest part of the whole exercise. |
| "While I'm in here, let me also check Y" | Y is a second question and a second prototype. Answer one, discard, then start the next. Bundling them produces a half-built feature, not an answer. |
| "It's basically production-ready already" | If it were production-ready it would have tests and review, so it is not a prototype and never was. Name that honestly and restart on a `feat/` branch. |

## Red Flags

- No single question named before the code started. You are building, not prototyping.
- The one question quietly became three as you worked.
- The prototype outlived its timebox and nobody reset the clock or stopped.
- Prototype code was cherry-picked or merged toward main instead of rewritten.
- Tests or error handling are being added to "harden" the prototype rather than
  rewriting it clean.
- The answer was never written down, so the prototype has to be kept "for reference."
- "Prototype" is being used as a label to skip tests and review on production-bound work.

## Pre-Flight

Before writing any prototype code, confirm both out loud:

- [ ] **The one question is named.** It fits in a single sentence and is
      falsifiable (the prototype can answer yes or no). If it will not compress to
      one sentence, stop: this is implementation work, not a prototype.
- [ ] **The discard decision is explicit.** State now that the code will be thrown
      away and the real work will happen on a separate `feat/` branch. If you are
      not willing to commit to discarding it, you are building production code and
      should use `test-driven-development` from the start.

## Interaction with Other Skills

- **`test-driven-development`**: the opposite mode and the correct destination.
  Prototyping answers a question with throwaway code; TDD builds the real thing
  with tests first. The rewrite in Step 5 uses TDD.
- **`using-git-worktrees`**: a spike worktree keeps the prototype filesystem-isolated
  from your main workspace, making the discard in Step 5 a clean directory removal.
- **`feasibility-check`**: a lighter-weight gate that answers "is this viable" by
  analysis rather than by building. Reach for it first; prototype only when the
  question genuinely needs running code to answer.
- **`finishing-a-development-branch`**: use it to delete the spike branch cleanly
  once the answer is recorded.
