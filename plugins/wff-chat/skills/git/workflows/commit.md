# Commit Workflow

Full conventional commit preparation workflow.

## Activation

Triggers on: commit, prepare commit, commit this, commit message, write commit,
stage and commit, commit changes, what should I commit, ready to commit

## Workflow

### 1. Gather Context

```bash
# See all changes
git status

# Staged changes (what will be committed)
git diff --cached --stat
git diff --cached

# Unstaged changes (won't be committed yet)
git diff --stat
```

### 2. Analyze Changes

Determine:

- **Type**: feat, fix, docs, refactor, test, chore, perf, ci
- **Scope**: Which component/module is affected (optional)
- **Breaking**: Are there breaking changes?
- **What**: What was changed
- **Why**: Why was it changed (if not obvious)

### 3. Generate Commit Message

Follow conventional commits format:

```text
<type>(<scope>): <subject>

<body>

<footer>
```

#### Type Reference

| Type | When to Use | Example |
| ---- | ----------- | ------- |
| `feat` | New feature | `feat: add user authentication` |
| `fix` | Bug fix | `fix: resolve null pointer in parser` |
| `docs` | Documentation only | `docs: update API reference` |
| `refactor` | Code restructuring | `refactor: extract validation logic` |
| `test` | Adding/fixing tests | `test: add unit tests for auth` |
| `perf` | Performance improvement | `perf: optimize database queries` |
| `chore` | Maintenance, deps | `chore: update dependencies` |
| `ci` | CI/CD changes | `ci: add caching to workflow` |
| `style` | Formatting only | `style: fix indentation` |

See `context/conventional-commits.md` for version impact per type.

#### Rules

- **Subject**: Imperative mood ("add" not "added"), no period, max 50 chars
- **Body**: Wrap at 72 chars, explain what and why (not how)
- **Footer**: Breaking changes, issue references

### 4. Handle Staging

If there are unstaged changes, ask:

- "Stage specific files?" (list files and let user choose; **preferred default**)
- "Review changes first?" (show diff, then offer file-by-file staging)
- "Stage all changes?" (`git add .`): use only when the user explicitly asks
  for this; note that `git add .` can accidentally include secrets, generated
  files, or IDE config that should not be committed

### 5. Execute Commit

After user confirms the message, always use HEREDOC for multi-line commits. Commits must be signed (`-S`):

```bash
git commit -S -m "$(cat <<'EOF'
feat: add user authentication

Implement OAuth2 flow with Google and GitHub providers.
Includes session management with secure cookies.

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

### 5b. Guard against formatter-daemon drift (Obs 428)

In an IDE-attached or daemon-watched workspace, an editor formatter (Ruff LSP, Prettier on
save) can rewrite staged files on disk AFTER `git add`, so the staged blob and working tree
diverge and the commit captures a torn version. The working tree is not frozen at `git add`
time when a formatter daemon watches it.

A file appearing in BOTH the staged and unstaged lists is the signal, not a mistake to
ignore. Before committing:

```bash
# Run the project formatter once to canonical form, then re-stage
git add <intended paths>
git diff --name-only -- <intended paths>   # MUST be empty (staged == working)
```

If that diff is non-empty, re-run the formatter, re-stage, and confirm stability before
committing.

### 6. Post-Commit

After successful commit:

- Show `git log -1` to confirm
- Suggest `git push` if ready
- Mention if more changes remain unstaged

---

## Breaking Changes

Use `!` after type and add `BREAKING CHANGE:` footer:

```text
feat(api)!: change response envelope format

BREAKING CHANGE: API responses now use { data, meta, errors }
envelope instead of flat response. Clients must update parsing.

Migration: Update response handlers to access .data property.
```

---

## Multiple Logical Changes

If staged changes touch multiple unrelated areas, recommend splitting:

> I see changes to multiple unrelated areas:
>
> 1. Bug fix in `parser.py`
> 2. New feature in `export.py`
> 3. Updated docs
>
> Recommend splitting into separate commits:
>
> 1. `fix(parser): handle empty input gracefully`
> 2. `feat(export): add CSV export option`
> 3. `docs: update export documentation`
>
> Want me to help stage and commit each separately?

---

## Attribution

Always include Claude attribution for AI-assisted commits:

```text
🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Safety Rules

- **NEVER** use `git commit --amend` on pushed commits
- **NEVER** skip hooks with `--no-verify` unless explicitly asked by the user
- **ALWAYS** sign commits with `-S` (`git commit -S`)
- **ALWAYS** show the commit message before executing
- **CHECK** staged files for secrets/credentials before committing
- **WARN** about large binary files in the staged set

---

## Example Interactions

### Simple Commit

**User**: "commit these changes"

```bash
git status
git diff --cached
```

Looking at your staged changes:

- Modified `src/auth/oauth.py`: added token refresh logic
- Modified `tests/test_auth.py`: added refresh tests

**Suggested commit**:

```text
feat(auth): add OAuth token refresh

Implement automatic token refresh when access token expires.
Includes retry logic with exponential backoff.
```

Shall I commit with this message?

---

### Breaking Change

**User**: "ready to commit"

I see you've changed the API response format. This is a breaking change.

**Suggested commit**:

```text
feat(api)!: change response envelope format

BREAKING CHANGE: API responses now use { data, meta, errors }
envelope instead of flat response. Clients must update parsing.

Migration: Update response handlers to access .data property.
```

This marks it as a breaking change with `!`. Proceed?

---

### Example: Multiple Logical Changes

**User**: "commit this"

I see changes to multiple unrelated areas:

1. Bug fix in `parser.py`
2. New feature in `export.py`
3. Updated docs

Recommend splitting into 3 separate commits. Want me to help stage and commit each separately?
