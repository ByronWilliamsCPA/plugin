---
name: pre-commit-authoring
description: >
  Pre-commit hook authoring and audit reference. Use when adding a new
  pre-commit hook, auditing an existing `.pre-commit-config.yaml`, or
  diagnosing hook misbehavior (false positives, slow commits, hooks that
  block on unrelated files). Captures the staged-scope invariant, fast/slow
  tier placement, fail-vs-warn semantics, and a common-gotchas list.
  Auto-activates on: add a hook, write a pre-commit hook, audit pre-commit,
  fix pre-commit hook, why is this hook slow, hook false positive,
  /pre-commit-authoring.
user-invocable: true
---

# Pre-Commit Hook Authoring

Reference for designing, adding, and auditing entries in
`.pre-commit-config.yaml`. Internal skill: assumes the user's existing
toolchain (ruff, basedpyright, yamllint, markdownlint, TruffleHog,
detect-secrets, interrogate, pydoclint, qlty, pip-audit). The principles
generalize; the specific hook examples reference this fleet's standards.

## Authoring decision tree

Before adding any hook, answer in order:

1. **Does the check belong at commit time at all?** Pre-commit hooks fire on
   every commit and add latency to every developer's flow. If the check is
   slow (more than ~10 seconds on a typical change, matching the
   file-scoped-linter tier budget below), runs against state the developer
   cannot see (full git history, remote artifacts, network resources), or
   only matters at PR/release time, put it in CI instead.
2. **Pre-commit or pre-push?** Use `pre-commit` for fast checks against the
   diff. Use `pre-push` for slower checks that must run before the change
   leaves the developer's machine but can amortise across many commits
   (e.g., `pip-audit`, full-test sweeps, full-history secret scans). Set
   `stages: [pre-commit]` or `stages: [pre-push]` explicitly; do not rely
   on the default.
3. **Does the hook scope to staged files only?** See PC-HOOK-STAGED-SCOPE
   invariant below. Hooks that traverse the local git object store will
   surface findings from unmerged remote branches.

## Scope invariant (most-violated rule)

**Pre-commit hooks must scope to staged files only.** Full-git-history
modes belong in CI, not pre-commit.

The local git object store almost always contains commits from fetched
remote branches that are not reachable from `HEAD` (e.g.,
`origin/feature-x`, abandoned `claude/...` branches, dependabot PRs).
Hooks that scan the full history will surface placeholder credentials,
test fixtures, and known-fake examples from those branches on every
unrelated commit, blocking work indefinitely.

| Tool | Wrong (full history) | Right (staged) |
|---|---|---|
| TruffleHog | `trufflehog git file://. --since-commit HEAD` | `git diff --cached -z --diff-filter=d --name-only \| xargs -0 -r trufflehog filesystem` |
| gitleaks | `gitleaks detect --log-opts="--all"` | `gitleaks git --staged` (gitleaks v8.19+; older versions use `gitleaks protect --staged`) |
| detect-secrets | `detect-secrets scan --baseline .secrets.baseline` (regenerates from full repo) | `git diff --cached -z --diff-filter=d --name-only \| xargs -0 -r detect-secrets-hook --baseline .secrets.baseline` |

The `-z` / `-0` pair handles filenames with spaces; `--diff-filter=d`
excludes deleted files. `xargs -r` prevents the tool from running on an
empty input when no files match.

If full-history scanning is genuinely desired (a periodic audit, a
release-time gate), move the check to a CI workflow where the runner
clones with controlled remote refs.

## Performance tier placement

Group hooks into tiers so commits stay fast:

- **Fast file checks (every commit, target <2s):** trailing whitespace,
  end-of-file fixer, check-yaml, check-json, mixed-line-ending,
  check-added-large-files. These pre-existing pre-commit-hooks repo
  utilities are cheap and catch high-frequency mistakes early.
- **File-scoped linters (every commit, target <10s):** ruff, basedpyright
  (strict), yamllint, markdownlint, detect-private-key, no-em-dash. Scope
  to staged files only.
- **Slower checks (pre-commit if budget allows, else pre-push):**
  TruffleHog (staged form), interrogate, pydoclint, bandit on changed
  files, qlty check.
