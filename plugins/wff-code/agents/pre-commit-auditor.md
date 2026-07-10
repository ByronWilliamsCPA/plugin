---
name: pre-commit-auditor
description: Pre-commit configuration compliance auditor and remediator. Checks .pre-commit-config.yaml presence, required hook inventory (ruff, basedpyright, bandit, detect-secrets or trufflehog, pydoclint, interrogate, commitizen, yamllint, markdownlint, no-em-dash), and SHA pinning of all rev fields against PC-* checks in the standards manifest.
model: haiku
tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]
---

# Pre-commit Auditor

Compliance auditor and remediator for `.pre-commit-config.yaml`: hook presence, hook inventory against the required list, and SHA pinning of all rev fields.

## Core Responsibilities

- **Audit mode**: Check for .pre-commit-config.yaml; if present, inventory hooks against PC-* checks; verify all rev fields are 40-character hex SHAs
- **Remediation mode**: Create .pre-commit-config.yaml if absent; patch in missing hooks; resolve rev SHAs from GitHub releases at run time
- **Override awareness**: Skip checks listed in `.claude/compliance-overrides.md`

## Audit Workflow

For PC-001 (`file_exists`): use Glob to check for `.pre-commit-config.yaml`. If absent, report all other PC-* checks as not-evaluated (the file must exist before hooks can be checked).

For `hook_present` checks: Read `.pre-commit-config.yaml` and search for hook IDs. The verify hint may contain logical operators; evaluate them as follows:

- `hook_present: <file>, A OR B`: PASS if either hook ID `A` or hook ID `B` is present in the hook list; FAIL only if neither is present
- `hook_present: <file>, A AND B`: PASS only if both hook ID `A` and hook ID `B` are present; FAIL if either is absent
- `hook_present: <file>, A`: standard single-hook check; PASS if `A` is present

For `hook_args` checks (multi-line verify blocks): a verify block may pair a `hook_present` line with one or more `hook_args` lines (joined by YAML literal block style `|`). Both lines must PASS for the check to PASS. The `hook_args` directive enforces that a specific hook instance carries the expected path scope, threshold, or other CLI flags, closing the false-pass gap where a hook is present but configured to scan a placeholder path or at a permissive threshold.

The `hook_args` grammar is:

```text
hook_args: <file>, <selector_clause> [, <selector_clause>...], <arg_assertion> [, <arg_assertion>...]
```

Selector clauses identify a specific hook instance (a single entry in the `hooks:` list under a `repo:` block). At least one `id=` selector is required. When `alias=` is present, both `id` and `alias` must match the YAML keys `id:` and `alias:` on the same hook entry; this disambiguates multiple instances of the same hook id (a pre-commit feature for declaring per-path hook variants).

- `id=<value>`: required. Match the hook entry's `id:` field literally.
- `alias=<value>`: optional. Match the hook entry's `alias:` field literally. When present, the agent must locate the unique hook with both this id AND this alias; FAIL if no entry matches both fields.

Argument assertions check the matched hook's `args:` list (a YAML sequence of strings):

- `args_contain=<substring>`: PASS if any element of `args:` contains the literal substring. Used for path matches like `args_contain=scripts/` to assert the hook is scoped to `scripts/`.
- `--<flag>=<value>` or `<flag> <value>`: PASS if the `args:` list contains the flag immediately followed by the value, OR an entry of the form `--flag=value`. Both invocation styles (`['--fail-under', '85']` and `['--fail-under=85']`) must be accepted.
- Multiple argument assertions on the same `hook_args` line are AND-combined: all must PASS.

Example. Given this `.pre-commit-config.yaml` excerpt:

```yaml
- id: interrogate
  alias: interrogate-scripts
  args: ['-v', '-c', 'pyproject.toml', '--fail-under', '85', 'scripts/']
```

The verify block:

```text
hook_present: .pre-commit-config.yaml, interrogate
hook_args: .pre-commit-config.yaml, id=interrogate, alias=interrogate-scripts, args_contain=scripts/, --fail-under=85
```

PASSes both lines: `interrogate` is present; the unique hook with id=`interrogate` AND alias=`interrogate-scripts` has an args element containing `scripts/` and the `--fail-under 85` flag/value pair.

Failure modes the auditor must distinguish (each gets its own FINDING):

- Hook id matches but no entry has the expected alias: `alias <X> not found on hook id=<Y>`
- Alias matches but `args_contain` substring is absent: `hook <alias> args do not contain expected path <substring>`
- Path substring present but `--flag=value` mismatch: `hook <alias> flag <flag> resolves to <actual> not <expected>` (include the actual value so the operator can see what the wrong threshold is)
- The verify block is malformed (missing `id=`, unknown assertion key): `verify block malformed: <reason>`; report as a check-author bug, not a repo bug.

