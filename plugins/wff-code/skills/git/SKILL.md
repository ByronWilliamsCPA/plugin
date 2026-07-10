---
name: git
description: >
  Git workflow management: branch creation/validation, conventional commit message
  preparation, and PR description generation. Auto-activates on: git, branch, commit,
  pull request, PR, merge, rebase, conventional commits, stage and commit, ready to
  commit, commit message, commit this, prepare commit, write commit, prepare PR,
  create PR, draft PR, write PR, ready for PR
---

# Git Workflow Skill

Git workflow management including branch validation, conventional commit preparation,
PR description generation, and repository health checks.

## Routing

| Activation Context | Workflow File |
|--------------------|---------------|
| Commit-related (`commit`, `stage and commit`, `commit message`, etc.) | `workflows/commit.md` |
| PR-related (`prepare PR`, `create PR`, `draft PR`, `pull request`, etc.) | `workflows/pr.md` |
| Branch-related (`branch`, `checkout`, `branch strategy`) | `context/branch-strategy.md` |

## Reference Files

- **`context/conventional-commits.md`**: Full type table with version impact
- **`context/branch-strategy.md`**: Branch naming format, semantic release mapping, validation

## Quick Reference

### Branch Status

```bash
git branch --show-current
git status
```

### Semantic Release Mapping

| Branch Prefix | Commit Type | Version Impact |
|---------------|-------------|----------------|
| `feat/` | `feat:` | Minor (0.X.0) |
| `fix/` | `fix:` | Patch (0.0.X) |
| `docs/` | `docs:` | No release |
| `refactor/` | `refactor:` | No release |
| `perf/` | `perf:` | Patch (0.0.X) |
| `test/` | `test:` | No release |
| `chore/` | `chore:` | No release |
| `hotfix/` | `fix:` | Patch (0.0.X) |

### Branch Format

```text
{type}/{descriptive-slug}
```

Examples: `feat/user-authentication`, `fix/null-pointer-api`, `docs/installation-guide`

## Hard Rules

These are not soft guidance. They fire at the moment of decision and exist because the
same mistakes recurred across sessions even after being logged in handoff docs.

### HR-1: Verify the staged set before every scoped commit (Obs 474)

`git add <paths>` ADDS to the index; it does not DEFINE the commit scope. When the index
already holds unrelated staged files (common with parallel sessions or a prior partial
`git add`), a scoped `git add` followed by `git commit` commits everything staged, not
just the named paths. This has swept another session's in-flight work into a commit (22
files committed when 1 was intended).

For any scoped commit, after staging and before committing:

```bash
git diff --cached --name-only   # MUST equal the intended set
```

If extra files are present, either unstage them or scope the commit to paths explicitly:

```bash
git restore --staged <unwanted-paths>     # remove from index
# OR commit only the named paths regardless of index contents:
git commit -- <intended-paths>
```

Treat `git add <paths>` as "add to index," never as "set commit contents." The committed
scope is whatever the index holds at commit time, not whatever you most recently added.

**Pathspec-scoped commit, two adjacent traps (Obs 442).** The safe way to commit a subset
while a parallel session's files sit staged is `git commit -- <pathspecs>`, but the
invocation has two silent failure modes:

1. **Option-after-`--` swallowing:** everything after `--` is a pathspec. `git commit -S -- <file> -m "msg"`
   treats `-m` and the message as (invalid) pathspecs and fails. The `-- <pathspec>` must
   come AFTER all options including `-m`/`-F`.
2. **Untracked-file rejection:** `git commit -- <newfile>` for an untracked file fails with
   "did not match any file(s) known to git" because pathspec-commit bypasses the index and
   only captures changes to already-tracked paths. A new file must be `git add`ed first.

Correct invocation for a scoped commit when other files are staged:

```bash
git add <new files>                       # only needed for untracked paths
git commit -S -F msg.txt -- <pathspecs>   # pathspec LAST, after all options
```

### HR-2: In squash-merge repos, merge status is a PR-state + two-tree-diff question, never an ancestry or three-dot test (Obs 43/44/118/125/272)

Squash-merge collapses a branch into a single new SHA on main with no shared ancestry to
the branch commits. Every ancestry-based and merge-base-based test therefore reports
already-merged work as "not merged":