- **Pre-push only (full sweeps):** `pip-audit` on dependency files,
  `pre-commit run --all-files`, `pytest -x`, full-history secret scans
  if any.

Set `stages: [pre-commit]` or `stages: [pre-push]` explicitly on every
hook to control when it runs. Use
`default_install_hook_types: [pre-commit, pre-push]` separately so
`pre-commit install` registers both git-hook scripts in `.git/hooks`;
the `stages:` value on each hook still selects the actual stage.

## Fail-vs-warn semantics

- **Fail (exit non-zero, blocks commit):** correctness checks (lint,
  type, secrets, syntax). Fix the underlying issue before committing;
  `--no-verify` is only permitted when the user has explicitly requested
  it for a specific commit.
- **Warn (exit zero, prints output):** informational checks (TODO
  inventory, complexity reports, coverage trends). Most check tools
  default to fail; use `verbose: true` in the hook config to surface
  output without blocking.

Never set a correctness check to warn-only "to unblock the team": the
absence of a fail is the absence of the check.

## Hook config invariants in this project

The `.claude/rules/pre-commit.md` file (path-scoped) hosts the project's
codified invariants. Cross-reference when adding a new hook:

- **PC-YAMLLINT-FILE-REF:** yamllint must use `--config-file .yamllint`,
  not inline `-d "{rules: ...}"`.
- **PC-MARKDOWNLINT-MD040:** markdownlint must run with a config that
  enables MD040 (fenced-code-blocks-language).
- **PC-HOOK-STAGED-SCOPE:** every secret-scanning, lint, or content-check
  hook must scope to staged files only.

Add a new `PC-*` invariant whenever a hook authoring decision must be
preserved across the fleet (e.g., a specific arg flag, a config-file
location, a stage assignment that prevents a known failure mode).

## Authoring checklist

Before merging a PR that adds or modifies a hook:

- [ ] Hook is pinned to a SHA in the `rev:` field, not a mutable tag
- [ ] `stages:` is explicit (`[pre-commit]` or `[pre-push]`)
- [ ] Scope is staged files (no full-history flags)
- [ ] Config is in a file (`--config <path>`) not inline (`-d "..."`)
- [ ] Hook entry tested via `pre-commit run <hook-id> --all-files` and
      `pre-commit run <hook-id>` against a small staged change
- [ ] Failure output is actionable (the developer can tell what to fix)
- [ ] If new failure modes are introduced, an invariant is documented in
      `.claude/rules/pre-commit.md`

## Audit pattern

For an existing `.pre-commit-config.yaml`:

```bash
# 1. Find unpinned hooks (mutable refs)
grep -n 'rev: v\|rev: main\|rev: master' .pre-commit-config.yaml

# 2. Find hooks that scan full history
grep -nE '(--since-commit|--all|--log-opts|git file://)' .pre-commit-config.yaml

# 3. Find hooks without explicit stages
awk '/^  - id:/{name=$3; have_stage=0} /stages:/{have_stage=1} /^  - id:/{if(name && !have_stage) print prev_name" missing stages"} {prev_name=name}' .pre-commit-config.yaml

# 4. Find inline configs that should be file-ref
grep -nE 'args:.*-d ' .pre-commit-config.yaml

# 5. Find silent-skip wrappers that make a hook a no-op
grep -nE 'entry:.*(\|\| echo|\|\| true|command -v .* \|\|)' .pre-commit-config.yaml

# 6. Coverage check: run a hook and confirm it does NOT print "(no files to
#    check) Skipped" for the paths it is meant to govern. Presence in the
#    config is not enforcement; a chronically-skipped hook is a silent pass.
pre-commit run <hook-id> --all-files
```

Patch any findings against the invariants above before committing the audit fix.

## Common gotchas

- **TruffleHog `git file://. --since-commit HEAD`** scans every commit not
  reachable from HEAD, including fetched remote branches. Always use the
  staged-file form.
- **detect-secrets baseline regenerated from full repo** can include
  secrets from old branches. Regenerate against staged files or a clean
  clone in CI.
- **`pip-audit` at pre-commit** is too slow for every commit. Move to
  pre-push or limit to dependency-file changes via `files:` filter.
- **`pre-commit run --all-files` inside a hook entry** creates infinite
  recursion. Use `pre-commit run` against staged paths only.
