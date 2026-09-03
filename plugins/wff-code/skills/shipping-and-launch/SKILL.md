---
name: shipping-and-launch
description: Prepare production launches safely. Use when preparing to deploy to production, when you need a pre-launch checklist, when setting up monitoring, when planning a staged rollout, or when you need a rollback strategy. Triggers on ship, launch, deploy, rollout, canary, feature flag, rollback, pre-launch checklist, staged rollout, go-live.
---

# Shipping and Launch

> **Ported skill.** Adapted from [`addyosmani/agent-skills`](https://github.com/addyosmani/agent-skills/blob/main/skills/shipping-and-launch/SKILL.md)
> (MIT License), commit `a5f0b17`, retrieved 2026-06-18. Adapted to our standards:
> em-dashes removed, upstream `references/` pointers replaced with cross-references to
> our skills, and a post-deploy verification loop added (converges with gstack
> `/land-and-deploy`). Examples are illustrative; the rollout discipline is
> stack-agnostic. For orchestration, hand execution to the
> `devops-deployment-agent`.

## Overview

Ship with confidence. The goal is not just to deploy; it is to deploy safely, with
monitoring in place, a rollback plan ready, and a clear understanding of what success
looks like. Every launch should be reversible, observable, and incremental.

## When to Use

- Deploying a feature to production for the first time
- Releasing a significant change to users
- Migrating data or infrastructure
- Opening a beta or early access program
- Any deployment that carries risk (all of them)

## The Pre-Launch Checklist

### Code Quality

- [ ] All tests pass (unit, integration, e2e); run `/testing` and `/ci-fix`
- [ ] Build succeeds with no warnings
- [ ] Lint and type checking pass (`/quality`: Ruff + BasedPyright)
- [ ] Code reviewed and approved (`/pr-review` for production/OSS, `/code-review` for solo)
- [ ] No TODO comments that should be resolved before launch
- [ ] No stray debug print/log statements in production code
- [ ] Error handling covers expected failure modes

### Security

- [ ] No secrets in code or version control
- [ ] `uv run pip-audit` shows no critical or high vulnerabilities (run the `/security` skill)
- [ ] Input validation on all user-facing endpoints
- [ ] Authentication and authorization checks in place
- [ ] Security headers configured (CSP, HSTS, etc.)
- [ ] Rate limiting on authentication endpoints, with the configured limit recorded (`OPS-011`)
- [ ] CORS configured to specific origins (not wildcard)
- [ ] Application data-store role is not the table owner and does not hold BYPASSRLS (`OPS-002`)
- [ ] Row-level security, if claimed, passes a two-direction test (`OPS-003`)
- [ ] Logs redact secrets, proven by a test rather than by the filter's presence (`OPS-004`)
- [ ] Public write paths (signup, password reset, contact forms) carry an anti-automation control (`OPS-009`)
- [ ] Runtime secrets come from a secret manager, not a baked-in `.env` (`OPS-010`)

### Performance

- [ ] Core Web Vitals within "Good" thresholds (see `performance-optimization`)
- [ ] No N+1 queries in critical paths
- [ ] Images optimized (compression, responsive sizes, lazy loading)
- [ ] Bundle size within budget
- [ ] Database queries have appropriate indexes
- [ ] Caching configured for static assets and repeated queries

### Observability

- [ ] Feature is instrumented (see `observability-and-instrumentation`)
- [ ] On-call questions for this feature are answerable from telemetry
- [ ] Logging and error reporting configured
- [ ] Symptom-based alerts created and test-fired
- [ ] Security events emitted against a documented taxonomy: authn failure, authz denial, rate-limit trip, input-validation reject (`OPS-005`)
- [ ] Security alerts are committed as rules, name their destination channel, and carry a recorded test-fire timestamp (`OPS-006`)

### Accessibility

- [ ] Keyboard navigation works for all interactive elements
- [ ] Screen reader can convey page content and structure
- [ ] Color contrast meets WCAG 2.1 AA (4.5:1 for text)
- [ ] Focus management correct for modals and dynamic content
- [ ] Error messages are descriptive and associated with form fields
- [ ] No accessibility warnings in axe-core or Lighthouse

### Infrastructure

- [ ] Environment variables set in production, and attested in a dated runtime-config document (`OPS-001`)
- [ ] Database migrations applied (or ready to apply)
- [ ] DNS and SSL configured
- [ ] CDN configured for static assets
- [ ] Health check endpoint exists and responds
- [ ] Backups inventoried with schedule, retention, and destination (`OPS-007`)
- [ ] A restore drill has actually been performed and logged; a configured backup is not a tested one (`OPS-008`)
- [ ] Managed-service console settings are committed AND pushed by a workflow, not just committed (`OPS-012`)

> **`OPS-*` references above point to the `operations` domain in
> `docs/standards-manifest.yaml`.** This checklist is the human-facing narrative
> for a single deploy; the manifest checks are the durable half that lands in the
> master log, gets delta caching, fleet escalation at the 3-repo threshold, and
> staleness detection. Use both. A checkbox ticked here leaves no record; an
> `OPS-*` finding does.
>
> The manifest checks are deliberately harder to satisfy than a checkbox: each
> names a durable artifact rather than a state of the world. "Backups are
> configured" ticks a box; `OPS-008` wants a dated restore-drill log entry.

### Documentation

- [ ] README updated with any new setup requirements
- [ ] API documentation current
- [ ] ADRs written for any architectural decisions
- [ ] Release commits are Conventional so semantic-release generates the CHANGELOG at release (OpenSSF release gate; do not hand-edit CHANGELOG.md)
- [ ] User-facing documentation updated (if applicable)

## Feature Flag Strategy

Ship behind feature flags to decouple deployment from release:

```typescript
const flags = await getFeatureFlags(userId);
if (flags.taskSharing) {
  return <TaskSharingPanel task={task} />;  // new feature
}
return null;                                 // default: existing behavior
```

**Feature flag lifecycle:**

```text
1. DEPLOY with flag OFF     -> Code is in production but inactive
2. ENABLE for team/beta     -> Internal testing in production environment
3. GRADUAL ROLLOUT          -> 5% -> 25% -> 50% -> 100% of users
4. MONITOR at each stage    -> Watch error rates, performance, user feedback
5. CLEAN UP                 -> Remove flag and dead code path after full rollout
```

**Rules:**

- Every feature flag has an owner and an expiration date
- Clean up flags within 2 weeks of full rollout (see `deprecation-and-migration`)
- Do not nest feature flags (creates exponential combinations)
- Test both flag states (on and off) in CI

## Staged Rollout

```text
1. DEPLOY to staging       -> full test suite + manual smoke test of critical flows
2. DEPLOY to prod (flag OFF) -> verify deploy (health check), no new errors
3. ENABLE for team         -> internal users in prod, 24-hour monitoring window
4. CANARY (flag ON, 5%)    -> compare canary vs baseline, 24-48h window, advance only if green
5. GRADUAL (25 -> 50 -> 100%) -> same monitoring at each step, can roll back to prior %
6. FULL rollout            -> monitor 1 week, then clean up the flag
```

### Rollout Decision Thresholds

Use these thresholds to decide whether to advance, hold, or roll back at each stage:

| Metric | Advance (green) | Hold and investigate (yellow) | Roll back (red) |
|--------|-----------------|-------------------------------|-----------------|
| Error rate | Within 10% of baseline | 10-100% above baseline | >2x baseline |
| P95 latency | Within 20% of baseline | 20-50% above baseline | >50% above baseline |
| Client JS errors | No new error types | New errors at <0.1% of sessions | New errors at >0.1% of sessions |
| Business metrics | Neutral or positive | Decline <5% (may be noise) | Decline >5% |

### When to Roll Back

Roll back immediately if:

- Error rate increases by more than 2x baseline
- P95 latency increases by more than 50%
- User-reported issues spike
- Data integrity issues detected
- Security vulnerability discovered

## Post-Launch Verification

In the first hour after launch, run this loop (converges with gstack `/land-and-deploy`):

```text
1. Check health endpoint returns 200
2. Check error monitoring dashboard (no new error types)
3. Check latency dashboard (no regression vs baseline)
4. Test the critical user flow manually
5. Verify logs are flowing and readable, correlation IDs present
6. Confirm the rollback mechanism works (dry run if possible)
```

If any step fails, treat it as a rollback trigger, not a "watch and see."

## Rollback Strategy

Every deployment needs a rollback plan before it happens:

```markdown
## Rollback Plan for [Feature/Release]

### Trigger Conditions
- Error rate > 2x baseline
- P95 latency > [X]ms
- User reports of [specific issue]

### Rollback Steps
1. Disable feature flag (if applicable)  OR  deploy previous version: `git revert <commit> && git push`
2. Verify rollback: health check, error monitoring
3. Communicate: notify team of rollback

### Database Considerations
- Migration [X] has a rollback path; data inserted by the new feature is [preserved / cleaned up]

### Time to Rollback
- Feature flag: < 1 minute
- Redeploy previous version: < 5 minutes
- Database rollback: < 15 minutes
```

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "It works in staging, it will work in production" | Production has different data, traffic patterns, and edge cases. Monitor after deploy. |
| "We do not need feature flags for this" | Every feature benefits from a kill switch. Even "simple" changes can break things. |
| "Monitoring is overhead" | Not having monitoring means you discover problems from user complaints instead of dashboards. |
| "We will add monitoring later" | Add it before launch. You cannot debug what you cannot see. |
| "Rolling back is admitting failure" | Rolling back is responsible engineering. Shipping a broken feature is the failure. |

## Red Flags

- Deploying without a rollback plan
- No monitoring or error reporting in production
- Big-bang releases (everything at once, no staging)
- Feature flags with no expiration or owner
- No one monitoring the deploy for the first hour
- Production environment configuration done by memory, not code
- "It is Friday afternoon, let's ship it"

## Verification

Before deploying:

- [ ] Pre-launch checklist completed (all sections green)
- [ ] Feature flag configured (if applicable)
- [ ] Rollback plan documented
- [ ] Monitoring dashboards set up
- [ ] Team notified of deployment

After deploying:

- [ ] Health check returns 200
- [ ] Error rate is normal
- [ ] Latency is normal
- [ ] Critical user flow works
- [ ] Logs are flowing
- [ ] Rollback tested or verified ready
