# Branch Strategy Reference

Branch naming conventions and semantic release mapping.

## Branch Type Mapping

| Branch Prefix | Commit Type | Version Impact | Use Case |
|---------------|-------------|----------------|----------|
| `feat/` | `feat:` | Minor (0.X.0) | New features |
| `fix/` | `fix:` | Patch (0.0.X) | Bug fixes |
| `docs/` | `docs:` | No release | Documentation |
| `refactor/` | `refactor:` | No release | Code restructuring |
| `perf/` | `perf:` | Patch (0.0.X) | Performance improvements |
| `test/` | `test:` | No release | Test additions |
| `chore/` | `chore:` | No release | Maintenance |
| `hotfix/` | `fix:` | Patch (0.0.X) | Critical production fixes |

## Branch Naming Format

```text
{type}/{descriptive-slug}
```

### Rules

- **Lowercase only**: `feat/user-auth` not `feat/User-Auth`
- **Hyphens**: `feat/add-login-page` not `feat/add_login_page`
- **Descriptive but concise**: `feat/oauth-google` not `feat/add-oauth-integration-with-google-identity-provider`
- **No ticket numbers alone**: `feat/auth-ABC-123` acceptable; `ABC-123` alone is not

### Good Examples

```bash
feat/user-authentication
fix/null-pointer-api
docs/installation-guide
refactor/database-queries
perf/image-optimization
hotfix/critical-security-patch
```

### Bad Examples

```bash
feature/UserAuthentication  # Wrong prefix, wrong case
fix_null_pointer            # Underscores, no prefix
docs/update                 # Too vague
ABC-123                     # Ticket number only
```

## Protected Branches

Never commit directly to: `main`, `master`, `develop`

Always create a feature branch first:

```bash
git checkout main && git pull origin main
git checkout -b feat/{descriptive-slug}
```

## Validation Check

```bash
CURRENT_BRANCH=$(git branch --show-current)
if [[ "$CURRENT_BRANCH" == "main" || "$CURRENT_BRANCH" == "master" || "$CURRENT_BRANCH" == "develop" ]]; then
    echo "ERROR: Cannot work directly on $CURRENT_BRANCH. Create a feature branch first."
    exit 1
fi
```
