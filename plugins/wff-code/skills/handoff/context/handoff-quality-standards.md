# Handoff Quality Standards (reference)

> Read-only reference for the `handoff` skill. The SKILL.md carries a short
> digest of the highest-value rules inline; this file holds the full set,
> including the edge-case git forensics that only some sessions need. A handoff
> is a snapshot of a past moment, not ground truth. The consuming session must
> treat it as a starting hypothesis, not a task list to execute blindly.

## For handoff authors

**Separate GOAL from MECHANISM.** For every prescribed action, state:

- The GOAL: what outcome the change must achieve (required)
- The MECHANISM: the specific edit or command assumed to achieve it (optional,
  clearly flagged as an assumption)

When the mechanism rests on an unverified structural assumption (CI runs tests
inline, a field exists in the data, a tool is on PATH, a function accepts a
certain parameter), the consuming session needs the goal to recover gracefully
when the assumption fails.

Bad: "Add a step inside the CI Gate job, which already has Python set up"
Good: "Ensure CI validates the manifest self-consistency check. The current
ci.yml may delegate to a reusable workflow; confirm where Python tests actually
run before deciding which file to edit."

**Distinguish verified from speculative.** Tag any field names, API endpoints,
CLI flags, assertion patterns, or identifier names that were NOT directly
verified against the live source as `[VERIFY before implementing]`. This tells
the consuming session which parts need a probe check:

```markdown
## Implementation notes
- The manifest uses `applies_to` (verified at manifest:line 42)
- The check accepts `--check-id` flag [VERIFY: grep check-repo-compliance.py --help]
- Severity should be `suggested` on introduction [VERIFY: confirm current policy]
```

**Pre-written artifacts must be paste-correct for the introduction state.** When
a handoff includes literal YAML, JSON, or code blocks to be pasted, the literal
value must be correct for the moment of introduction, not the eventual target
state. When introduction state and end state differ on a field (e.g.,
`severity: suggested` introducing a check that will later be promoted to
`severity: critical`), annotate the divergent field inline:

```yaml
severity: suggested  # target: critical after 100% fleet reach
```

Do not rely on a separate "Rollout note" prose section to communicate the
introduction state; an implementer copying a block trusts the block, not a
paragraph three sections away.

**Include coupled-invariant checklists.** For known artifact types, list the
secondary edits that must accompany the primary change:

- **Standards manifest check addition:** also update `last_updated` in the
  manifest header and classify the commit per `manifest-changes.md` (feat vs
  fix); the changelog is generated from the commit at release, not hand-edited
- **Pre-commit hook addition:** also verify `rev:` is pinned to a SHA, add to
  `additional_dependencies` if needed, run `pre-commit autoupdate` or pin
  manually

**Cite only durably-stored artifacts (Obs 187).** A handoff is only as resumable
as its least-durable cited artifact. Naming a file is not preserving it: the
receiving session inherits the citation but not necessarily the bytes. For every
data artifact the handoff cites as a source, verify it resolves to a path inside
durable/version-controlled storage, NOT `/tmp` or another ephemeral location:

```bash
# At handoff-write time, while the file still exists:
for f in <each cited artifact>; do case "$f" in /tmp/*) echo "EPHEMERAL: $f";; esac; done
```

Surface any artifact that exists only in `/tmp` as a preservation risk and
either copy it into the durable folder or note explicitly that it must be
regenerated (and from what). Verify durability at write time, not at resume time
when the file may be gone.

