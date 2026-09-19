---
name: verification-before-completion-extras
description: Local delta on top of the vendored verification-before-completion skill. Adds artifact-anchored, consumer-derived, and dependency-graph verification patterns for handoffs, derived numbers, templated deliverables, and detector checks. Use alongside verification-before-completion whenever claiming work is complete or fixed, accepting a delegated lane's "done", filling tokens in a report, deriving a new statistic from a frozen model, or shipping a guard/regression test. Triggers on: is this done, completion claim, verify complete, accept handoff, fill tokens, derive statistic, freshness check, does the guard work.
---

# verification-before-completion-extras

Extends the vendored `verification-before-completion` skill (read-only, in `.submodules`). Contains only the delta: a set of patterns that all reduce to one meta-principle, then the specific cases that make it operational.

## Meta-principle: check claims against a falsifiable artifact or a frozen anchor

Every observation here is the same failure in different clothing. A completion, freshness, or derivation claim is trustworthy only when it is tied to something external that can prove it wrong:

- A completion claim is meaningful only relative to a named, falsifiable output artifact. "Done" with no checkable referent is a status, not a fact.
- Internal consistency is not agreement with the source of truth. A table that agrees with itself, a manifest that reads all-green, a report whose cells are mutually consistent: none of these prove agreement with the producing artifact.
- A check that passes on a known-broken state proves nothing. Green-on-clean is necessary but not sufficient; the detector must go red on the defect it exists to catch.

Hold every "complete / fresh / correct" assertion against that bar before making it.

## Accepting delegated, parallel, or handed-off work

When a subagent, lane, or teammate reports a task complete, do not accept the narrative. Verify against the task's named output artifact: the exact file, path, or test the deliverable was defined as. If the artifact does not exist or is empty, the task is not done regardless of the report. Make the expected artifact path part of every delegation up front, so the completion claim is falsifiable rather than rhetorical.

A handoff describes intent, not ground truth. Steps a handoff labels "mechanical" (fill these tokens, just re-run script X) routinely hide missing or partial upstream work:

- For any "re-run script X" step, confirm the script's actual scope (which inputs/candidates it iterates) and that its output covers the target entity. A rerun script that silently iterates a 5-item subset omits the candidate that mattered.
- For any token families or value families, confirm a producing artifact actually exists and covers the target before treating the fill as mechanical.

Scope your own completion to the reviews you actually reconciled against. A verification scoped to your own checks reads as a clean close of all known findings, but parallel reviews and out-of-tree artifacts (search `/tmp`, `outputs/`, parallel-team dirs, not just the in-repo review) carry non-overlapping finding sets. Enumerate all review artifacts, re-verify each finding against current code by recomputation rather than prose, and state completion explicitly scoped ("closed the criticals X found") with the remainder listed.

## Verifying a deliverable that another party will judge

For any deliverable validated by someone other than the author, ship a runnable verification gate (script or test) rather than a prose claim. The gate should:

- check each definition-of-done item with a non-zero exit on failure, and
- validate schema/interface conformance by importing the consumer's own contract (e.g., read the expected CSV column order from the downstream script's constant), not by restating it.

A snapshot assertion rots; a contract-derived assertion stays honest as the consumer evolves. Where feasible, prove completion THROUGH the consumer (a dry ingest), not merely adjacent to it.

## Live-exercise gate for external dependencies

A green mock, static-config, or build/sign/scan pipeline is not proof a live capability works: an 88%-coverage mocked test suite still shipped six live-only defects, and a fully green build/SBOM/sign/scan pipeline produced an image that could not boot. For any integration whose correctness depends on a remote system, container runtime, or network path, require one live smoke call (boot plus a real request, DNS resolution plus one API call, a curl against the real capability) as a completion gate, not optional polish. When the canonical live check is environment-gated and cannot run, do not report the gate as satisfied; substitute a check of the same invariant and disclose the substitution explicitly, rather than letting a Docker-gated test skip silently and pass by omission. When a change moves a quantitative target, verify both the floor and the ceiling it could now violate, not only the direction being pushed: a prompt fix that cleared a floor can silently produce invalid truncated output past the other bound.

## Status codes are not provenance

