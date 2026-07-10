---
name: domain-modeling
description: Maintains a living domain glossary and challenges terminology drift. Use when domain modeling, defining domain terms, maintaining a glossary, enforcing ubiquitous language, or when code or conversation introduces a term that conflicts with or duplicates an existing one. Triggers on domain modeling, glossary, ubiquitous language, terminology drift, domain term, what do we call this.
user-invocable: true
---

# Domain Modeling

> **Ported skill.** Adapted from the `domain-modeling` concept in
> [`mattpocock/skills`](https://github.com/mattpocock/skills) (MIT License),
> retrieved 2026-06-18 via our skills survey
> (`docs/tool-evals/skills-deep-dive-2026-06.md`). Authored fresh to our
> conventions, not a verbatim port: TypeScript-specific scaffolding was stripped
> (our config is Python-centric and language-agnostic here), em-dashes removed,
> and the glossary repointed to our folder-scoped CLAUDE.md model (see the
> "Scoped context" section of the root `CLAUDE.md`).

## Overview

A domain has one vocabulary. When the code, the docs, and the conversation all
use the same word for the same concept, that word is **ubiquitous language**:
the model and the implementation stay in sync, and a reader of either can trust
the other. Terminology drift breaks that link. The moment one part of the system
calls a thing a `Customer`, another calls it a `Client`, and a third calls it an
`Account`, every reader pays a translation tax and every change risks editing the
wrong concept.

Drift is expensive because it compounds silently. A synonym coined today becomes
a column name tomorrow, an API field next week, and a migration you cannot
reverse next quarter. The cheap moment to catch it is the moment the second name
appears.

## When to Use

- Before writing code or docs in a domain that already has a glossary: load it.
- When naming a new entity, field, status, event, or operation.
- When a term in the conversation or a diff does not match a glossary entry.
- When onboarding to unfamiliar domain code and the vocabulary is unclear.
- When the same concept appears under two or more names across the codebase.

**When NOT to use:**

- Pure mechanical work (formatting, file moves) that introduces no new terms.
- Domains with no shared vocabulary at stake (throwaway scripts, spikes).

## The Glossary Artifact

The glossary is a folder-scoped context artifact, the same model as our
folder-level `CLAUDE.md` (root `CLAUDE.md`, "Scoped context": last scope wins).
Place it next to the code it governs so it loads with that scope:

- A domain `CONTEXT.md` (or `glossary.md`) in the relevant package directory,
  for example `src/billing/CONTEXT.md`.
- One glossary per bounded domain, not one global file. Billing terms live with
  billing code; a term that means different things in two domains gets two
  entries, one per folder.

A good entry pins the term down hard enough that a synonym cannot sneak in. It
carries the term, a precise definition, the distinctions that separate it from
near-neighbors (the NOT-this lines), and one concrete example:

```markdown
### Subscriber

A party with at least one active paid plan. Identified by `subscriber_id`.

- Definition: an account that currently owes recurring payment for a plan.
- NOT a `User`: a User is an authenticated login. A Subscriber may map to
  many Users (a team), and a User may be no Subscriber at all (free tier).
- NOT a `Customer`: we do not use "Customer" in billing. If you see it,
  it is drift; reconcile to Subscriber or User.
- Example: account `acct_8812` on the Pro plan is a Subscriber; its three
  invited logins are Users, none of them Subscribers.
```

The NOT-this lines do the real work. A definition alone tells a reader what the
term includes; the distinctions tell them which neighboring term they were about
to reach for by mistake.

## The Terminology-Drift Challenge

Drift is a new term that collides with an existing glossary entry: a synonym for
a defined concept, or a defined word reused for a different concept. When you are
about to introduce or you encounter a domain term, run this check:

```text
Drift check:
- [ ] Is this concept already in the glossary under a different name? (synonym)
- [ ] Is this word already in the glossary meaning something else? (homonym)
- [ ] Does the code already use a different name for this exact concept?
- [ ] If new: does it overlap any existing entry's definition or NOT-this lines?
```

If any box is checked, you have drift. **Stop. Surface the conflict. Do not
silently coin a synonym or quietly rename.** Naming is the human's call when an
existing term is at stake; guessing entrenches the drift you were meant to catch.

```text
TERMINOLOGY DRIFT:
The code I am about to write calls this a `Client`, but the billing glossary
(src/billing/CONTEXT.md) defines `Subscriber` for "a party with an active paid
plan", which is the same concept.

Options:
A) Use the glossary term `Subscriber` (keeps ubiquitous language intact)
B) `Client` is genuinely a distinct concept; add a new glossary entry with
   NOT-this lines separating it from Subscriber
C) `Subscriber` is the wrong name and should be renamed glossary-wide

Which one? If B, I need the distinguishing definition before I write the code.
```

When the resolution is a genuinely new concept, add the entry (with its NOT-this
lines) before writing the code that depends on it. Keeping the glossary and the
code in sync is the point; a stale glossary is worse than none, because readers
trust it.

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "It is obvious these mean the same thing" | Obvious to you today, not to the reader in six months or the next synonym. Write the entry. |
| "A synonym is harmless, it reads fine" | It reads fine and ships a second name into a column, an API field, a migration. The cost lands later and cannot be reversed cheaply. |
| "I will update the glossary after I ship" | After shipping, the drift is already in the schema. Reconcile before the term hardens, not after. |
| "Renaming to match the glossary is churn" | Two names for one concept is the churn; every reader translates every time. The rename pays for itself on the first maintenance pass. |
| "The glossary slows me down" | Loading it is one read. Debugging a feature that edited the wrong concept is not. |
| "This domain is too small for a glossary" | Then there is nothing to drift from and the check is instant. Size is not the trigger; a shared concept is. |

## Red Flags

- Two or more names for one concept appearing in the same diff or module.
- The same concept named three different ways across the codebase.
- A glossary that has not changed while the domain code has (stale vs code).
- Coining a new term without checking whether the concept already has a name.
- A NOT-this line in the glossary that the code now contradicts.
- A PR that renames a domain term in code but not in the glossary, or vice versa.
- Reaching for "Customer", "Client", "Account", "Entity" as filler when a precise
  domain term already exists.

## Pre-Flight

Before declaring domain work complete, confirm:

- [ ] The relevant domain glossary was loaded before code or docs were written.
- [ ] Every new domain term was checked against the glossary for synonym and
      homonym drift.
- [ ] Each genuinely new concept got a glossary entry (term, definition,
      NOT-this lines, example) before the code depending on it.
- [ ] Any detected drift was surfaced to the user, not silently renamed.
- [ ] The glossary and the code use the same names for the same concepts.