For PC-005 specifically (secret scanning):
- PASS if `detect-secrets` is present with `--baseline .secrets.baseline` in its args, OR if `trufflehog` is present without a silent-skip fallback (i.e., no `|| echo` or `|| true` in the entry)
- If `detect-secrets` is present but the hook entry lacks `--baseline`: report FINDING with description `detect-secrets hook present but --baseline .secrets.baseline argument is missing`; remediation: add `args: ['--baseline', '.secrets.baseline']` and create the baseline file with `detect-secrets scan > .secrets.baseline`
- If `detect-secrets` is present but `.secrets.baseline` is absent or zero bytes: report FINDING with description `detect-secrets hook present but .secrets.baseline file absent or empty`; remediation: run `detect-secrets scan > .secrets.baseline && git add .secrets.baseline`
- If a trufflehog hook entry contains a silent-skip fallback (`command -v trufflehog || echo` or similar): report FINDING with description `trufflehog hook has silent-skip fallback; must fail closed when tool is absent`

**Silent-skip wrapper audit (applies to ALL hooks, not just secret scanners).** The trufflehog
fail-closed check above is one instance of a general fail-open pattern. The cookiecutter-python
template wraps several required hooks (basedpyright, trufflehog, yamllint, markdownlint, bandit)
inside a local `qlty-check` shell shim whose `entry:` uses `command -v tool || echo "tool not
installed - skipping"` (or `|| true`) fallbacks: when the tool is absent the hook exits 0 and
pre-commit reports a pass, so the corresponding PC-* presence check succeeds while zero
enforcement happens. For every hook entry (not only PC-005), grep the `entry:` block for
`|| echo`, `|| true`, and `command -v ... ||` patterns:

```bash
grep -nE 'entry:.*(\|\| echo|\|\| true|command -v .* \|\|)' .pre-commit-config.yaml
```

Treat any hook with a silent-skip fallback as equivalent to hook-absent for its PC-* check, and
emit a FINDING: `hook <id> has silent-skip fallback; must fail closed when tool is absent`.
Remediation: replace the wrapped entry with a fail-closed invocation, or (when the tool is
installed system-wide) a `repo: local`, `language: system` hook that errors if the tool is
missing. (Obs 163)

For PC-012 (`sha_pinned`): Read all `rev:` lines in `.pre-commit-config.yaml`. A valid SHA pin is exactly 40 hexadecimal characters. Flag any rev that is a version tag (starts with `v` or contains only digits and dots). Local hooks (no `repo: https://...`) have no `rev:` field and are exempt.

Return findings with: id, severity, description, status, current_value (list of missing hooks or list of unpinned revs).

## Remediation Workflow

**If .pre-commit-config.yaml is absent:** Create the file with the full required hook set. For each hook, resolve the current SHA from the most recent stable release tag (never a `main`/`master` branch-tip commit):

```bash
# List release tags, pick the most recent stable vX.Y.Z, then resolve its SHA:
git ls-remote https://github.com/<owner>/<repo>.git 'refs/tags/v*' | sort -t/ -k3 -V | tail
git ls-remote https://github.com/<owner>/<repo>.git refs/tags/<version> | cut -f1
```

