# Confidence scoring and Critical-finding validation detail

This covers the detailed procedure for Step 6 (Confidence Scoring) and Step
7b (Validate Critical Findings) of `workflows/pr-review.md`: the Haiku
scoring rubric with its anchor examples and caps, the tier-assignment table,
and the evidence-ladder validation of Critical findings (empirical CI
evidence, empirical local execution, primary-source verification, and
cross-model consensus via the `/panel` skill engine, including the security
finding validation pass). The spine keeps the `## Step 6` and `## Step 7b`
headings with short orchestration stubs; the full procedures live here.

---

## Step 6 detail: Confidence Scoring (parallel Haiku agents)

For each finding returned by Agents A–M, launch a parallel Haiku agent with:

```text
Score this code review finding on a scale of 0–100.

Finding: {finding description}
File: {file}
Agent source: {A|B|C|D|E|F|G|H|I|J|K|L|M}
PR diff context: {10 lines of diff around the finding}

Scoring rubric:
- 0:  False positive that doesn't survive basic scrutiny, or pre-existing issue
      unrelated to this PR's changes.
- 25: Might be real, hard to confirm. Speculative.
- 50: Verifiably real, but low impact; affects edge cases rarely hit.
- 75: Real and impactful; will affect users or functionality in normal use.
      Or: directly called out in CLAUDE.md.
- 100: Certain, frequent impact. Direct evidence in the diff confirms it.

Anchor examples and caps (small scoring models pattern-match "violates a standard" to
high scores and cluster at round numbers; these constraints correct both):
- 75+ requires user-visible breakage, data loss, dead links shipped by the PR, or a
  hard CLAUDE.md rule violation evidenced in the diff.
- PR-body process hygiene (unchecked acceptance-criteria checkboxes, missing `Fixes #N`
  issue references, description completeness, missing motivation section) is capped at
  49 (Suggested) unless the finding evidences an actual untested code-behavior risk in
  the diff. A statically-verifiable no-op (e.g., a boolean input that is never read,
  default false) is not Critical.
- Doc-nit findings (doc count off-by-one, missing Bash
  permissions allow rule, SKILL.md frontmatter gap, style/vocabulary inconsistency) are
  capped at 65 (Important) unless they break a build, lose data, or violate a hard
  CLAUDE.md rule.
- Severity is impact multiplied by reachability. For code/config/detection content the PR
  ITSELF documents as not-yet-activated (feature-flagged off, awaiting a documented out-of-
  band deploy step, or guarded by an as-yet-undeployed component), a genuine correctness
  defect is at most Important (must-fix-before-activation), not Critical (must-fix-before-
  merge), unless merging itself activates it. A real bug in code that cannot execute yet is
  real but deferred; do not conflate "this is a real bug" with "this blocks merge."
- Cite ONLY rules present verbatim in the provided context. Do NOT invent a project
  rule to justify a tier (e.g., do not claim CLAUDE.md mandates issue references; it
  mandates Conventional Commits and says nothing about issue references).
