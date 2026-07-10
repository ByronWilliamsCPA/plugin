---
name: ast-grep
user-invocable: true
description: >
  Structural code search and multi-file refactoring with ast-grep. Use for
  structural search, structural refactor, ast-grep, find a code pattern,
  rewrite a call signature, codemod, or any task targeting a code shape rather
  than a literal string. Prefer over Grep plus Edit when the query is
  syntactic, not textual.
tools: ["Bash", "Read", "Glob"]
---

# ast-grep Reference

Structural search and rewrite across codebases. Always invoke as `ast-grep`,
not `sg`: shadow-utils ships its own `sg` command (a `newgrp` wrapper) that
shadows it.

## When to use ast-grep vs Grep

| Need | Tool |
| --- | --- |
| Find all calls to `foo(...)` regardless of formatting | ast-grep |
| Rename a function parameter across a codebase | ast-grep |
| Match a decorator, import shape, or class definition | ast-grep |
| Search prose, config values, or comment text | Grep |
| Find a literal string in any file type | Grep |

Rule of thumb: if the query describes a code structure, use ast-grep. If it
describes a substring that could appear anywhere, use Grep.

## Core syntax

### Meta-variables

- `$X` matches exactly one syntax node (an identifier, expression, or
  statement). The same name binds consistently in one pattern: `$X + $X`
  matches `a + a` but not `a + b`.
- `$$$` matches zero or more nodes (variadic). Use inside argument lists,
  block bodies, or import lists where the count is unknown.
- `$_` is an anonymous single-node wildcard (does not bind a name).

### Essential flags

| Flag | Short | Purpose |
| --- | --- | --- |
| `--lang <lang>` | `-l` | Set language: `bash`, `python`, `js`, `ts`, `rust`, `go`, etc. |
| `--pattern <pat>` | `-p` | Inline pattern (quoted) |
| `--rewrite <template>` | `-r` | Replacement template using the same meta-variables |
| `--json` | | Machine-readable output (one JSON object per match) |
| `--interactive` | `-i` | Confirm each rewrite before applying |

Always specify `--lang` when the file extension is ambiguous or when searching
a mixed directory.

## Recipes

### Find every `command -v <tool>` guard in shell scripts

```bash
ast-grep --lang bash --pattern 'command -v $X' scripts/
```

### Find all Python decorator applications

```bash
ast-grep --lang python --pattern '@$DECORATOR
def $FUNC($$$):
    $$$' src/
```

### Rewrite a function call (rename argument keyword)

```bash
ast-grep --lang python \
  --pattern 'connect(host=$HOST, port=$PORT)' \
  --rewrite 'connect(address=$HOST, port=$PORT)' \
  --interactive src/
```

### Find all TypeScript `useState` calls and emit JSON for downstream tooling

```bash
ast-grep --lang ts --pattern 'useState($$$)' --json src/
```

### Find bare `except:` clauses in Python

```bash
ast-grep --lang python --pattern 'try:
    $$$
except:
    $$$' src/
```

## YAML rule files

For relational rules (match a node only when it appears inside, or contains,
another node), write a YAML rule file and pass it with `--rule`:

```yaml
# find-bare-except.yaml
id: bare-except
language: python
rule:
  pattern: |
    try:
        $$$
    except:
        $$$
  inside:
    kind: function_definition
message: Bare except inside a function -- add a specific exception type.
severity: warning
```

```bash
ast-grep --rule find-bare-except.yaml src/
```

Key relational operators: `inside` (ancestor match), `has` (descendant match),
`follows` (sibling after), `precedes` (sibling before). Combine with `all`,
`any`, and `not` for compound conditions.

## Notes

- ast-grep respects `.gitignore` by default. Pass `--no-ignore` to override.
- For large codebases, `--json` plus `jq` is faster than interactive mode for
  counting or filtering matches before committing to a rewrite.
- `--rewrite` does not modify files unless you also pass `--update-all` (or
  confirm interactively). Dry-run is the default.