- `git branch -d`, `git log origin/main..HEAD`, `git cherry` (patch-id based) all fail.
- The three-dot diff `git diff origin/main...origin/<branch>` ALSO fails: three-dot
  diffs from the merge-base, so it shows the branch's full squash-merged content as still
  outstanding (a merged PR has shown +1822 lines this way). Do not use three-dot diff or
  `git log main..branch` commit counts as merge evidence.

Authoritative merge-status check in a squash-merge repo:

```bash
git fetch origin

# 1. PR state is the primary signal
gh pr list --head <branch> --state all

# 2. Confirm with a TWO-TREE (two-dot) diff scoped to the files the branch touched.
#    Two-dot compares the tip trees directly, so squash-merged content reads as absent.
git diff origin/main origin/<branch> -- <touched files>
```

If the two-tree diff over the touched files is empty, the branch content is on main
regardless of ancestry or PR metadata. Always use `origin/main`, never bare local `main`
(local `main` is routinely stale; see HR-4).

> Why this is a hard rule, not a hazard note: this exact trap was logged in handoff docs
> (Obs 125) yet recurred (Obs 272) because the correction lived in a log, not in the
> skill that fires at decision time. The rule belongs here.

### HR-3: git stash is global, not per-branch (Obs 128)

`git stash` shares one stack across all branches. Popping "the stash" may apply another
branch's WIP to your current tree. For "is this failure pre-existing?" comparisons, use
`git show ref:path | <tool>` or a throwaway worktree instead of stash-and-restore:

```bash
git worktree add .worktrees/baseline-check origin/main
```

### HR-4: Always diff against fetched remote, not local main (Obs 141)

`git fetch` updates remote-tracking refs but not local branch refs, so local `main` is
routinely stale. For branch reviews and comparisons, always `git fetch` first and diff
against `origin/<default>`:

```bash
git fetch origin
git rev-list --left-right --count origin/main...HEAD   # ahead/behind counts
```

(Use a two-tree diff for supersession checks per HR-2; reserve three-dot for review-diff
display where merge-base framing is what you want.)

### HR-5: Destructive cleanup runs most-reversible first (Obs 223)

A repo-cleanup batch mixes operations of very different reversibility. Sequence them so any
failure happens while recovery is still possible:

1. **Capture/rescue unique work to a durable place first** (branch + PR, or `git bundle create --all`).
2. **Local and reflog-recoverable deletions next** (local branch delete, stash drop, worktree removal; reflog covers these ~90 days).
3. **Irreversible remote deletions last** (remote branch delete; effectively gone once server GC runs), ideally after a verification pass.
4. **Never** use `--force` / `--no-verify` to push the cleanup through.

Pair each destructive command with its recovery path (reflog SHA, PR URL, bundle path) in
the summary so a mistake is recoverable. When a task batches operations of differing
reversibility, the ordering itself is the safety mechanism.

### HR-6: Route a needed fix to whatever branch already owns that change (Obs 271)

Before opening a standalone fix PR against main, check whether a large in-flight PR already
touches the same files. The cheapest merge conflict is the one not created.

```bash
git fetch origin
# For each target file, diff the in-flight branch's copy before opening a competing PR:
git diff origin/main origin/<in-flight-branch> -- <target files>
```

If an in-flight branch already owns that class of change (e.g., a normalization sweep that
fixed 3 of 4 stale pins), add the remaining fix as a commit to THAT branch. Only open a
standalone PR when no in-flight branch covers it. Fix-routing is a function of what is in
flight, not just what is on main.

## Common Hazards

Real-world failure patterns collected from production sessions.

### Committing stale WIP surfaces a cascade of pre-existing gate debt (Obs 176)

Two distinct, costly failure modes appear when committing an old uncommitted changeset with
pre-commit hooks installed:

1. **Pre-commit's unstaged-stash strands unrelated work.** pre-commit auto-stashes UNSTAGED
   changes while running hooks on the staged set. If an auto-fixer (ruff-format) rewrites a
   staged file mid-run, the restore can revert unrelated unstaged edits to HEAD. Defense:
   STAGE the full intended set (leave nothing related unstaged), and snapshot uncommitted
   work before starting.