**Quote counts and tallies from the source verbatim (Obs 276).** Handoffs are
lossy compressions, and numeric claims are where loss is most damaging because
downstream sessions use them as completion criteria. When summarizing an
artifact's claims (finding counts, severity tallies, file counts), copy the
artifact's own numbers verbatim rather than paraphrasing. If the source is
internally inconsistent (executive summary says "two", the numbered list has
three), state the discrepancy explicitly ("doc internally inconsistent: summary
says 2, list has 3") instead of silently resolving it to one value.

**Add a consumer trace to every file:line edit spec (Obs 414).** A "repoint A
onto B" or "edit file X" task carries a hidden assumption that the named entry
point is on the live critical path. In repos with duplicated loaders or parallel
entry points (common during a migration), the named file may be DEAD relative to
the gate that actually consumes the output. Before accepting the framing, trace
the consuming artifact: for each entry point, name the downstream artifact and
the gate/script that reads it, and state explicitly whether the entry point is
on the live gate path or a parallel/legacy path. A spec that lists file:line
edits without a consumer trace can send an implementer to harden a path nothing
reads while the real risk (loader duplication/drift) goes unnamed.

**Preserve a pre-existing versioned artifact before writing a same-named
deliverable (Obs 454).** "Write to FILE" does not imply FILE is empty. A
same-named artifact from an earlier run is evidence, not clutter: it may encode
conclusions formed before a later discovery. Before writing any versioned or
re-run deliverable to a named path, check whether the path already exists; if it
does, read its provenance (embedded date/commit, or git metadata), and if it is
a prior run of the same artifact, preserve it under a date- or commit-stamped
name rather than overwriting. Diff the headline conclusions and surface any
divergence to the user rather than silently replacing.

**Put a superseding pointer at the TOP, not only at the end (Obs 463).** A
handoff is read in order, so a correction placed AFTER the thing it corrects is
not a correction for a sequential reader who acts top-to-bottom. When a later
edit contradicts the existing body, do not rely on an end-of-file addendum
alone. Place a short banner at the very top that enumerates the reversed claims
and points to the truth:

```markdown
> **SUPERSEDED ON N POINTS (read first):**
> - Body says "scoring fixed, no more modeling" -> VOID; one modeling task remains (see Addendum).
> - Body framing "own-leaning" -> VOID; framing is current-anchored.
```

The body stays for unaffected detail; the banner prevents a top-to-bottom reader
from acting on the stale parts. Supersession belongs at the first point of
contact, with the void claims named explicitly.

## Documenting orphaned branches, stashes, and other uncommitted git artifacts

When the handoff describes a local branch with no remote, a git stash, or any
uncommitted artifact, run a content-level supersession and freshness check
BEFORE drafting action options. Commit ancestry is an unreliable signal in
squash-merge repositories: ahead/behind counts, `git log main..branch`, and
`git cherry` all break when a branch was squash-merged or re-implemented under
different SHAs. A branch that reads as "3 commits, no remote, 20 behind main"
may already be fully delivered on main.

Run these cheap checks at write time and record their results in the doc:

```bash
# Supersession by content: does main already define the branch's distinctive symbols?
git grep -n 'distinctive_symbol_from_branch' origin/main
git diff origin/main <branch> -- <each touched file>   # two-tree diff, NOT three-dot
gh pr list --state merged --search "<branch commit title>"  # squash-merge by title

# For a stash: diff against the CURRENT merged main, direction-checked
git diff <current-main> 'stash@{0}' -- <each touched file>

# Record the upstream sync point the claims were evaluated against
git rev-parse origin/main
git rev-list --left-right --count origin/main...HEAD   # local-vs-origin divergence
```

Then write the action options ordered by likelihood after the check, not by
effort:

- If the branch or stash content is already on main (symbols present, per-file
  diff empty, or a squash-merged PR shares the title), lead with "likely
  superseded, verify and delete" instead of an elaborate PR-split or cherry-pick
  plan.
- State the invariant the work was meant to establish (e.g., "no unpinned
  actions", "digest-pinned images"), then test whether main already satisfies
  it. Close as superseded-by-outcome when the invariant holds even though the
  patches differ. Patch identity and outcome identity are different equivalence
  classes; `git cherry` tests only the former.
- Never assert branch topology ("this was the tip of the branch that became
  PR #N", "these are post-merge tweaks") from commit-message inference. Back
  every topology claim with `git merge-base --is-ancestor` output, and record
  the local-vs-origin divergence so the consumer knows whether the checkout was
  stale when the claim was made.

## For handoff consumers (mandatory pre-flight before acting on any handoff)

**Re-verify current state before executing.** A handoff's "What Remains" section
describes work as of the moment it was written. Branches and PRs advance after a
handoff is created. The cheapest, highest-leverage first action when resuming is:

```bash
git fetch --all
gh pr list --state all
gh pr view {PR_NUMBER} --json state,mergeable,checks  # if PR referenced
```

Treat "What Remains" as a hypothesis. Diagnose the CURRENT state of the work
before executing the handoff's plan. A 2-minute check may reveal that the
"remaining work" is already complete, or that the actual blocker is different
from what the handoff described.

**Check whether another session is already executing this handoff.** A handoff
doc is a work queue with no locking; in a multi-session environment any doc that
says "the team executing this decides" will eventually be executed twice. Before
acting:

- Run `gh pr list --head <branch>` for every branch the handoff names, and scan
  for recent PRs or worktrees whose content matches the handoff's work. A match
  means another executor is already on it; coordinate or stand down rather than
  producing duplicate PRs.
- Mark the handoff file as claimed so a second session sees the claim: rename to
  `.executing-<session-id>.md` or prepend a `CLAIMED: <timestamp> <session-id>`
  header. On completion, update the file to `RESOLVED` rather than deleting it,
  so a late-arriving session sees the outcome instead of an apparently-open queue.

**Treat completed-fix claims as hypotheses when a live symptom contradicts
them.** A handoff or plan doc records what a session believed at write time; the
"fix" may have been wrong or later reverted. Whenever a current symptom
contradicts a recorded "done" item (a 404 after a config was reportedly "fixed
live", a test failing that was reportedly passing), re-verify the claim against
the live system (API, config, run logs) before extending work that depends on
it. The live system wins; do not rationalize the symptom to fit the note.

**Re-resolve pinned external references at merge time.** Pre-flight must cover
not just the state of the work queue but the freshness of facts embedded in
queued work. For any PR or instruction that pins an external ref (commit SHA,
version number, image digest, URL), re-resolve the ref at merge time and confirm
the pinned target still matches intent. A long-lived PR that pinned an org
reusable workflow weeks ago can silently downgrade it when merged as-written if
the upstream file has since changed. Verify the original reason for the pin
still holds at the current ref before merging or updating it.

**Verify external identifiers before building.** Before using any identifier
named in the handoff (check IDs, file paths, CLI flags, API endpoints, function
names, schema field names), confirm it exists in the current live source:

- Check IDs: grep the manifest (`grep "id: CI-NNN" docs/standards-manifest.yaml`)
- File paths: `test -f {path}` or `ls {path}`
- Function names: `grep "def {name}" {file}`
- CLI flags: `{tool} --help | grep {flag}`

A handoff mixes verified observations with speculative scaffolding, and the
reader cannot tell them apart by tone. The fix is to verify before building.

**Probe data schemas before writing assertions.** If the handoff prescribes
tests or assertions against a data structure, run a schema probe of the actual
data first:

```python
import yaml; data = yaml.safe_load(open("manifest.yaml")); print(list(data['checks'][0].keys()))
```

Assertions against fields that do not exist will raise `KeyError` (dict key
access) or fail for the wrong reason (if `dict.get()` returns `None` and the
assertion happens to pass on that).
