# GitHub API idioms shared by pr-review and pr-fix

Reference material for `workflows/pr-review.md` and `workflows/pr-fix.md`. Each
entry records an API behaviour that has produced a real defect in one or both
workflows. Read the relevant entry before writing any code that touches the
field it describes.

These are not style preferences. Every rule below is here because the obvious
implementation was written, shipped, and silently did the wrong thing.

---

## Reviewer bot identity: Copilot has two logins, not one

**The rule:** match reviewer logins case-insensitively on substring. Never use
exact equality.

Copilot posts under two different `user.login` values depending on what it
posted:

| What Copilot posted | `user.login` |
| --- | --- |
| A review submission (`/pulls/{n}/reviews`) | `copilot-pull-request-reviewer[bot]` |
| An inline comment on that review (`/pulls/{n}/comments`) | `Copilot` |

CodeRabbit is more consistent but still carries the suffix: `coderabbitai[bot]`.
The literal `[bot]` suffix is part of the login string for GitHub App accounts,
so `login == "coderabbitai"` matches nothing.

**Working filter:**

The stated rule is substring, case-insensitive, never anchored exact-match:
an anchored `^...$` pattern is exactly the "exact equality" trap the rule
warns against, just spelled as a regex instead of `==`, and it silently stops
matching the moment GitHub varies casing or appends/reorders a suffix on
either login. Match on the unanchored, case-insensitive substrings `copilot`
and `coderabbitai`, consistent with how both bot logins are filtered
elsewhere in this workflow:

```bash
gh api "repos/$OWNER/$REPO/pulls/$PR_NUMBER/reviews" --paginate \
  --jq '[.[] | select(.user.login | test("copilot|coderabbitai"; "i")) | .user.login] | unique'
```

**Two defects this caused, with different symptoms:**

1. In a *polling loop* the failure was loud in wall-clock terms. The reviewer
   wait compared against bare `copilot-pull-request-reviewer`, so its done-count
   was permanently zero and every run burned the full timeout before giving up.
2. In a *classifier* the failure was completely silent. Author classification
   ends in a catch-all (`All others --> Human`), so unmatched Copilot inline
   comments were relabelled as human change requests and triaged at the wrong
   priority, with no error anywhere.

The second case is the reason the patterns must be deliberately permissive: when
a classifier ends in a catch-all, a matching gap does not raise, it mislabels.

**Related trap:** a `coderabbitai` *status check* reports SUCCESS even when the
bot was rate-limited and produced no review at all. A green check is not
evidence a review happened. Count actual review submissions instead.

---

## `mergeStateStatus` and `mergeable`: settle first, then reject only

**The rule:** poll until the field is settled, then use it to reject, never to
confirm.

Both fields are computed asynchronously by GitHub. On a freshly opened or
freshly pushed PR they commonly read `null` or `UNKNOWN` for several seconds.
This produces two opposite errors, and a workflow can contain both at once:

- **Reading too early and passing.** If the only abort conditions are "PR is
  closed" and "metadata fetch fails", an unsettled read falls straight through
  to a silent proceed. An unsettled value means *retry*; it never means *passed*.
- **Trusting it as the ready signal.** Because the field lags, it is not
  evidence the branch is mergeable. Use it in the negative direction only: a
  settled `DIRTY`, `BEHIND`, or `CONFLICTING` is grounds to stop and surface,
  but a settled anything is never the signal that confirms readiness. Confirm
  readiness from the check runs themselves.

**Settling poll:**

Fetch and retain both fields on every attempt, not `mergeStateStatus` alone. `mergeable` and
`mergeStateStatus` settle independently: GitHub can report a real `mergeStateStatus` while
`mergeable` is still `null` mid-computation, or vice versa. A snippet that loops on
`mergeStateStatus` only and reads `mergeable` once outside the loop can hand the caller an
unsettled `mergeable`, reproducing the exact race this section exists to prevent, even though
`mergeStateStatus` itself looked settled.

```bash
for i in $(seq 1 10); do
  RESULT=$(gh pr view "$PR_NUMBER" --repo "$OWNER/$REPO" --json mergeStateStatus,mergeable)
  MS=$(printf '%s' "$RESULT" | jq -r '.mergeStateStatus // "UNKNOWN"')
  MG=$(printf '%s' "$RESULT" | jq -r '.mergeable // "UNKNOWN"')
  [ "$MS" != "UNKNOWN" ] && [ -n "$MS" ] && [ "$MG" != "UNKNOWN" ] && [ -n "$MG" ] && break
  sleep 3
done
```