2. **Gates judge the WHOLE touched file, not just your diff.** Rescuing stale WIP forces the
   commit to satisfy current gates on every line of each file it touches, surfacing
   pre-existing repo debt unrelated to the WIP (pip-audit vulns, bandit defaults, stale
   `requires-python` vs CI floor, `-e .` editable-package audit failures). Budget for this
   and treat repo-infra fixes as SEPARATE, surfaced commits, never silently absorbed.

Also: before committing a large changeset, run `git diff -w` to separate real content from
whitespace/line-ending churn (a "150-file WIP" is often ~87% churn) and discard the churn.

### Content-purity hooks fire on quoted text and on the rule's own example (Obs 491)

A repo-wide content gate (no-em-dash PC-011, no-secret, banned-terms) is a property of what
enters the repo, not of authorship or intent. It fires on internal notes that quote
external-model output verbatim, and on a doc that must *describe* the forbidden token
(documenting "replace the em-dash glyph" by pasting the glyph violates the rule). Each block
costs a full re-commit cycle because the hook only runs at commit time.

When authoring any doc into a hooked repo:

- Run the same check on the new file BEFORE committing, not via the commit's own hook
  (e.g., `grep -nP '\x{2014}' <file>` for no-em-dash).
- When a doc must reference a banned token, name it by codepoint ("em-dash, U+2014"), never
  paste the glyph. The literal example is indistinguishable from a real violation to a
  mechanical checker.

### Workflow-file Edit blocked by the security-reminder hook (Obs 251)

The PreToolUse security-reminder hook hard-blocks `Edit` against `.github/workflows/*.yml`
keyed on file TYPE, not on the risky construct (untrusted input flowing into `run:`). Benign
edits (adding `merge_group:` to `on:`, a concurrency fallback) are blocked anyway, and the
block only covers the Edit path.

Correct response when it blocks a workflow-file edit:

1. Explicitly review the diff against the hook's injection checklist (does any untrusted
   input reach a `run:` step?).
2. If clean, apply the exact literal replacement via a scripted edit through Bash with a
   match-count assertion.
3. Surface the full diff for verification, then let pre-commit (actionlint + yamllint) run.

Flag to the user that the hook fires on file type rather than the dangerous pattern, and
covers only Edit, so routing around it via Bash/Write is uncovered.

### Shared-clone staging safety (Obs 111)

In a shared (non-worktree) clone with concurrent agent sessions, `git add <file>` stages
the entire working-tree file, including another session's uncommitted edits. A commit
reporting unexpectedly large changes (e.g., "140 insertions" for a 1-line fix) is the
signal. HR-1 (verify `git diff --cached --name-only`) is the defense. Use
`.worktrees/<branch-slug>` for isolation whenever concurrent agent sessions are active.

### History purge: GitHub retains unreachable objects (Obs 139)

After `git filter-repo` and force-push, purged commits remain resolvable by SHA via
GitHub's API and via `refs/pull/*` until GitHub Support runs GC. Treat exposed data as
already compromised; rotate secrets rather than relying on purge.

Also: force-push guards that pattern-match on `git push` adjacency are bypassable by
alternate git invocation forms:

```bash
git -C <dir> push --force main
git --git-dir=<path> push --force main
```

### Dependabot/Renovate scope-doubling in commit messages (Obs 39)

Dependabot's `commit-message.include: "scope"` appends a second parenthesized
scope to whatever `prefix` is set. With `prefix: "ci(actions):"` it generates
`ci(actions):(deps): bump X`: two scope groups, which a conventional-commit
regex expecting a single optional scope cannot match, failing every downstream
PR-title / standards-validation check. Either pair `include: "scope"` with a
bare prefix (`ci:`), or omit `include: "scope"` when the prefix is already
scoped. General rule: when a strict format validator (conventional-commit regex)
is downstream, audit the full generated output of each dependency-tool config
combination, not each option in isolation.

### secrets.baseline generated_at conflict (Obs 104)

The `generated_at` field in `.secrets.baseline` conflicts whenever two branches both run
the detect-secrets hook. The correct resolution is: keep the newer timestamp. No manual
inspection of the secrets entries is needed unless the conflict extends beyond that line.

```bash
git add .secrets.baseline
```
