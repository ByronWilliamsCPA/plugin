---
name: executing-plans-extras
description: Local delta on top of the vendored executing-plans skill. Adds a DONE_WITH_CONCERNS protocol for exact-content steps that fail an environment-specific parse check, and a pre-commit lever-direction probe for steps that prescribe a value to hit a metric. Use alongside executing-plans when a plan step specifies exact file content that conflicts with the project's module system or environment, or when a step says "change X to achieve metric Y." Triggers on: executing a plan, exact file content, parse check failed, __dirname ESM, change X to achieve Y, plan step environment mismatch.
---

# executing-plans-extras

Extends the vendored `executing-plans` skill (read-only, in `.submodules`). Contains only the delta: how to honor exact-content fidelity when the environment contradicts it, and how to validate a step's causal premise before committing a prescribed value.

## Exact-content step that fails a parse check: commit as-is, surface the concern

A plan's causal or content claim can conflict with the project environment. When a step specifies exact file content (not to be modified) and the parse/verification step then fails due to an environment mismatch rather than a plan authoring error, do not modify the plan content and do not silently skip the parse check. Commit the content as specified, then report a DONE_WITH_CONCERNS that clearly distinguishes:

1. the plan content was committed as-is;
2. the parse check failed due to a named environment issue, with the error verbatim and the root-cause diagnosis; and
3. the minimal one-line fix for the next task author.

Example: a plan specified `cwd: __dirname` in a Playwright config, but the project has `"type": "module"`, so `__dirname` is undefined under the ESM loader and `playwright test --list` fails. The fix to hand forward:

```ts
import { fileURLToPath } from 'url';
import { dirname } from 'path';
const __dirname = dirname(fileURLToPath(import.meta.url));
```

The concern report carries the error, the root cause, and the fix so the next task author can resolve it without rediscovery.

## Validate the lever's direction before committing a prescribed value

A spec's causal claim ("do X to move Y toward Z") is a hypothesis, not a fact. When a step prescribes a value of X to achieve a target metric Y, run a cheap pre-commit diagnostic that sweeps X across a small grid and confirms the sign of dY/dX matches the brief BEFORE picking a value. A brief can assume growing benefits pull funded status DOWN when they push it UP (growth drains the liability denominator faster than NAV), so the prescribed direction overshoots and hides the real cause. If the sign is wrong, surface it as a finding rather than tuning X to fit the target.