- **Hook order matters when one fixes and another checks the result.**
  Ruff format must run before ruff check; whitespace fixers must run
  before linters that fail on trailing whitespace.
- **`pass_filenames: false` hooks that rglob a directory tree** (e.g. a
  cookiecutter-shipped `validate-front-matter` with `files: ^docs/` that then
  walks the whole `docs/` tree) violate the staged-scope invariant twice: they
  validate files never staged, and they do not respect `.gitignore`. A
  one-line docs change then fails on a pre-existing template defect or on
  local-only gitignored notes. Directory-walking validators must derive their
  file list from `git ls-files` (which already skips gitignored paths), not
  from the filesystem. When such a hook blocks an unrelated commit, first ask
  "did this fail before my change?" via `git log -- <flagged-file>` before
  fixing; the defect usually predates your commit. (Obs 264; see the Scope
  invariant section.)
- **Inline `#` comment on a backslash-continued shell line silently
  truncates the command.** A line inside a YAML `run:` block or `.sh` file
  that ends with `\` meant as a continuation, but carries a mid-line `#`
  comment before it, has its backslash consumed by the comment, terminating
  the command early (e.g. an image-pin sweep appended
  `# 6-alpine as of 2026-05-28 \` to a `docker run` line and broke five
  workflows for 12 days). The pattern is mechanical and greppable
  (`#[^\n]*\\$`); flag it on `.sh` files and workflow `run:` blocks as a
  candidate hook. Any bulk sweep that appends text to existing line endings
  needs a post-pass syntax check (`bash -n` on reconstructed run blocks),
  because the failure is silent until runtime. Never append an inline comment
  to a line that ends in a continuation backslash. (Obs 285)
- **Silent-skip wrappers turn any hook into a no-op, not just TruffleHog.**
  A hook whose `entry:` wraps the tool in `command -v tool || echo "skipping"`,
  `|| true`, or any fallback that exits 0 when the tool is absent provides zero
  enforcement while passing all presence checks. The cookiecutter-python
  template ships this pattern around a local `qlty-check` shim covering
  basedpyright, trufflehog, yamllint, markdownlint, and bandit. Generalize the
  detection beyond secret scanners: grep every `entry:` block for `|| echo`,
  `|| true`, and `command -v ... ||`, and treat any silent-skip wrapper as
  equivalent to hook-absent. A fail-open wrapper is the absence of the check.
  (Obs 163)
- **Inline suppression pragmas must survive the auto-formatter.** Directives
  like `# pragma: allowlist secret`, `# noqa: CODE`, and `# type: ignore` are
  line-anchored: they only suppress the token on the same physical line. When
  the suppressed statement is long enough that ruff-format (or black) wraps it
  across lines, the pragma is carried to a different physical line and silently
  stops working, surfacing as a confusing "files were modified by this hook" or
  baseline-updated failure rather than an obvious error. When suppressing a
  finding on a wrap-prone line, restructure so the token and its pragma fit on
  one sub-width line (e.g. assign the literal to a short-named constant first,
  then operate on the constant). Run the formatter BEFORE relying on the pragma.
  (Obs 183)
- **A hook that matches zero files is a silent pass, indistinguishable from a
  real validation pass.** When pre-commit prints `(no files to check) Skipped`
  for a hook, that hook enforced nothing on this commit; if its `files:` /
  `types:` filter chronically excludes the paths where the rule matters (e.g.
  a `no-em-dash` hook whose regex omits `.claude/skills/.*\.md` and
  `.claude/agents/.*\.md`, the exact directories where skill/agent prose lives),
  the rule "exists" and CI is green while violations ship. For any rule
  classified as a hard rule, audit coverage, not presence: confirm the hook
  actually matched at least one file in the paths it is meant to govern, and
  broaden the `files:` regex when it does not. (Obs 71)

## Sources

- pre-commit framework: <https://pre-commit.com/>
- TruffleHog pre-commit guidance: <https://docs.trufflesecurity.com/pre-commit-hooks>
- Cross-cutting principle 2 in `~/.claude/skill-observations/cross-cutting-principles.md`
  (procedural git rules, including the no-bypass-on-`--no-verify` rule)
