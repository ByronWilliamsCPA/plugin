---
name: using-git-worktrees
description: Use when starting feature work that needs isolation from current workspace or before executing implementation plans - creates isolated git worktrees with smart directory selection and safety verification
---

# Using Git Worktrees

## Overview

Git worktrees create isolated workspaces sharing the same repository, allowing work on multiple branches simultaneously without switching.

**Core principle:** Systematic directory selection + safety verification = reliable isolation.

**Announce at start:** "I'm using the using-git-worktrees skill to set up an isolated workspace."

## Directory Selection Process

Follow this priority order:

### 1. Check Existing Directories

```bash
# Check in priority order
ls -d .worktrees 2>/dev/null     # Preferred (hidden)
ls -d worktrees 2>/dev/null      # Alternative
```

**If found:** Use that directory. If both exist, `.worktrees` wins.

### 2. Check CLAUDE.md

```bash
grep -i "worktree.*director" CLAUDE.md 2>/dev/null
```

**If preference specified:** Use it without asking.

### 3. Ask User

If no directory exists and no CLAUDE.md preference:

```
No worktree directory found. Where should I create worktrees?

1. .worktrees/ (project-local, hidden)
2. ~/.config/superpowers/worktrees/<project-name>/ (global location)

Which would you prefer?
```

## Safety Verification

### For Project-Local Directories (.worktrees or worktrees)

**MUST verify directory is ignored before creating worktree:**

```bash
# Check if directory is ignored (respects local, global, and system gitignore)
git check-ignore -q .worktrees 2>/dev/null || git check-ignore -q worktrees 2>/dev/null
```

**If NOT ignored:**

Per Jesse's rule "Fix broken things immediately":
1. Add appropriate line to .gitignore
2. Commit the change
3. Proceed with worktree creation

**Why critical:** Prevents accidentally committing worktree contents to repository.

### For Global Directory (~/.config/superpowers/worktrees)

No .gitignore verification needed - outside project entirely.

## Creation Steps

### 1. Detect Project Name

```bash
project=$(basename "$(git rev-parse --show-toplevel)")
```

### 2. Create Worktree

```bash
# Determine full path
case $LOCATION in
  .worktrees|worktrees)
    path="$LOCATION/$BRANCH_NAME"
    ;;
  ~/.config/superpowers/worktrees/*)
    path="~/.config/superpowers/worktrees/$project/$BRANCH_NAME"
    ;;
esac

# Create worktree with new branch
git worktree add "$path" -b "$BRANCH_NAME"
cd "$path"
```

### 3. Run Project Setup

Auto-detect and run appropriate setup:

```bash
# Node.js
if [ -f package.json ]; then npm install; fi

# Rust
if [ -f Cargo.toml ]; then cargo build; fi

# Python (uv)
if [ -f uv.lock ] || grep -q "\[tool.uv\]" pyproject.toml 2>/dev/null; then
    unset VIRTUAL_ENV   # prevents uv from targeting the parent worktree's venv
    uv sync --extra dev 2>/dev/null || uv sync --all-extras
fi

# Python (poetry / pip)
if [ -f requirements.txt ] && [ ! -f uv.lock ]; then pip install -r requirements.txt; fi
if [ -f pyproject.toml ] && [ ! -f uv.lock ] && grep -q "^\[tool.poetry\]" pyproject.toml 2>/dev/null; then
    poetry install
fi

# Go
if [ -f go.mod ]; then go mod download; fi
```

### 4. Verify Clean Baseline

Run tests to ensure worktree starts clean:

```bash
# Examples - use project-appropriate command
npm test
cargo test
pytest
go test ./...
```

**If tests fail:** Report failures, ask whether to proceed or investigate.

**If tests pass:** Report ready.

### 5. Report Location

```
Worktree ready at <full-path>
Tests passing (<N> tests, 0 failures)
Ready to implement <feature-name>
```

## Recovery: When Local State Vanishes Mid-Session (Obs 287)

In a repo with multiple concurrent actors (your terminals, parallel agent sessions,
cleanup automation), a worktree, its branch, or the main checkout's branch can disappear
underneath an active session, and `main` can jump forward several commits. The first
instinct is data loss and reconstruction from context. That instinct is usually wrong and
reconstructing blindly produces a duplicate PR of already-merged work.

**Rule: before re-applying anything, fetch and check the remote for the in-flight work.**

```bash
git fetch origin
# Inspect recent integration-target commits for your work, matched by SUBJECT + content,
# not by branch name (the branch may already be cleaned up):
git log origin/main --oneline -20
git show origin/main -- <files you were editing>   # did your exact edits already land?
```

If the edits are present on `origin/main` (committed, PR'd, merged, branch pruned by a
parallel actor), the work landed: do NOT reconstruct or re-open a PR. Confirm the match
and report that the work is already integrated. Only reconstruct if the remote shows the
work genuinely absent.