- If the finding's check is pre-assigned a tier by an Agent prompt in this workflow
  (e.g., Agent J's [Suggested] checks), the score MUST stay within that tier's range
  unless the diff provides direct evidence of higher impact.
- Do not default to the 50 boundary. If torn between Important and Suggested, pick a
  score that reflects the decision, not 50 exactly.

Additional constraint: If the agent source is C (Git History) or D (Prior PR
Comments) AND the finding describes historical context, file churn, or past review
patterns rather than a specific, fixable line in the diff: cap the score at 20
regardless of the rubric above. Two exceptions lift the cap:

1. A C or D finding that cites a specific prior commit SHA where the now-reappearing
   lines were removed or reverted. It is the SHA citation, not the agent source, that
   lifts the cap; vague history churn stays capped regardless.
2. Agent M (source M) findings. Agent M is never a C or D source; its checks are
   evidence-grounded appropriateness judgments that do not fit the "historical context"
   profile the cap targets. The cap does not apply to M.

Return ONLY a JSON object:
{"score": <number>, "rationale": "<one sentence>"}
```

**Tier assignment from score:**

| Score | Tier |
| ----- | ---- |
| 75–100 | Critical |
| 50–74 | Important |
| 25–49 | Suggested |
| 0–24 | Informational |

**Do not discard any finding.** All four tiers appear in the output.
The old practice of dropping findings below 80 does NOT apply here.

---

## Step 7b detail: Validate Critical Findings

After deduplication, validate the Critical tier before assembling the final report. This
catches false positives before they reach the user. Validation follows an evidence
ladder: cheaper, more authoritative evidence first; cross-model consensus only for what
remains.

**Evidence precedence (apply in order; stop as soon as a Critical finding is resolved):**

1. **Empirical evidence from the PR's own CI run.** The system under review has often
   already executed the disputed code path. Before any model call, check whether the
   PR's own check conclusions, skipped jobs, or step outputs already demonstrate or
   refute the claimed behavior (e.g., "Documentation Links: SKIPPED" on a pull_request
   event proves a boolean gate works). Observed runtime behavior from the head SHA
   outrules model opinion in either direction. Resolve the finding on it and skip the
   consensus call for that finding.
2. **Empirical local execution (only when the local checkout is already at the PR head
   SHA).** If `git rev-parse HEAD` equals the PR head SHA and a Critical finding is an
   empirical claim (test-plan counts, lint result, build result), run the stated command
   locally with a timeout and use the result as authoritative. This is a deliberate,
   read-only exception to "no local checkout for review": running a command on an
   already-matching checkout does not touch the working tree. Never check out the PR to
   create this condition; only use it when it already holds.
3. **Primary-source verification for third-party-tool and cross-repo claims.** When a
   Critical finding (or a bot-reviewer concern) hinges on the runtime semantics of a
   third-party action or tool (python-semantic-release, sigstore, actions/checkout) or
   on state outside the diff (another repo's file names, an external convention, remote
   config), spawn a `research-agent` to verify against the tool's documentation or
   source, or `gh api`-dereference the external state, BEFORE consensus scoring.
   Doc-verified or directly-checked evidence overrides agent confidence in both
   directions. Crucially: when multiple agents converge on a finding whose correctness
   depends on state outside the diff, that agreement is NOT independent confirmation
   (the agents share the same evidence boundary). Verify the external fact directly and
   weight convergence as zero additional evidence; a clarifying-comment suggestion may
   survive, but the "bug" framing must not. This verification gate keys on the TYPE of
   claim, not the source's provenance: a technical claim about tool/runtime/library
   semantics (or about state outside the diff) from one of THIS workflow's own dispatched
   subagents (Agents A-M) gets the same authoritative-doc / direct-check verification that
   Step 8 applies to bot review comments, BEFORE it is tiered Critical or Important. An
   agent you dispatched is as capable of a confident, plausible, wrong claim as an external
   bot; trusting your own subagents more than bots is an unjustified asymmetry that lets
   false positives in through the side door.

   **Bot-finding disposition has two independent axes: is the CONCLUSION right, and is the
   STATED RATIONALE right.** These do not always agree, and refuting one is not refuting the
   other. A bot can reach the right conclusion via the wrong rationale (it cites a rule that
   does not exist, but the flagged line is still defective for a different, real reason); this
   is a distinct outcome from being simply wrong, and treating it as "rationale false, so
   decline" silently drops a genuine finding with no trace in the report. Dispose of every
   bot finding into one of three outcomes, not two:

   | Conclusion | Rationale | Disposition | What to post |
   | --- | --- | --- | --- |
   | Correct | Correct | Keep as-is | Forward the finding and the bot's own rationale unchanged. |
   | Correct | False | **Rationale wrong, finding stands** | Keep the finding; replace the bot's stated reason with the independently-derived one, and say so explicitly ("the cited rule does not apply; flagging for {actual reason} instead") so the record does not misattribute the correct call to a rule that does not exist. |
   | Wrong | (either) | Declined: false positive | Post the doc citation or direct-check evidence that refutes the conclusion; do not forward the fix. |

   Before declining a bot comment solely because its cited rule, tool semantics, or hook
   scope turns out to be false, re-examine the flagged line on its own merits; a checker's
   scope disclaimer or a wrong cited rule refutes the RATIONALE, not necessarily the
   CONCLUSION. A wrong disposition posted to a bot thread (declining a real finding, or
   forwarding a false one under a borrowed correct-sounding reason) corrupts the public PR
   record in a way a private miss does not; get the row right before posting, not after.
4. **Cross-model consensus (7b-1 / 7b-2 below)** for Critical findings still unresolved
   after steps 1-3.

**A finding whose entire evidence is an absence needs a higher bar than a positive one.**
"X is missing," "nothing handles Y," or "no control does Z" is a claim about the whole search
space, not about the one place searched, and it is a distinct failure mode from a positive
finding: a positive finding is wrong only if the cited thing is misread, but a negative one is
wrong whenever the search could not have found the thing even if it existed. Before including
an absence-only finding, establish all three of:
1. **Query provenance.** What actually ran, and could it have found X if X existed? A
   zero-match `grep` over one directory tree only proves absence within that tree; some
   controls are enabled at a control-plane or platform level with no in-repo file to grep for
   at all, so a search that only reads checked-in files can return "not found" for something
   that is very much present and enforced elsewhere.
2. **Non-repo locations where X could legitimately live.** Org-level shared config, git
   submodules, generated build output, and CI-platform settings (branch protection, app
   installations, dashboard-only toggles) are all real places a control can live without a
   corresponding line in this repo's tree. An absence claim that never looked there is
   incomplete, not confirmed.
3. **The checker's own stated scope.** When the evidence for "missing" is "a repo checker
   should have caught this and didn't," read that checker's source or docstring before trusting
   the inference. A checker's name advertises ambition; only its documented scope is evidence.
   A checker that explicitly disclaims the exact property in question (for example, one whose
   own docs state it verifies a citation resolves but not that the citation discriminates the
   claimed property) proves nothing about that property either way, and a green run from it is
   not corroboration.

A null grep published as a nonexistence claim is a wrong finding, not a conservative one. Note
the adjacent risk this does not resolve: even a broadened search is only as good as the
instrument running it (a malformed pattern, an untested regex, a tool flag that silently
narrows scope can all manufacture the same false "not found"); verifying scope and location
does not substitute for verifying the query itself actually works, which is a separate check.

**Before the consensus call, extract a 15-line diff context window for each remaining
Critical finding.** Locate its `file` and `line` in `PR_DIFF` and capture lines
`[line - 7 .. line + 7]` (clamped to file boundaries) so models assess the actual code,
not just the description.

### 7b-1. Cross-model false-positive filter (Critical findings unresolved by the ladder)

If any Critical findings (score 75-100) remain after the evidence ladder, validate them
with the `/panel` skill engine (one-shot; replaces the PAL `tiered_consensus` call
that reliably returned setup-only messages with no verdicts):

```bash
cat > /tmp/prreview-consensus-prompt.txt << 'PROMPT'
You are reviewing Critical-tier findings from a PR code review. For each finding,
decide: is this a genuine defect that must be fixed before merge, or is it a false
positive? A false positive is a finding that does not survive scrutiny when you read
the actual code context provided.

Findings (JSON array):
{Critical findings as JSON with finding_id, file, line, description, score, rationale,
 and 15 lines of diff context around the finding}

Return a JSON array; for each finding:
{ "finding_id": N, "verdict": "genuine" | "false_positive", "reason": "one sentence" }
PROMPT

uv run .claude/skills/panel/scripts/consensus_cli.py select \
  --level "$CONSENSUS_LEVEL" --domain code_review > /tmp/prreview-roster.json
uv run .claude/skills/panel/scripts/consensus_cli.py run \
  --prompt-file /tmp/prreview-consensus-prompt.txt \
  --roster-file /tmp/prreview-roster.json --level "$CONSENSUS_LEVEL"
```

Synthesize the per-model responses yourself (do not delegate synthesis to a template):
a finding is `false_positive` only when a majority of succeeded models agree it does not
survive scrutiny.

**Incomplete-response fallback:** If the engine reports `succeeded < 2` (every model
failed, or only one voice returned), note "consensus validation: incomplete
(succeeded < 2); proceeding on independent evidence quality" and continue. Downgrade no
findings on an incomplete response. Do not retry within the same review.

Apply the verdicts: move any finding the panel marks `false_positive` from Critical to
Informational, appending "(consensus: false positive: {reason})" to its rationale.

### 7b-2. Security finding validation (Critical security findings only)

Route by the finding's SUBSTANCE, not its origin. Agent I (Security Pass) is not the
only source of a genuinely security-relevant Critical finding: Agent B (CLAUDE.md
compliance), Agent M (premise/regression), or any other agent can surface an
injection vector, an auth/authz bypass, a secrets-handling defect, or an unsafe
deserialization path while investigating something else entirely, and a "Security/"
description prefix is a formatting convention some agents use and others do not.
Route a Critical finding through the security pass below if EITHER:

- it originates from Agent I, or its description carries the "Security/" prefix, OR
- its content otherwise describes a security-relevant defect category regardless of
  source agent or description formatting: injection (SQL, command, template, log),
  authN/authZ bypass, secrets or credential exposure, unsafe deserialization,
  path traversal, SSRF, insecure cryptography, or a supply-chain/dependency
  vulnerability.

When in doubt whether a finding fits one of those categories, route it through the
security pass; the cost of one extra `--domain security` call is far cheaper than a
real vulnerability validated only by the generic false-positive filter. For any
Critical finding routed here, repeat the 7b-1 engine call with `--domain security` and
`--level 2` (security decisions warrant more model coverage regardless of
`CONSENSUS_LEVEL`), using this prompt:

```text
You are validating security findings from a PR review. For each finding, assess: is
the vulnerability real and exploitable given the code context, or is it a false
positive?

Findings (JSON array):
{Security findings as JSON with finding_id, file, line, description, score, and 20
 lines of diff context}

Return a JSON array; for each finding:
{ "finding_id": N, "verdict": "real" | "false_positive",
  "exploitability": "high" | "medium" | "low" | "theoretical",
  "reason": "one sentence" }
```

If 7b-1 already returned an incomplete response (`succeeded < 2`), skip 7b-2: the same
engine in the same session will near-certainly return the same outcome, and level 2 is
not free. Note the skip.

Apply security verdicts: downgrade `false_positive` security findings from Critical to
Important (not removed, so reviewers still see them). Retain `exploitability` in the
finding rationale: "(consensus security: {exploitability}, {reason})".