When what's being verified sits behind a proxy, gateway, or an orchestrator's reconciliation step, a 200 or a passing healthcheck can be produced by a shadow layer, not the real service: a reverse-proxy stub answered the app's health path for a month while the real handler never ran, and a `--version` healthcheck reported healthy through a total outage because it probed the artifact, not the service. Recreating a container from compose can also silently drop a hand-patched network attachment, so a direct-port probe passes while the real ingress path fails. Assert on response provenance or content (a field only the real handler emits, the right content-type) and on the actual ingress path a client takes, never on status code or a direct-port probe alone. If a hardcoded stub could satisfy the assertion, the assertion proves nothing.

## Freshness is a property of the dependency graph, not the filesystem

Do not judge "is this output current?" by file existence or coarse mtime:

- Use full ISO timestamps with dates, not time-only listings; a sibling that looks newer may be a day older.
- Establish the read/write dependency graph (`grep` for who writes and who reads each artifact). A newer-looking file is not evidence of staleness unless it is actually an input to the output in question. Verify the edge exists before treating timestamp ordering as a signal.

When a set of entities expands (5 baselines become 9 candidates), expansion is not done when the source list is updated; it is done when every iteration driver iterates the new set and every regenerated artifact actually contains the new keys. Audit (a) every driver for a stale hardcoded set (a function that loads `active_candidates()` then ignores it for a hardcoded list), and (b) every artifact for real key coverage, not just file mtime. A handoff's "regenerated over X" claim must be checked against the artifact's contents.

The same discipline applies to claims about live external systems, not just local files. A claim of the form "X is (or is not) live, applied, or up to date" (a migration applied to staging, an issue's open/closed state, a merge status) must be settled by querying that system directly, never by a proxy (a CI run outcome, a merge state, a stored note, an issue's open/closed flag) and never from a snapshot older than the decision it supports. Before the first mutating call through a shared connection, confirm which environment it actually targets with a read-only, data-signature probe; a shared DB/MCP connection can be silently bound to prod while the task is framed as staging. When two tracking artifacts agree, that is not corroboration if they share the same blind spot: the tiebreaker is the live system, not either document. Classify each verification step by what it actually asserts (a system-wide property vs. a data-specific journey) before applying an admissibility rule uniformly across both; over-conservatism under-reports as reliably as laxity over-reports.

## Templated deliverables: verify the non-token cells, not just the placeholders

A placeholder marks what is missing, not what is stale. When filling tokens in a templated exhibit, the surrounding hardcoded cells can be from an older run, so a token-only fill places fresh numbers beside stale neighbors. The unit of correctness is the exhibit, not the token: verify the whole artifact shares one run/vintage, especially comparison tables where the placeholder column and the fixed columns must share one vintage.

Reconcile every numeric cell against the live producing artifact by candidate-plus-metric, never against the report's own internal consistency. Two distinct failure classes hide here:

- Metric-definition drift between runs (a pre-fix vs post-fix definition change shifts a whole column, not one cell); and
- Partial reconciliation, where one table in a file is fixed and a sibling table on the same metric is left contradicting it.

When one table has been reconciled, re-scan sibling tables in the same file for the same metric.

## Metric-as-computed vs metric-as-documented

A status manifest tracks what it was built to track. Token presence and weight-vector reconciliation are cheap, so they get checked; metric-definition fidelity is expensive, so it gets assumed. For each locked definition (criterion, metric, constraint), confirm the value as COMPUTED in the engine matches the value as DOCUMENTED in the spec by reading the code path, not the manifest. A manifest can read fully green while a criterion's floor was never implemented or a criterion is scored on a placeholder metric. Cross-check a finished artifact's own metadata (run date, draft/winner flags) against the prose that cites it.

When report prose states WHY an engine removed, kept, or ranked something, treat the causal mechanism as a claim to verify against the engine's own pass/fail record. Inherited rationale ("X fails because Y") is a hypothesis, not a citation: a diagnostic value that co-occurs with removal (a low LCR) can be a bystander while the real gate is elsewhere (an IPS ceiling). Read the gate formula.

## Provenance: trace the verdict to the audited code path

A PASS is only as trustworthy as the code path that produced it. Re-checking the cited numbers is necessary but not sufficient. Run the gate's own tested entry point on the committed inputs (not the narrative numbers), confirm the basis/column the harness reads matches the basis the verdict claims, and confirm the test fixtures match the production input schema (row names, units, decimal-vs-percent). Treat any verdict-vs-harness divergence as critical: a PASS hand-transcribed from a different script on a different basis is a provenance defect even when the numbers look plausible.

