---
name: test-driven-development-extras
description: Local delta on top of the vendored test-driven-development skill. Adds GREEN-step lint discipline, shared-definition extraction for comparable metrics, autofix-hook edit ordering, and an empirical design-falsification step for metrics. Use alongside test-driven-development when implementing a feature or bugfix, especially when the change adds a control-flow branch, computes a value that must match a reported one, edits files in a repo with PostToolUse formatters, or designs a new scoring/heuristic metric. Triggers on: TDD, write the test first, GREEN step, new metric, comparable metric, autofix stripped my import, scoring criterion.
---

# test-driven-development-extras

Extends the vendored `test-driven-development` skill (read-only, in `.submodules`). Contains only the delta: where the red/green/refactor loop needs extra guards in this environment, and where "watch it fail" must be applied at the design level, not just the code level.

## A green unit test does not prove the spec is right

A unit test proves the code matches the spec; it does not prove the spec is correct. For metric, scoring, or heuristic work, the spec itself needs an empirical falsification step on live data BEFORE you implement it. Compute the PROPOSED metric on real input in a throwaway script and confirm it moves the result in the intended direction. A metric can be implemented perfectly and still encode the exact defect it was meant to remove (e.g., a vol-band-only metric inverts intent when the perturbation co-moves all candidates and freezes ranks). Without the prototype, the unit test passes against a laundered artifact and certifies a wrong answer. "Watch it fail" has a design-level analogue: prove the metric design discriminates on real data first, or the prototype will redirect a self-contained patch into the cross-module change it actually needs.

## Shared definition for values that must be equal by construction

Comparability bugs are silent. When a new feature computes a value that must equal a value already produced elsewhere (a new optimizer metric vs an existing reported breach-share), do not reimplement the formula at the new call site: two copies can drift, and nothing fails loudly when they do. Extract the existing computation (often an inline expression buried in a larger function) into a named, pure, separately-tested helper; write one test asserting the helper reproduces the original inline expression on a synthetic input; then route both the old site and the new site through it. One tested definition replaces an invisible two-copies-can-diverge risk.

## Run the linter as part of the GREEN gate, not after it

Complexity-limit lint rules are stateful over the whole function, so a one-line behavioral change can cross a threshold the diff did not obviously approach. When the minimal implementation that satisfies the failing test adds a control-flow branch (an extra return, an extra nesting level, an extra boolean clause) to an already-dense function, it can trip cumulative-count rules: PLR0911 (returns), PLR0912 (branches), PLR0915 (statements), C901 (mccabe). Run the project linter before declaring GREEN. Under the no-suppression policy the only correct fix is to extract a helper, never an inline ignore; caught at GREEN this is cheap, caught at commit it is expensive. Also put new symbols a test needs (including private constants) in the top-level import block, not a function-local import, to avoid PLC0415.

## Stage edits so the autofixer never breaks the next edit

In a repo with a known PostToolUse autofix/formatter hook, the file is mutated between your edits. Splitting "add import" and "add usage" across two edits lets ruff `--fix` remove the import as unused (F401) after the first edit, so the second edit references an undefined name and the module fails at import (a NameError that only surfaces at test collection). Add an import and at least one use of it in the SAME edit, or add the consuming code first and the import second. Treat every intermediate edit as if it will be linted and autofixed immediately, because it will be: no intermediate state may contain a violation the autofixer will act on.