**Principle:** Disappearance of local state in a multi-actor repo is as likely to mean
"work landed" as "work lost." Verify the remote before reconstructing.

## When the deliverables are gitignored (Obs 446, 457)

A git worktree isolates version-controlled state only. When the work product is gitignored
(generated data, model outputs, build artifacts, report markdown in a code-only repo), a
fresh worktree branched from HEAD is EMPTY of those artifacts, and "merge back" is not a git
merge at all. Classify what is tracked vs ignored FIRST, not as an afterthought:

```bash
git check-ignore <candidate deliverable paths>   # which work product is ignored
```

Then handle the gitignored work explicitly:

- **Provision inputs one-way.** Copy required gitignored inputs from the source tree into the
  new worktree before anything will run; a fresh checkout does not have them.
- **Validate by reproduction, not by diff.** Verify against the source-of-truth by re-running
  and reproducing the authoritative numbers, not by diffing files (the files are not tracked,
  so there is nothing to diff). A guard/test that depends on gitignored runtime artifacts
  cannot do a live end-to-end run inside a bare worktree: either root-parametrize the tool (a
  `--root` flag) and bridge the real artifacts via a gitignored symlink, or run the live
  check in the original checkout that physically holds the artifacts. Reserve build-time unit
  tests (synthetic fixtures) for inside the worktree; reserve the live check for where the
  state lives. Decide this BEFORE isolating, not after.
- **Treat merge-back as two moves.** A git merge for the few tracked code/doc files, plus a
  plain file-copy for the gitignored deliverables. Coordinate writes when another session
  owns the target tree.

## Target the correct worktree path when multiple are active (Obs 700)

The Read and Edit tools operate on absolute filesystem paths and have no awareness of
which git branch a path belongs to. When the main checkout and a child worktree both
contain the same file, the project-root path silently refers to the MAIN branch, not the
PR branch you are working on. An Edit aimed at the project root lands on the wrong branch.

Before applying any Edit or Write to a file that exists in both the main checkout and a
child worktree:

1. Confirm which branch is checked out at the project root: `git branch --show-current`.
2. If the target branch lives in a child worktree, build the absolute path with the
   `.worktrees/<slug>/` prefix, e.g.
   `/home/byron/dev/<project>/.worktrees/<slug>/<path>`. Never use the project-root path
   for an edit targeting a child worktree's branch.
3. If a stray edit already landed on the main checkout, recover by verifying the worktree
   file is still unedited, applying the edit to the correct absolute path, then reverting
   the main checkout with `git checkout -- <file>`.

Explicit absolute paths carrying the worktree slug are the only safe way to target a
specific branch's files.

## `git stash` does not restore index-only changes (`git rm --cached`) on pop (Obs 697)

`git stash` saves and restores the WORKING TREE reliably, but pure-index operations lose
their staged status on pop. `git rm --cached` removes a file from the index without
touching the working tree; on `stash pop`, git applies the index diff against HEAD, and
because the files are unchanged on disk the rm-cached delta is dropped and the files
revert to tracked. The staged deletions silently disappear, and a commit made afterward
misses the intended index cleanup.

So do NOT use `git stash` to temporarily suspend staged changes when those changes
include `git rm --cached`. When you need to test pre-existing hook behavior in that state:

- Run `pre-commit run <hook-id> --all-files` directly without stashing; hooks run on all
  files regardless of staged state.
- Or use a separate worktree on main to test baseline behavior without touching the
  working branch's staged index.
- Or use `git stash --keep-index` if the goal is only to stash unstaged changes and leave
  the staged index intact.

## Multi-session isolation: a worktree per actor (Obs 466)

The git index and working tree are per-worktree global state, not per-process. Any workflow
that runs multiple concurrent committers against ONE working tree will interleave and lose
work. When more than one agent/session operates on the same repo concurrently, each MUST work
in its own `git worktree` (separate index and working dir, shared object store). Sharing one
working tree corrupts staging across sessions because the index is global.

Symptoms that signal a shared-tree race:

- `git add -A` from another session sweeping your staged files into an unrelated commit.
- pre-commit "files were modified by this hook" from a whole-project hook running while
  another session edits files mid-hook.
- HEAD moving unexpectedly between your commands (verify via `git reflog`).

Isolation (a worktree per actor) is a precondition for safe parallel commits, not an
optimization.

## Worktree-aware reversible dedup of duplicate clones (Obs 175)

Local clone "duplicates" (a hyphen and an underscore copy of the same project) are rarely
clean copies; the directory name is cosmetic and the remote is usually identical for both.
Let the work-bearing clone win, and treat dedup as a worktree-aware, reversible procedure:

1. **Compare both clones fully:** remote, branches, unpushed commits, stashes, uncommitted
   state, AND enumerate registered worktrees (`git worktree list`). A "lean" clone can hold
   registered worktrees with their own feature branches; a "bloated" one can hold unpushed
   commits and large uncommitted diffs.