If the loop exits with either field still unsettled, stop and surface it. Do not fall
through. `mergeStateStatus == DIRTY` (or `BEHIND`/`CONFLICTING`) is grounds to reject
independently of `mergeable`'s value, since GitHub itself computes `DIRTY` from a real
conflict; that rejection path does not need to wait on `mergeable` to settle. Every other use
of either field must wait for both.

**Why this is stated so emphatically:** `pr-fix.md` once held three incompatible
postures on this single field at the same time. Step 0 treated it as a hard
entry gate, Step 9 Phase A demoted it to "a supplementary signal only", and
Phase B, seventy-five lines later, promoted it back to "the authoritative gate".
Anyone copying a passage out of that file inherited whichever of the three they
happened to read first. One field, one posture: the one at the top of this
section.

---

## Renamed files: REST only, GraphQL cannot answer this

**The rule:** detect renames with the REST files endpoint. The GraphQL
`previousFilename` field no longer exists.

```bash
gh api "repos/$OWNER/$REPO/pulls/$PR_NUMBER/files" --paginate \
  --jq '.[] | select(.previous_filename) | {from: .previous_filename, to: .filename}'
```

The GraphQL field `previousFilename` was removed from the schema. A query still
containing it fails outright rather than returning empty, so this is a loud
failure, but the fix is a different endpoint rather than a different field name.

Renames matter to both workflows: a review that treats a rename as
delete-plus-add reports the entire file as new, and a fix run that does the same
will rewrite a file that only moved.

---

## Scanner exit codes: a verdict, not a diagnosis

**The rule:** when a scanner ran with a file-output flag, read the artifact, not
the log.

Tools invoked as `osv-scanner --output=report.json`, `trivy --output`, or
`bandit -o report.json` write their findings to a file and print only a summary
plus an exit code to stdout. Grepping the job log therefore surfaces only
whichever noise *is* printed, typically filtered or disputed advisories and a
bare `Exit code: 1`, which actively misleads diagnosis toward the wrong cause.

When the failing step is a scanner:

1. Look for `--output`, `-o`, or `--format json` in the step's arguments. If
   present, download the report artifact (`gh run download -n <artifact>`) and
   parse it.
2. If the artifact is absent, which happens when the upload step was skipped
   because the scan aborted the job first, reproduce the scan locally against
   the worktree lockfiles with the same config and read the result there.

Treat `Exit code: 1` with no visible finding in the log as a signal to go to the
artifact, never as the finding itself.

---

## An unreachable MCP server is not an empty result set

**The rule:** record transport failure as `unavailable`, distinctly from "zero
findings".

The SonarQube MCP servers are Docker-backed and routinely unreachable. So are
other MCP-backed quality gates. Collapsing a connection failure into an empty
finding list makes a run report a clean quality gate it never actually queried,
which is the most dangerous possible outcome: a false all-clear.

This is the same failure shape as the catch-all classifier above. When the
absence of a signal and the absence of a *channel* for that signal are
represented identically, the system cannot tell "nothing is wrong" from "I did
not look."

---

## Merge queues are invisible to both workflows, and the gate is Organization-only

**The rule:** before assuming a merge queue can exist on a repo, check `owner.type`.
Merge queue is an Organization-only GitHub feature. A `User`-owned repo cannot
have one, and unconditional merge-queue guidance sends every such repo down a
path that cannot succeed.

Neither workflow currently detects a merge queue at all (zero hits for
`merge.?queue`, `merge_group`, or `gh-readonly-queue` in either file). On a
queue-enabled repo the gap has three separate consequences, not one:

1. `gh pr merge` does not merge; it **enqueues**. Treating the call's success
   as "merged" is wrong the moment a queue exists.
2. The checks that gate the merge run against a distinct, ephemeral ref,
   `gh-readonly-queue/<base>/pr-<number>-<sha>`, not the PR head. Watching
   PR-head check runs on a queued repo is watching the wrong oracle entirely.
