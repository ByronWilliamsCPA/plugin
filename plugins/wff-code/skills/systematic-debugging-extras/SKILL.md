---
name: systematic-debugging-extras
description: Local delta on top of the vendored systematic-debugging skill. Adds numeric premise-probing, sibling-consumer falsification for shared components, data-semantics verification before applying a prescribed transform, proxy-input discipline, newly-reachable-path testing after a guard is removed, mechanism verification against the live system, uniform-failure fingerprinting, never-invoked diagnosis, and named alarms for abandoning the current approach entirely rather than continuing to patch it. Use alongside systematic-debugging when investigating any bug, all-zero/constant metric, a "shared component is broken" diagnosis, a brief that prescribes a transform or fix mechanism, a finding built on stand-in data, a fix that removes a guard, a root-cause narrative that names a mechanism, or when two straight patches have each fixed the prior patch's symptom. Triggers on: debug, root cause, all-zeros metric, shared workflow broken, difference the cumulative, proxy data, removed a guard, patch-on-patch, come too far to restart, never invoked, stale handoff path.
---

# systematic-debugging-extras

Extends the vendored `systematic-debugging` skill (read-only, in `.submodules`). Contains only the delta: the bug premise and the prescribed fix are both hypotheses, and several cheap probes discriminate truth from plausible-but-wrong before any code is written.

## The brief's diagnosis and its prescribed fix are two separate claims; verify both

systematic-debugging already says verify the root cause before fixing. Extend that to the fix mechanism. When a task brief or reviewer prescribes a transformation over a data structure (difference, cumsum, normalize, invert), verify the structure's actual semantics empirically (print a sample, check monotonicity, sum, sign) before applying it, even when the brief sounds authoritative. A confident instruction like "ta_distributions returns a cumulative curve, so difference it" can be wrong about the data model: the curve was bell-shaped per-year, and differencing it would have produced negative distributions that pass shape/sign tests but corrupt the economics. One cheap empirical probe of the actual values discriminates between the two mental models.

Likewise verify a lever's DIRECTION before committing the value a brief assumes. When a step says "change X to move metric Y toward Z," sweep X across a small grid and confirm the sign of dY/dX matches the brief first. A brief can assume growing benefits lower funded status when they raise it; committing the assumed value bakes in a wrong-signed change and masks the real driver (an asset-scope mismatch). If the sign is wrong, surface it as a finding rather than tuning X to fit.

## Restate a confirmed mechanism in a second vocabulary before choosing a fix

Between "mechanism confirmed" and "implement fix," restate the mechanism in at least two vocabularies (a bad value vs. a bad ordering, phase, or owner) and prefer the framing whose fix corrects rather than compensates. A correctly-diagnosed "stale closure" framing constrained a fix to a ref-based workaround; reframing the identical mechanism as "wrong lifecycle phase" made a one-word, non-workaround fix (`useEffect` to `useLayoutEffect`) visible. Flag inherited fix prescriptions specifically for re-derivation even when the diagnosis half is already proven correct.

## Verify a stated mechanism against the real system, not testimony, a handoff, or recollection

When a root-cause narrative names a mechanism (a file being read, a cache consulted, a hook firing), grep for that mechanism's actual implementation before writing the cause down; absence of the mechanism is itself the finding, as when "the settings object fails to load its env file" propagated through 4 comments and 5 docs before a grep showed the class declares no env-file load at all. When behavior contradicts a checked-in config, enumerate other control planes (org/repo API settings, sibling tool configs) before concluding the file is wrong; Dependabot kept opening PRs despite a detection-only config file because of an org-level API setting invisible in any repo file. When a task references an artifact by a human-supplied name, path, or branch that a direct lookup misses (a remembered story title, a stale Portainer SHA, a feature-branch tag), re-resolve it through the system's own record (runtime inspection via `docker inspect`, an activity log, the current default branch, live data) rather than continuing to search by name, and rebuild any inventory against the exact target branch before acting on it. When a diagram and prose contradict each other, resolve it by reading the governing code, not by trusting whichever artifact was edited more recently, including your own prior edit.

## "It doesn't work" sometimes means "never invoked," not "broken code"

