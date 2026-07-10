# Conventional Commits Reference

Single source of truth for commit types, usage, and version impact.

## Type Reference

| Type | When to Use | Example | Version Impact |
|------|-------------|---------|----------------|
| `feat` | New feature for the user | `feat: add user authentication` | Minor (0.X.0) |
| `fix` | Bug fix for the user | `fix: resolve null pointer in parser` | Patch (0.0.X) |
| `docs` | Documentation changes only | `docs: update API reference` | No release |
| `refactor` | Code restructuring, no behavior change | `refactor: extract validation logic` | No release |
| `test` | Adding or fixing tests | `test: add unit tests for auth` | No release |
| `perf` | Performance improvement | `perf: optimize database queries` | Patch (0.0.X) |
| `chore` | Maintenance, dependency updates | `chore: update dependencies` | No release |
| `ci` | CI/CD configuration changes | `ci: add caching to workflow` | No release |
| `style` | Formatting, whitespace (no logic change) | `style: fix indentation` | No release |

## Breaking Changes

Append `!` to any type to indicate a breaking change. This triggers a Major version bump.

```text
feat!: redesign authentication API
fix!: remove deprecated endpoint
```

Always include a `BREAKING CHANGE:` footer explaining the migration path:

```text
feat(api)!: change response envelope format

BREAKING CHANGE: API responses now use { data, meta, errors }
envelope instead of flat response. Clients must update parsing.

Migration: Update response handlers to access .data property.
```

## Format Rules

```text
<type>(<scope>): <subject>

<body>

<footer>
```

- **Subject**: imperative mood ("add" not "added"), max 50 chars, no trailing period
- **Scope**: optional, component name in parentheses — `feat(auth):`, `fix(parser):`
- **Body**: wrap at 72 chars, explain *what* and *why* (not how)
- **Footer**: `BREAKING CHANGE:`, `Closes #123`, `Co-Authored-By:`