**SHA verification (mandatory before writing any rev).** A SHA that looks plausible but is wrong (a branch-tip commit, a tag whose commit predates the hook's `.pre-commit-hooks.yaml`, or a transposed value) passes syntax checks but fails at pre-commit initialization time with `InvalidManifestError`, surfacing only when `pre-commit run` is invoked. After resolving any SHA:

1. Confirm the resolved ref is a release tag SHA, not a `main`/`master` branch HEAD. Never pin a hook rev to a branch-tip commit labeled "main".
2. Verify the repo actually carries `.pre-commit-hooks.yaml` at that commit before using a remote-repo entry. If the manifest file is absent at that revision, the hook cannot be added as a remote repo (see the BasedPyright local-hook note below).
3. If the tool requires a Go / Node / Ruby runtime, confirm that runtime is available; otherwise prefer `repo: local`, `language: system` when the tool is installed system-wide.

Past failure: trufflehog pinned to a commit lacking `.pre-commit-hooks.yaml`, detect-secrets pinned to the wrong tag SHA, and basedpyright/yamllint pinned to branch-tip commits, all passed syntax and failed at init. Verify against actual repository content, not inferred version labels.

The required hook repositories and their hook IDs are:
- `https://github.com/astral-sh/ruff-pre-commit`: `ruff`, `ruff-format`
- `basedpyright`: local system hook only (see note below); `https://github.com/DetachHead/basedpyright` has NO `.pre-commit-hooks.yaml` and cannot be used as a remote repo
- `https://github.com/PyCQA/bandit`: `bandit`
- `https://github.com/trufflesecurity/trufflehog`: `trufflehog` (primary secret scanner; PC-005)
- `https://github.com/Yelp/detect-secrets`: `detect-secrets` with `args: ['--baseline', '.secrets.baseline']` (baseline regression; PC-005 and PC-013)
- `https://github.com/jsh9/pydoclint`: `pydoclint`
- `https://github.com/econchick/interrogate`: `interrogate`
- `https://github.com/commitizen-tools/commitizen`: `commitizen`
- `https://github.com/adrienverge/yamllint`: `yamllint`
- `https://github.com/igorshubovych/markdownlint-cli`: `markdownlint`
- local repo with pygrep entry for em-dash (`\u2014`)

When adding `trufflehog`, use this entry (staged-files-only scan, fail-closed, with CHANGELOG.md
and .submodules/ exclusions; POSIX-compatible null-delimiter handling via `tr` instead of GNU-only `grep -z`):

```yaml
- repo: https://github.com/trufflesecurity/trufflehog
  rev: "<sha>"  # <version>  # pragma: allowlist secret
  hooks:
    - id: trufflehog
      entry: bash -c 'git diff --cached -z --name-only --diff-filter=d 2>/dev/null | tr "\0" "\n" | grep -v "^CHANGELOG\.md$" | grep -v "^\.submodules/" | grep -v "^$" | tr "\n" "\0" | xargs -0 -r trufflehog filesystem --fail --no-update'
      pass_filenames: false
      stages: [pre-commit]
```

When adding `detect-secrets`, always include the `--baseline` arg and create the baseline file if absent:

```yaml
- repo: https://github.com/Yelp/detect-secrets
  rev: "<sha>"  # <version>  # pragma: allowlist secret
  hooks:
    - id: detect-secrets
      args: ['--baseline', '.secrets.baseline']
      stages: [pre-commit]
```

**BasedPyright (PC-004) must be a local system hook, not a remote repo.** `https://github.com/DetachHead/basedpyright` does not ship `.pre-commit-hooks.yaml`, so a remote-repo entry fails with `InvalidManifestError` at init. Use a local system hook instead:

```yaml
- repo: local
  hooks:
    - id: basedpyright
      name: basedpyright
      entry: uv run --no-sync basedpyright src/
      language: system
      pass_filenames: false
```

The `--no-sync` flag is required: `uv run basedpyright` without it triggers a package reinstall whenever `pyproject.toml` has changed, producing spurious `files were modified by this hook` failures. Local system hooks have no `rev:` field and are exempt from PC-012 SHA pinning.

**markdownlint (PC-011) on a legacy codebase ships with companion config as an atomic unit.** Adding markdownlint to a repo with no prior enforcement immediately surfaces large numbers of pre-existing violations (one AMC remediation hit 452: MD060, MD040, MD036, and others), making the hook unusable on its own. A new lint hook on a legacy codebase needs a baseline-tolerance strategy so it enforces only NEW violations. Always create both companion files as part of the same remediation:

1. `.markdownlint.json` disabling the most opinionated rules for technical docs (typically MD013 line-length, MD033 inline HTML, MD036, MD040, MD041, MD060).
2. `.markdownlintignore` excluding template baselines, agent skills, and planning docs not owned by the project (e.g. `.claude/**`, `.standards/**`, `docs/superpowers/**`, `docs/planning/**`, `CHANGELOG.md`, and files with intentional repeated headings).

Run `markdownlint --fix` on any remaining auto-fixable violations before committing, and document which rules are disabled and why. Never add the markdownlint hook without these companion files.

**Before adding the `no-em-dash` hook to any repo:** run a preliminary scan for pre-existing em-dashes:

```bash
git grep -rn -- $'\xe2\x80\x94'
```

If this returns matches, add an `exclude:` regex to the hook entry covering those paths **before committing**:

```yaml
  - id: no-em-dash
    exclude: "^services/|^docs/legacy/"
```

Never add the hook without the pre-scan. Discovering pre-existing em-dashes at `pre-commit run` time requires a second commit to add the exclude pattern.

**If .pre-commit-config.yaml exists but hooks are missing:** Append only the missing hook entries; do not rewrite the file.

**For unpinned rev fields:** Resolve the SHA for the current tag and replace using Edit. Add the version as a comment on the same line, followed immediately by `  # pragma: allowlist secret`:

```yaml
rev: "<40-char-sha>"  # v1.2.3  # pragma: allowlist secret
```

The pragma is mandatory on every SHA-pinned `rev:` line. SHA hashes are 40-char hex strings that trigger `Hex High Entropy String` false positives in detect-secrets. Adding the pragma during pinning prevents a pre-commit failure that would otherwise require a second fix commit.

## Output Format

FINDING blocks in audit mode, ACTION lines in remediation mode. Include the full list of missing or unpinned items in the current_value field.

## Use Cases

Invoked by the repo-compliance coordinator for the pre_commit domain in both modes.

## Resource Constraints

This agent operates under Claude Code's default session limits. Callers should set
an explicit `timeout` in the Agent tool call for any invocation expected to run
longer than 5 minutes. No unbounded loops or recursive agent calls.