Before attributing a failure to application code, check whether the failing symbol traces to a declared-but-unsynced dependency (run `uv sync` or `npm ci` first: "pre-existing typecheck errors" and a broken a11y suite were actually declared-but-uninstalled npm deps, cleared entirely by `npm ci`) and whether the capability has ever actually executed (query runtime or DB state, don't just read the code: 23 "blocked" Storybook drafts needed zero code fixes because the import script had simply never been run). In CI logs, a grep hit inside a multi-branch script body is the runner's pre-execution echo of an untaken branch, not proof the branch ran; anchor on output unique to the taken branch, not the script's verbatim text.

## A constant or all-zero metric is a scale mismatch in disguise

When a metric reads as a constant (all-zeros, all-same across inputs), it is almost never "low signal": one operand of a min/max/threshold is on the wrong scale (aggregate-vs-summed, per-unit-vs-total, rate-vs-level). Instrument BOTH sides of the binding comparison and print them per-input. A short numeric probe both confirms the premise (aggregate stressed share 0.48 vs summed ceiling 0.625, so over=0) and reveals the correctly-scaled operand to switch to (the single most-overweight sleeve vs its own max). The instrumentation that proves the bug usually designs the fix in the same step.

## Falsify "the shared component is broken" by sampling siblings first

When the suspect is a shared or centralized component (a reusable workflow, a shared library version, an org config), sample three to five other consumers of the same version before concluding the component is broken. One green consumer on the same version immediately falsifies the global-breakage hypothesis and redirects the investigation to the caller/consumer side. A workflow that startup-failed for one caller was caused by a caller-side missing `actions: read` grant (GitHub validates this at compile time with only a generic `startup_failure` message), not an org-wide break; five sibling repos ran the same reusable green that day. Run this cheapest falsification test before building any workaround.

## Uniform-failure and shared-predicate fingerprints localize a shared cause fast

When a failure set is uniform across targets your change provably didn't touch (18/18 visual-regression tests failed identically, including untouched pages), or when several distinct-looking guards, routes, or errors share one trigger (three cascading config guards all fired from one shared `environment != "local"` predicate; Traefik 503s hit every auth-gated route including the IdP's own host), suspect a single environmental or shared-predicate cause before investigating each symptom individually; fixing one guard at a time is whack-a-mole that also destroys the signal. Characterize what the *passing* subset has in common, not just the failing one: after a clean merge, the tests that kept passing shared "makes no provider call," which named the changed collaborator immediately. In a layered-config system, a value present in exactly one layer, observed downstream, partitions the hypothesis space before touching anything. Before attributing a containerized-reproduction connection failure to the code, confirm the container runtime's network model matches the target environment (`docker context show`, since Docker Desktop/WSL2's `--network host` doesn't share the host loopback); before comparing a local probe to CI, confirm both resolve to the same network path (`getent hosts`), since split-horizon DNS can route them differently.

## A proxy is a placeholder for evidence, not evidence

When an analysis rests on a proxy, sample, or stand-in for a blocked real input, any conclusion carries an obligation to recompute against the real input. (a) Label the finding provisional and name the proxy explicitly in any broadcast; (b) record the specific upstream artifact whose arrival resolves it; (c) treat "real input now available" as a high-priority trigger to recompute and correct the record before the proxy finding ossifies into accepted fact. A stale-CMA proxy implied a 116 bps miss; the real 2026 inputs reversed it to within tolerance. Correcting a broadcast finding is a deliverable, not an embarrassment.

## Removing a guard makes downstream code reachable for the first time

A bug-causing condition can double as accidental protection for code downstream of it. When a fix removes a guard or makes a previously-unreachable path reachable, run the end-to-end scenario in the exact trigger condition, not just unit tests. Fixing a `max([])` crash on an empty-survivor set let scoring proceed over the full field, which then KeyError'd in a downstream function on a candidate missing from a stale artifact; unit tests passed and only the real trigger condition exposed the second failure. Verify the whole newly-live path, not just the line you changed.

## A fix that removes a mask can convert a hidden defect into a louder one, or merely reveal the next of several

The same principle extends beyond guards to any cache, retry, or mask (`continue-on-error`, a broad try/except, `|| true`): when a fix removes one, ask what it was hiding and verify the newly-live path end to end, not just that the original symptom is gone. Fixing a masked `continue-on-error` 403 revealed a deeper "Advanced Security not enabled" blocker underneath, and fixing a silently-ignored env var unmasked a second defect (a wrong DB driver) in the value it started reading. When the fix is "add the missing list entry," run the tool to completion rather than reasoning that one observed omission is the whole class; a fail-fast runner reports only the first of several sequential blockers per run. When a fix restores a broken sync or deploy mechanism, its blast radius is everything that accumulated while it was broken, not just the immediate defect: repairing a broken GitOps auto-deploy pipeline applied every accumulated commit at once, including two new required secrets nobody had provisioned.

## Named alarms for abandoning the loop entirely, not just the current hypothesis

systematic-debugging's reproduce-hypothesize-fix loop assumes the approach is sound and only the specific defect is unknown. Sometimes the approach itself is the defect, and no amount of careful hypothesis-testing inside a wrong plan converges. Treat any of these as a stop signal, not background noise, and switch from debugging the current line to replanning the approach:

- The last two changes each fixed the symptom the previous change introduced (patch-on-patch, not narrowing toward a root cause)
- The design keeps growing special cases to route around the same recurring conflict
- Fixing this requires fighting or monkey-patching the framework rather than working with it
- A "small fix" has now spread edits across many unrelated files
- You cannot explain why a line exists beyond "it made the error go away"
- Three attempts have failed on the same error
- You catch yourself thinking "I've come too far to restart"

When one fires: stop making incremental edits, name what the current approach got right (understanding of the problem, ruled-out branches) so it isn't lost, revert or discard the accumulated patches, and replan from the corrected understanding rather than continuing to layer fixes onto a plan that is itself the bug. Code built on a wrong approach is cheap to discard; the understanding that revealed the approach was wrong is the only part worth keeping.