3. Every merge-completion signal derived from PR-head state (checks green,
   `mergeStateStatus`, the PR's own `merged` field) is consequently wrong.

**Verified directly:** `gh api repos/ByronWilliamsCPA/.claude --jq .owner.type`
returns `Organization`; `gh api users/williaby --jq .type` returns `User`. A
`merge_queue` rule inside a repository ruleset returns HTTP 422 against a
`User`-owned repo (CI-062), so the 26 `williaby` repos structurally cannot have
a merge queue no matter what guidance is written for them.

**Gate every merge-queue branch on this check, run once per repo:**

```bash
gh api "repos/$OWNER/$REPO" --jq .owner.type
```

Only take the queue-aware path (enqueue detection, `gh-readonly-queue` ref
reads, queue-specific completion polling) when this returns `Organization`.
When it returns `User`, `gh pr merge` already merges directly and PR-head
checks are already the correct oracle: running queue-detection logic there
does not just waste a call, it risks manufacturing a false "stuck in queue"
diagnosis for a queue that cannot exist on that repo.

---

## Machine-output parsing and exit-code traps: three ways a poll loop lies about its own state

**The rule:** validate a `--json` field name before looping, treat `false` as
a real value in `jq`, and never trust `$?` after a pipe.

Three independent traps, verified separately, each producing a loop that keeps
running and keeps reporting a result while never actually having checked
anything:

1. **An invalid or misspelled `--json` field name.** `gh` errors on a field
   name it does not recognize for that subcommand. If a poll loop pipes the
   command straight into `jq` without checking `gh`'s own exit status, that
   error is discarded and every iteration silently falls into the "not yet"
   branch, running to timeout having never read real state even once. Validate
   the field list once, outside the loop, and check `gh`'s exit code, not just
   the piped output. Reproduction, verified 2026-09-06: a bad field prints
   `Unknown JSON field: "..."` to stderr and exits 1, so on its own the failure
   is loud. It goes silent only through the capture idiom, because
   `MS=$(gh ... --json badField --jq .badField 2>/dev/null)` discards both the
   message and the status and yields an empty string, which then fails every
   `[ "$MS" = "CLEAN" ]` test forever. The defect is in the capture, not in `gh`.
2. **jq's `//` alternative operator treats `false` as empty.** `.mergeable //
   "unknown"` replaces a real, settled `false` with the fallback string,
   because `//` treats `false` the same as `null`. Use
   `if .mergeable == null then "unknown" else .mergeable end` instead, which
   substitutes only on an actual `null`.
3. **A pipeline destroys `$?`.** `$?` after `cmd1 | cmd2` reports `cmd2`'s
   exit status, never `cmd1`'s. Confirmed twice in this repo's own operating
   history: a test suite run as `bats ... 2>&1 | tail -3 && echo OK` reported
   green while a test was actually failing, because the reported status was
   `tail`'s; the same shape later masked three of four `git commit` calls that
   had actually failed, because the batch was piped through `tail -4`. Use
   `set -o pipefail` before the pipeline, or read `${PIPESTATUS[0]}` directly;
   never trust the bare `$?` that follows a pipe.

**Why this is stated so firmly:** none of these three fail loudly. There is no
crash and no visible error, only a loop that finishes on schedule and reports
a plausible-looking result. A silent no-op in a terminal watch step is worse
than a loud failure, because nothing downstream ever learns the step did not
actually check anything.

---

## The verification instrument can manufacture the finding it claims to check for

**The rule:** distrust a clean result from the checking tool as much as a
dirty one. A scanner, grep, or count can be wrong about its own inputs, not
just about the code it is scanning.

The strongest confirmed case was logged twice, 26 days apart, against the
exact same rule: `grep -P '\xe2\x80\x94'` matches NOTHING against a real
em-dash. Inside single quotes the shell passes the backslash-escape text
through unchanged, so PCRE receives a 12-character literal string
(`\`, `x`, `e`, `2`, `8`, `0`, `9`, `4`, ...), not the 3 raw UTF-8 bytes
(`E2 80 94`) that make up an em-dash. The pattern compiles and runs with no
error, so a zero-match result reads as "no em-dashes here" when it actually
means "this escape form cannot match the byte sequence at all." Verified
working forms, all three confirmed:

- The raw bytes constructed directly, bypassing PCRE's own escape handling:
  `` grep -n "$(printf '\xe2\x80\x94')" FILE ``
- PCRE's own codepoint escape (distinct from a `\x` byte escape):
  `grep -P '\x{2014}' FILE`
- ANSI-C quoting, which expands the escape to real bytes before grep ever
  sees the pattern: `grep -- $'\xe2\x80\x94' FILE`

Two related traps in the same class:

- `grep -c` counts matching **lines**, not occurrences. A line carrying three
  em-dashes counts as 1, not 3, so a `grep -c` total under-reports the true
  finding count whenever more than one hit lands on a single line.
- A config shim or a measurement-only flag can create a finding, or suppress
  one, that exists only under the harness and never under the real run being
  checked. A passing local check is only evidence if it runs the exact command
  CI runs, not an adapted stand-in for it.

**Why this is stated so firmly:** the em-dash case recurred verbatim against
the exact same documented rule 26 days later; the rule being written down once
did not stop it happening again. A wrong tool is not caught by re-running the
tool. It is caught by giving the tool a known-bad input first, a positive
control, and confirming it flags that before trusting a clean result on the
real one.
