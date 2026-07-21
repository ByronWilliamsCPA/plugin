# PR Preparation Workflow

Full pull request description generation workflow.

## Activation

Triggers on: prepare PR, prepare the PR, prepare a PR, create PR, create pull request,
PR description, pull request description, ready for PR, ready to PR, draft PR, write PR

## Workflow

### 0. Confirm CI gates are green

#### 0a. Fetch and freshness check

```bash
git fetch origin
BEHIND=$(git rev-list --count HEAD..origin/main)
if [ "$BEHIND" -gt 0 ]; then
  echo "Branch is $BEHIND commit(s) behind origin. Rebase before continuing."
  git rebase origin/main
fi
```

If rebase produces conflicts, stop here. Resolve conflicts and re-run `/git pr`.

#### 0b. CI gate

Before creating the PR, confirm `/ci-fix` has been run and all gates are green. If not,
run it now:

```text
/ci-fix
```

Do not proceed with PR creation until all blockers are resolved. pip-audit findings
should be documented in the PR description if they cannot be resolved immediately.

### 1. Gather Context

```bash
# Current state
git status

# Commits on this branch vs main
git log $(git merge-base HEAD main)..HEAD --oneline

# Files changed
git diff $(git merge-base HEAD main)..HEAD --stat

# Actual diff (for smaller changes)
git diff $(git merge-base HEAD main)..HEAD
```

> If the base branch is not `main`, substitute the correct base (e.g., `develop`).

### 1b. Self-review

Before writing the description, scan the diff for common problems:

```bash
git diff $(git merge-base HEAD main)..HEAD
```

Check for:

- Debugging artifacts: `print()`, `console.log()`, `debugger`, `.only`, `TODO: remove`
- Committed secrets: API keys, tokens, passwords, private keys
- Unintended file changes: lock files with unexpected diffs, generated files, IDE config
- Incomplete work: `raise NotImplementedError`, `pass`, empty function bodies meant as stubs

If any of these are found, stop and ask the user to address them before continuing.

### 2. Analyze Changes

Identify:

- **Components modified**: Which files/modules changed
- **Purpose**: Why these changes were made
- **Impact**: Benefits, risks, breaking changes
- **Testing**: What validation was done or needed
- **Size**: Count total lines changed (`git diff $(git merge-base HEAD main)..HEAD --stat |
  tail -1`). If > 500 lines, consider whether the PR can be split. Recommend a split when
  changes span unrelated concerns (for example, a feature addition combined with a
  large refactor or documentation overhaul).

### 3. Generate PR Description

Use this template:

```markdown
## Summary

[1-3 sentences: what changed and why]

## Why

[Motivation. What problem does this solve, or what opportunity does it capture?
Link to the issue, ticket, or decision that drove this work.]

## Changes

- **[Component]**: [What changed and why]
- **[Component]**: [What changed and why]

## Impact

- ✅ [Key benefit or outcome]
- ✅ [Another benefit]
- ✅ No breaking changes

## Acceptance Criteria

- [ ] [Observable behaviour that confirms this works correctly]
- [ ] [Edge case or boundary condition that must hold]

## Migration and Rollback

[Required only for schema changes, API changes, config changes, or anything that
affects deployed state. Describe the migration steps and how to roll back if needed.
Omit this section for pure code changes with no deployment side-effects.]

## Testing

- [ ] Tests pass (`uv run pytest`)
- [ ] Format passes (`uv run ruff format --check`)
- [ ] Linting passes (`uv run ruff check`)
- [ ] Type checking passes (`uv run basedpyright`)

## Notes

[Optional: known issues, follow-up work, pip-audit findings that cannot be resolved
immediately, or other context reviewers should know.]
```

### 4. Suggest PR Title

Follow conventional commits format (see `context/conventional-commits.md`):

| Type | When to Use |
| ---- | ----------- |
| `feat:` | New feature |
| `fix:` | Bug fix |
| `docs:` | Documentation only |
| `refactor:` | Code restructuring |
| `test:` | Adding tests |
| `perf:` | Performance improvement |
| `chore:` | Maintenance, dependencies |

### 5. Create the PR

