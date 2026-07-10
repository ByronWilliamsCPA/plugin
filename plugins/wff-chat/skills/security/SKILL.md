---
description: Security validation — GPG/SSH key validation, dependency scanning, and encryption. Triggers on "security, scan, audit".
tools: ["Read", "Bash", "Grep", "Glob"]
---

# Security Skill

Security validation, vulnerability scanning, and compliance checking.

## Invocation

```text
/security [scope]
```

**Scope** (optional): `all` (default), `env`, `scan`, `deps`

## Activation

Auto-activates on keywords: security, vulnerability, audit, OWASP, encryption, GPG, SSH, signing, secrets, scan, bandit

## Workflows

### Environment Validation
- **workflows/validate-env.md**: GPG/SSH key validation

### Scanning
- **workflows/scan.md**: Security vulnerability scanning

### Encryption
- **workflows/encrypt.md**: Secret encryption and management

## Workflow

Execute in this order for a full `/security all` run:

**Step 1 — Environment validation** (`/security env`)
```bash
gpg --list-secret-keys
ssh-add -l
git config --get user.signingkey
```

**Step 2 — Code scanning** (`/security scan`)
```bash
uv run bandit -r src/ -c pyproject.toml
uv run semgrep scan --config auto src/
```

**Step 3 — Dependency audit** (`/security deps`)
```bash
uv run pip-audit
```

CVE suppression: pip-audit (2.10.0) does NOT read a `[tool.pip-audit]` section from
pyproject.toml (Obs 79). A `[tool.pip-audit]` block with `ignore-vulns` is documentation
only and has no functional effect. The only working suppression is the `--ignore-vuln ID`
CLI flag:

```bash
uv run pip-audit --ignore-vuln PYSEC-2022-42969
```

If a task or doc claims pyproject config will suppress a CVE, treat it as a no-op and move
the ID to the invocation command. Before writing any `[tool.<name>]` block, confirm the
tool actually reads it; many such sections are documentation only.

**Step 3a: Enumerate every package ecosystem** (Obs 190)

Dependabot scans every ecosystem present in the repo, so its alerts are NOT equivalent to
the primary-language audit tool. In a polyglot repo, `pip-audit` cannot see the npm, cargo,
or go trees, and a single audit command gives a false sense of completeness. Before
triaging:

1. Enumerate every ecosystem present (pip, npm, cargo, go, etc.).
2. Run that ecosystem's audit tool for each (pip -> `pip-audit`, npm -> `npm audit`, ...).
3. Group host alerts (Dependabot) by the ecosystem of the flagged package, then choose the
   remediation tool per group. Never map an alert to the project's primary language by
   default. Reconcile the host's aggregated list against the union of per-ecosystem tools.

**Step 3b: Python-gated security floors** (Obs 117)

When a security fix needs a newer Python than the project's `requires-python` floor, do not
abandon the bump. A blanket floor (e.g. `urllib3>=2.7.0`) makes `uv lock` unsatisfiable
against an old floor; backing it out leaves the real runtime vulnerable. Add the floor with
an environment marker matching the fix's minimum Python:

```text
urllib3>=2.7.0 ; python_full_version >= '3.10'
```

uv then patches the real runtime while keeping a compatible fallback for the old floor.
Verify which Python actually runs (check `pyvenv.cfg`) to confirm the runtime gets the fix,
then document the older-Python fallback as a residual in `docs/known-vulnerabilities.md`.
A `requires-python` floor is often aspirational, not the deployment target; check the real
runtime before declaring a Python-gated CVE unfixable.

**Step 4 — Secrets detection**
```bash
gitleaks detect --source .
trufflehog filesystem .
```

## Security Checklist

### Pre-Commit
- [ ] No secrets in code (checked by gitleaks)
- [ ] Dependencies scanned for vulnerabilities
- [ ] Bandit security scan passes

### Pre-Release
- [ ] All known vulnerabilities addressed
- [ ] Security advisory published (if applicable)
- [ ] Dependencies updated to secure versions

### Exposed Service Audit (paired port + auth check, Obs 63)

Port binding and authentication are two independent controls; both must be present. Auditors
tend to check one or the other, which misses the case where auth middleware is configured
but the port is still host-bound directly. For every exposed port, run the paired check:

| Port binding (127.0.0.1-prefixed or absent) | Auth middleware (e.g. Traefik labels) | Severity |
| --- | --- | --- |
| Missing (bound to all interfaces) | Missing | HIGH |
| One of the two present | The other missing | MEDIUM |
| Both present | Both present | OK |

Check the Traefik labels block AND the port binding format together in the same pass; a
README calling auth "optional" is not a substitute for the binding being scoped.

## OWASP Top 10 Considerations

1. **Injection**: Use parameterized queries, validate input
2. **Broken Authentication**: Use secure session management
3. **Sensitive Data Exposure**: Encrypt sensitive data at rest and in transit
4. **XML External Entities**: Disable external entity processing
5. **Broken Access Control**: Implement proper authorization checks
6. **Security Misconfiguration**: Use secure defaults
7. **XSS**: Escape output, use Content Security Policy
8. **Insecure Deserialization**: Validate and sanitize serialized data
9. **Using Components with Known Vulnerabilities**: Keep dependencies updated
10. **Insufficient Logging**: Log security events, monitor for anomalies

## Common Rationalizations

The reasons a control gets skipped, and why each one is how incidents start. When an audit
hears the left column, the right column is the response.

| Rationalization | Reality |
| --- | --- |
| "It is internal-only, so it is safe" | Internal networks get breached. Defense in depth assumes the perimeter fails. |
| "We will add auth later" | "Later" ships to production. Add the control before the port is exposed, not after. |
| "No one would think to attack this" | Attackers automate discovery. Obscurity is not a control. |
| "The library handles security for us" | Libraries handle the cases you configure. Misconfiguration is the top cause of breaches. |
| "pip-audit is noisy, I will suppress it" | Suppression without a documented entry (see CLAUDE.md > Unfixed CVEs) is how known CVEs reach production. |
