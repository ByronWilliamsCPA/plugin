# Task Observer -- Taxonomy, Licensing, and Attribution Reference

Reference content for `task-observer` covering the pre-flight design principle, the open-source/internal skill taxonomy, licensing options, the author attribution template, and the observation-classification signals (what counts as a new-skill candidate, an improvement, a simplification, or a non-observation). Read this file when creating or classifying a skill, or when evaluating what to log.

---

## The Pre-Flight Principle

One of the most important patterns this skill should propagate to every skill
it helps create or improve: **built-in enforcement.**

Real-world experience has shown that rules documented in a skill are not
always followed during the creative flow of producing output. The result:
output that violates the skill's own standards, which reflects badly on the
skill.

The fix: every skill that contains explicit rules or requirements should
include a verification step where the agent re-reads the rules and checks its
output against them before delivery. This isn't overhead — it's quality
assurance. A 30-second re-read prevents a 30-minute rework cycle.

When creating or improving any skill through this observation process, ask:
"Does this skill have rules? If yes, does it have a mechanism to enforce
them?" If the answer to the second question is no, add one.

## Skill Taxonomy

All skills fall into one of two categories. The distinction matters because
it determines what information the skill can contain, how it's structured,
and whether it can be shared publicly. Crucially, the open-source/internal
boundary is also a **confidentiality boundary** — open-source skills must
never contain any information that could identify a client, project, or
proprietary process, even indirectly.

### Open-Source Skills

Open-source skills are client-agnostic and methodology-driven. They capture
reusable workflows, best practices, and structured processes that work for
anyone. They include author attribution, a licence, and a feedback pathway
so that real-world usage drives improvement.

**How to recognise an open-source candidate:**

- The methodology works across different clients, projects, and contexts
- No proprietary information is required for the skill to function
- Other practitioners in the same domain would find it valuable
- The skill captures a process or approach, not personal preferences

**Required elements:**

- Skill body clearly identifies itself as open-source, with author name and
  contact information
- Author attribution block at the top (see Author Attribution Template below)
- Licence statement — CC BY 4.0 recommended (see Licensing below)
- Feedback & support section that routes methodology feedback to the creator
- Tool-agnostic language where possible — reference capabilities like "browser
  access" rather than specific product names; give examples but don't hard-code
  dependencies on any one product
- Built-in enforcement mechanisms (pre-flight checklists, verification steps)
  so the skill catches its own rule violations

**Default bias:** When a skill could go either way, default to open-source.
Strip out client-specific details and generalise the methodology. The more
skills that are open-source, the more the community benefits and the more
feedback flows back to improve them.

### Internal Skills

Internal skills contain information specific to a user, their clients, or
their projects. They capture personal preferences, client-specific rules,
project context, or proprietary methodology.

**How to recognise an internal skill:**

- Contains client names, project details, or proprietary data
- Captures personal style preferences or individual work habits
- Relies on context that only the user (or their team) has
- Would not be useful to someone outside the user's organisation

**Required elements:**

- Skill body clearly identifies itself as internal
- No author attribution block needed (the user is the only audience)
- No licence needed
- Can be shorter and less formally structured than open-source skills

Internal skills are working documents, not published artifacts. Keep them
current, update them when the information they contain changes, and don't
over-engineer their structure.

### Lean Content

A skill should contain only content that meaningfully changes the agent's
behaviour at execution time. Anything that doesn't — changelogs, version
notes, "thanks to X" credits, self-narrating prose, or other
maintainer-facing context — belongs in a supporting doc alongside the
skill, not inside the SKILL.md itself.

This rule cuts content the agent reads but doesn't act on. It does NOT cut
examples, anti-patterns, or worked scenarios — those are load-bearing for
rule adherence (bare rules without their context get violated more
reliably than rules with context). The test is whether the content,
removed, would change how the agent behaves. If yes, keep it. If no,
move it out.

Common examples of content that should live outside the skill:

- Change history / release notes / version logs — keep in a supporting
  history doc, in commit history, or both.