2. **Preserve with `git bundle`, not `git push`.** `git bundle create --all` is local,
   lossless across all refs INCLUDING worktree branches, fully reversible, and has zero
   outward side effects (no recreated branches, no CI). Prefer it to pushing `[gone]`/merged
   branches, which would recreate deleted branches and retrigger CI. Also capture per-worktree
   `git diff HEAD` patches, archived `git ls-files --others --exclude-standard` untracked
   files, and stash patches. Then `git bundle verify` and confirm the load-bearing commit is
   inside the bundle before any `rm`.
3. **Delete the redundant clone only after** the verified bundle contains its unique commits.
4. **On rename, repair worktrees explicitly.** A bare `git worktree repair` does NOT fix
   moved worktrees; pass the NEW worktree paths so it rewrites both the admin gitdir and the
   worktree `.git` file, then verify each worktree resolves HEAD. A renamed clone's `.venv`
   also has stale absolute paths needing `uv sync`.

Note: `git log --branches --not --remotes` OVERCOUNTS "unpushed" because squash-merged-then-
deleted branches show upstream `[gone]` and their commits are not on origin/main.

## Quick Reference

| Situation | Action |
|-----------|--------|
| `.worktrees/` exists | Use it (verify ignored) |
| Concurrent agent sessions on one repo | One worktree per actor; shared index races and loses work |
| Deliverables are gitignored | Classify tracked-vs-ignored first; provision inputs, validate by reproduction, merge back in two moves |
| Live verification needs gitignored artifacts | Root-parametrize + symlink, or run the check in the original checkout |
| `worktrees/` exists | Use it (verify ignored) |
| Both exist | Use `.worktrees/` |
| Neither exists | Check CLAUDE.md → Ask user |
| Directory not ignored | Add to .gitignore + commit |
| Tests fail during baseline | Report failures + ask |
| No package.json/Cargo.toml | Skip dependency install |
| Worktree/branch vanished mid-session | `git fetch`; check origin/main for the work before reconstructing |

## Common Mistakes

### Skipping ignore verification

- **Problem:** Worktree contents get tracked, pollute git status
- **Fix:** Always use `git check-ignore` before creating project-local worktree

### Assuming directory location

- **Problem:** Creates inconsistency, violates project conventions
- **Fix:** Follow priority: existing > CLAUDE.md > ask

### Proceeding with failing tests

- **Problem:** Can't distinguish new bugs from pre-existing issues
- **Fix:** Report failures, get explicit permission to proceed

### Hardcoding setup commands

- **Problem:** Breaks on projects using different tools
- **Fix:** Auto-detect from project files (package.json, etc.)

### Reconstructing vanished work without checking the remote

- **Problem:** A worktree/branch deleted by a parallel actor usually means the work merged; blind reconstruction creates a duplicate PR
- **Fix:** `git fetch` and match your edits against origin/main by subject + content before re-applying anything

### Additional common mistakes

| Mistake | Problem | Fix |
|---------|---------|-----|
| Inheriting parent VIRTUAL_ENV | uv targets the parent worktree's venv, installing into the wrong environment | `unset VIRTUAL_ENV` before `uv sync` in a new worktree |
| Missing dev extras | `uv sync` installs only runtime deps; `uv run pytest` fails with ModuleNotFoundError | Always run `uv sync --extra dev` or `--all-extras` for worktrees used for testing |

## Example Workflow

```
You: I'm using the using-git-worktrees skill to set up an isolated workspace.

[Check .worktrees/ - exists]
[Verify ignored - git check-ignore confirms .worktrees/ is ignored]
[Create worktree: git worktree add .worktrees/auth -b feature/auth]
[Run npm install]
[Run npm test - 47 passing]

Worktree ready at /Users/jesse/myproject/.worktrees/auth
Tests passing (47 tests, 0 failures)
Ready to implement auth feature
```

## Red Flags

**Never:**
- Create worktree without verifying it's ignored (project-local)
- Skip baseline test verification
- Proceed with failing tests without asking
- Assume directory location when ambiguous
- Skip CLAUDE.md check
- Reconstruct vanished work before checking origin/main for it

**Always:**
- Follow directory priority: existing > CLAUDE.md > ask
- Verify directory is ignored for project-local
- Auto-detect and run project setup
- Verify clean test baseline
- On unexpected loss of local state, fetch and check the remote first

## Integration

**Called by:**
- **brainstorming** (Phase 4) - REQUIRED when design is approved and implementation follows
- **subagent-driven-development** - REQUIRED before executing any tasks
- **executing-plans** - REQUIRED before executing any tasks
- Any skill needing isolated workspace

**Pairs with:**
- **finishing-a-development-branch** - REQUIRED for cleanup after work complete