Use the `/git pr` skill to push and create the PR. This keeps the workflow consistent with
the documented path and ensures all PR safeguards are applied:

```text
/git pr
```

The skill handles `git push -u origin HEAD` and `gh pr create` with the correct title and
body generated in the steps above.

**Share the PR URL with the user immediately** after `gh pr create` returns it. Do not
wait for the review in Step 6 to complete before showing the URL.

### 6. Run automated code review

After `gh pr create` succeeds, present the PR URL and recommend the user run the
review in a **new session**:

```text
PR created: <PR URL>

Run the automated review in a new session to get the best results:
  /pr-review <PR URL>

Starting a fresh session before review has two benefits:
- Lower cost: review agents start with a cold cache instead of inheriting the
  accumulated cache-write overhead from this implementation session.
- Unbiased evaluation: review agents have not seen the reasoning and trade-offs
  from this session, so they challenge assumptions independently rather than
  anchoring on decisions already made here.
```

Do NOT invoke `/pr-review` in the current session. Hand off the PR URL and let
the user start a new session to trigger the review.

---

## Multi-PR merge under strict org rulesets (Obs 269)

Merging a backlog of PRs into a branch governed by `strict_required_status_checks_policy=true`
(plus required signatures, linear history, Copilot review) is inherently SERIAL: each merge
invalidates every other PR's up-to-date status, so only one PR can be up-to-date at a time.
Most "stuck" auto-merges are not CI failures but invisible gates. Run this loop, one PR at a
time:

1. **Re-sync immediately before merge.** `gh pr merge --auto` plus update-branch is the
   efficient loop, but the PR must be up-to-date against the latest base at merge time.
2. **Apply skip labels BEFORE the synchronize push.** A label only takes effect if
   present before the push that triggers the workflows. Applying it after requires an empty
   commit to re-trigger; a bare label event does not re-run `pull_request` workflows.
3. **Dismiss stale bot reviews.** A `coderabbit`/Copilot review left in CHANGES_REQUESTED
   blocks merge even with `required_approving_review_count=0`. Dismiss it explicitly.
4. **Push with an explicit refspec.** `git push` with `push.default=simple` silently refuses
   when the local branch name differs from upstream; use `git push origin HEAD:<remote-branch>`.
5. **Re-fetch before every conflict resolution.** Local `origin/main` goes stale across a
   long session of server-side merges; re-fetch or the PR re-conflicts (BEHIND/DIRTY) after
   you push.
6. **Diff the merged file vs base to verify semantic correctness.** A textual auto-merge can
   be semantically wrong. Conflict-resolution heuristic: for files already changed by merged
   PRs take the base branch's version (never revert merged work); keep the PR's version only
   for files unique to it; union additive doc sections (e.g., a reference index or catalog).

Verify the actual gate state (`gh pr view <n> --json mergeStateStatus,statusCheckRollup`)
rather than waiting on a never-reported required context.

---

## Example Interaction

**User**: "Can you prepare the PR for this branch?"

1. Run git commands to gather context
2. Analyze the changes
3. Output:

---

**Suggested Title**: `feat: add user authentication with OAuth2`

**PR Description**:

```markdown
## Summary

Add OAuth2 authentication supporting Google and GitHub providers.

## Why

Users currently have no SSO option, requiring manual password management. This
unblocks the enterprise customer pilot that requires SSO. Tracks #142.

## Changes

- **auth/oauth.py**: OAuth2 client implementation with token refresh
- **api/routes/auth.py**: Login, logout, and callback endpoints
- **models/user.py**: User model with OAuth provider fields

## Impact

- ✅ Users can sign in with Google or GitHub
- ✅ Secure session management with httponly cookies
- ✅ No breaking changes to existing API

## Acceptance Criteria

- [ ] Clicking "Sign in with Google" redirects and returns a valid session
- [ ] Expired tokens refresh automatically without user action

## Testing

- [x] Tests pass (`uv run pytest`)
- [x] Format passes (`uv run ruff format --check`)
- [x] Linting passes (`uv run ruff check`)
- [x] Type checking passes (`uv run basedpyright`)

## Notes

Follow-up: Add Microsoft provider support
```

---

Ready to copy! Create the PR using the `/git pr` skill:

```bash
/git pr
```