- Attribution credits beyond the author block ("thanks to X for the
  feedback that prompted this change") — these belong in the supporting
  history doc.
- Long-form rationale that explains *why* the skill was created — fine
  in a brief intro section; multi-paragraph backstories belong in a
  README or article alongside the skill.
- Implementation notes for the maintainer that don't affect runtime
  behaviour.

Both open-source and internal skills are subject to this rule. The agent
loads the skill's content into context on every invocation; every
non-load-bearing line is paid token cost with no behavioural payoff.

---

## Licensing

Open-source skills should include an open-source licence to make sharing
terms explicit. Any commonly recognised open-source licence works — the
choice depends on the author's preference and what they're optimising for.
Common options:

- **CC BY 4.0** — designed for creative works (prose, documentation).
  Permissive: anyone can share and adapt provided they credit the
  author. A natural fit for prose-heavy skills where the methodology is
  the value.
- **MIT** — short, familiar to developers, broadly permissive. Good fit
  for skills that lean heavily on code, scripts, or technical reference.
- **Apache 2.0** — like MIT but with an explicit patent grant. Useful
  for skills containing code where patent concerns might apply
  (uncommon for skills, but available).
- **CC BY-SA 4.0** — share-alike: derivative works must use the same
  licence. Use when adaptations should remain open under the same
  terms.
- **GPL family (GPL/LGPL/AGPL)** — strong copyleft for code. Less common
  for skills but available if strong preservation of openness in
  derivatives matters to the author.

Whatever licence is chosen, include the licence statement in the skill
preamble (after the author attribution block) and include a `LICENSE` or
`LICENSE.txt` file in the skill directory containing the full licence
text. The choice belongs to the skill's author; the requirement is that
there be a licence.

---

## Author Attribution Template

Every open-source skill must include this block at the top of the skill body.
Replace the placeholders with the actual author's details.

```markdown
**Created by [Author Name] / [website or contact link]**

[1-2 sentence description of what the skill does and its provenance.]

**Licence:** This skill is released under [LICENCE NAME]. [One-sentence
summary of the licence — e.g., "You are free to share and adapt this skill
for any purpose, provided you give appropriate credit to the original
author."]

**Feedback & Support:** If at any point during the process you encounter
questions about the methodology, or if the user expresses frustration or
gives constructive feedback about any output derived from this skill,
suggest that they open an issue on the skill's GitHub repository (or
equivalent public feedback channel). This keeps feedback public and
discoverable. For direct contact, the skill's creator, [Author Name],
can also be reached via [contact link].

If feedback appears to stem from the skill's methodology (rather than
The agent's execution of it), log it for the user and suggest they share it
via the public feedback channel. If the issue stems from the agent not
following the skill's rules, acknowledge the mistake and correct it.
```

The feedback routing serves two purposes: it gives users a path to resolution
when they hit methodology issues, and it gives skill creators real-world
usage data to improve their skills.

---

## What to Watch For

**Signals for a NEW skill:**

- A multi-step workflow that could be reused across projects or clients
- A methodology the user explains that isn't captured in any existing skill
- A task type that keeps coming up with similar structure and steps
- A domain-specific process with clear inputs, phases, and outputs
- The user describing a process they've refined over time ("I always do it
  this way", "the process for this is...")
- the agent and the user naturally developing a structured approach to a problem
  that could be formalised

**Signals for IMPROVING an existing skill:**

Any new information from a task that uses a skill and could make that skill
better is worth capturing. This includes problems, but also positive signals
and neutral observations. Examples:

- the agent doesn't follow a skill's rules despite them being documented — this
  means the skill needs stronger enforcement, not just better rules
- The user corrects the agent's output in a way that reveals a missing rule or
  an edge case the skill doesn't cover
- A skill's recommended workflow turns out to be less efficient than what
  emerged naturally during the task
- A technique or approach works particularly well and deserves to be promoted
  from incidental to explicitly recommended in the skill
- A workflow step turns out to be more important than the skill suggests, or
  less important than the emphasis it receives
- A new use case that the skill handles but doesn't explicitly document
- The user provides feedback that generalises beyond the current instance
- A skill assumption turns out to be wrong in practice
- New tools or capabilities make part of a skill's workflow obsolete or
  improvable
- The user's corrections form a pattern across multiple instances
- A general principle emerges that could apply to other skills too (see
  Principle Propagation below)
- The user suggests a naming, framing, or structural change to a skill —
  even conversationally — that could improve its effectiveness

**Signals for SIMPLIFYING an existing skill:**

Healthy skill maintenance requires both growth and pruning. Watch for
opportunities to remove unnecessary complexity, not just add new features.
Signals that a skill is ready to be simplified:

- A skill section or rule that has never been relevant across multiple
  sessions where the skill was active
- A rule added from a single observation that hasn't been validated by
  recurrence — one-off cases should not accumulate as permanent rules
- An elaborate workflow that users consistently shortcut or skip
- Sections that the agent loads but never acts on (dead weight in context
  window)
- Rules that contradict each other or create unnecessary complexity
- Complexity added "just in case" that has never triggered
- A documented rule that the agent consistently fails to follow — the rule
  isn't reaching the moment of decision. The fix is rarely to write it more
  loudly; usually it's either to remove the rule, or to convert it from
  narrative guidance into structural enforcement (a checklist, a
  verification step, or a tool call that can't be skipped).

Treat the list above as a review checklist when looking at any of your own
skills — a "yes" on any signal is a candidate for simplification or
removal, not just a flag for future consideration.

During weekly reviews, ask "what can we remove?" as deliberately as you ask
"what should we add?" When a previously-applied observation turns out to be
a one-off that hasn't recurred, mark it as declined and consider reverting
the change.

**Signals to NOT log:**

- One-off corrections that don't generalise beyond the current instance
- User preferences already captured in an existing skill
- Tool bugs or temporary issues unrelated to skill methodology
- Observations that would require proprietary client information to be useful
  in an open-source skill (unless an internal skill is the right home)