The same trap applies to tool identity, not just basis. When verifying a claim about a specific named gate, tool, or vendor behavior, reproduce it with that exact tool, config, and version, never a same-category substitute or the vendor's own marketing text. Common divergent pairs worth naming explicitly: pip-audit vs osv-scanner, an ad-hoc per-file linter/type-checker call vs the project's configured wrapper (e.g. a `nox -s type_check` session), `python -m build` vs the project's native builder (e.g. `uv build`), and a vendor's documentation vs one live call against the real API.

### Oracle independence: could the check pass even if the target failed?

Before accepting a verification command as evidence, ask what it would output if the thing being verified had actually failed. If the answer is the same output, the oracle shares state with its subject and proves nothing: `git show <tag>:<file>` reads the local object store regardless of whether a remote push ever succeeded. Replace such a check with an independent reader, a fresh clone or fetch rather than a local read, and prefer the real consumer's own parser or resolver over a reimplementation of its rules (a hand-rolled `.env` parser can flag a value the real dotenv consumer parses cleanly; a hand-rolled publish-check script can read the wrong field name and report a successful publish as failed). Before running an inherited or prescribed verification procedure, restate the claim in one sentence and ask for the minimum observation that would falsify it, then prefer that over the more expensive, mutating, or timing-dependent method the brief assumed (a one-call read-only query can replace triggering a real paid job and snapshotting it mid-flight). For any load-bearing fact with a known single-tool blind spot (a single `ss -tlnp` capture can silently miss exposed services a second method like `docker ps` catches, and a container scanner can answer differently for a tag vs. its own digest when the daemon substitutes a stale cached image), corroborate with a second, differently-blind method before concluding.

## Re-deriving a new number from a frozen model

When a task forbids re-running a model but requires a new statistic derived from it, re-execute the seeded/deterministic path, then prove the derivation is faithful by reproducing a value the frozen artifact ALREADY publishes (a known median, percentile, or board value) exactly. Report that tie-out alongside the new number. A derivation that cannot reproduce a known anchor has not been verified; the anchor reproduction converts "the number looks right" into "the number is computed correctly."

## Detectors: red-on-broken is the test of the test

When the deliverable is itself a check (guard, assertion, regression test) for a known or reproducible defect, verification must include running it against a state where the defect is present and confirming it FAILS there, in addition to passing on clean input. A new guard whose unit tests are green can still stay green against the exact broken state it was written to catch. A detector is only proven by the thing it is supposed to detect. The same red-on-broken requirement extends beyond dedicated detectors to any comparison, filter, wait-loop, or shell sequence used as evidence, below.

### Vacuous and silently-swallowed passes

A comparison, validator, wait-loop, or shell redirect can report success without doing or seeing anything. Any comparison, filter, or lookup used as evidence must assert its inputs are non-empty and report a denominator ("N items examined"), not just a zero-difference result: a diff script comparing empty-to-empty because of a wrong grep pattern reported "0 differences" as proof of safety, and a lookup helper returning `{}` on "not found" is indistinguishable from "legitimately empty," letting a corrupted table vanish from a gate silently. A wait-for-condition loop must assert the positive success state for every item on a known list, never the absence of a negative marker across whatever happens to be present; a wait-loop keyed on absence of "pending" declared all-settled while a required check hadn't even been created yet. Never pipe a gate command into a truncating filter (`cmd | tail`); redirect to a file and check the gate's own exit code instead, or a failing `pre-commit run` piped through `| tail -30` will read as success. Any shell step that writes then deletes must chain the delete to the write's success (`&&`, or `set -euo pipefail`), never sequence them as separate statements, or a failed redirect can be followed by an `rm` that destroys the only copy. When ranking a batch of failing/passing checks, treat a suspiciously green result as higher priority to investigate than the red ones, especially for safety, security, or compliance gates: in one batch of 7 CI checks, the single green one was the most seriously broken (an all-skipped safety-eval reporting SUCCESS).

## Long, costly, or externally-settling operations: checkpoint early, never interrupt mid-flight

For a long, costly, or failure-prone operation (a 25-40 minute live-API measurement run), launch it in the background with an early-read checkpoint (the first N items, or the first failure signature) so a systemic problem aborts the run before its full cost is spent. When an operation has a known settle or propagation delay (DNS, certificate issuance, provisioning), let it complete and poll rather than restarting or re-triggering mid-flight; restarting a service mid-ACME-DNS-propagation-wait can leave stale records that break the retry differently than the original failure did. When orchestrating a long remote job, separate launch (returns immediately) from wait (a distinct backgrounded poller); coupling both into one synchronous call can hang the calling tool to its own timeout even though the remote process is running fine.
