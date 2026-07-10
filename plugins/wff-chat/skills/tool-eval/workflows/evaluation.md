# Tool Eval: phase commands

Concrete commands for each phase of the `tool-eval` workflow. Run from a fresh
clone of the target unless a phase says otherwise. Replace `TARGET` with the
clone path.

## Phase 1: Characterize

Read docs without cloning the whole tree first:

```bash
# Cheap doc read via the API-free raw host
for f in README.md DESIGN.md SPEC.md ARCHITECTURE.md docs/architecture.md; do
  echo "=== $f ==="; curl -fsSL "https://raw.githubusercontent.com/<owner>/<repo>/main/$f" 2>/dev/null | head -120
done
```

Record the inspected commit or tag so the eval is reproducible:

```bash
git -C TARGET rev-parse HEAD
git -C TARGET describe --tags --always 2>/dev/null
```

## Phase 2: Map the source tree

```bash
# Directory shape, excluding noise
find TARGET -type f -not -path '*/.git/*' -not -path '*/node_modules/*' \
  | sed "s#^TARGET/##" | awk -F/ '{print $1}' | sort | uniq -c | sort -rn

# LOC split: value core vs peripheral. Adjust the globs per target.
echo "core:"; find TARGET/src/main -type f \( -name '*.ts' -o -name '*.py' \) -exec cat {} + | wc -l
echo "peripheral (ui/blog/assets):"; find TARGET/src/renderer TARGET/blog -type f -exec cat {} + 2>/dev/null | wc -l
```

The split is the headline number: it shows how much of the repo is a real
reuse candidate versus shell.

## Phase 3: Coupling-boundary gate

Read the imports of every core candidate file. A file is PORTABLE only if its
imports are stdlib or framework-free.

```bash
# Find framework lock-in across the core
grep -rn "from 'electron'\|from \"react\"\|import torch\|from django" TARGET/src/main

# Per-file import audit (Node example)
grep -n "^import" TARGET/src/main/<file>.ts
# Python example
grep -n "^\(import\|from\) " TARGET/<pkg>/<file>.py
```

A core file that imports only `node:*` (or Python stdlib) is the high-value
case: it can be lifted without dragging the framework.

## Phase 4: Licence gate

```bash
head -5 TARGET/LICENSE
# Hunt carve-outs the LICENSE file alone will not show
find TARGET \( -name 'README.md' -o -name 'ATTRIBUTION.md' -o -name '*LICENSE*' \) 2>/dev/null \
  | xargs -r grep -in "non-commercial\|no commercial\|free version\|attribution required\|cc by-nc" \
  2>/dev/null | head
```

Flag any asset or sub-dependency carve-out explicitly. A permissive code
licence does not clear bundled non-commercial assets.

## Phase 5: Relationship classification

Decide using the table in `SKILL.md`. The deciding question:

- Does Claude Code LOAD this the way it loads our repo (skills, agents,
  markdown)? Then HOMOGENEOUS LOADABLE CONTENT, submodule fits.
- Does this RUN Claude Code (spawns it, wraps it, hosts it)? Then INVERTED /
  HOST, submodule is a category error.
- Is it a different language or runtime you would call, not load? Then
  ORTHOGONAL, port concepts only.

## Phase 6: Gap mapping

Map each PORTABLE unit to a real gap in our setup. Confirm the gap is real,
not already covered:

```bash
# Is there already an agent/skill/rule/standard for this capability?
grep -rl "<capability keyword>" ~/.claude/agents ~/.claude/skills \
  ~/.claude/rules ~/.claude/standards 2>/dev/null
```

If the grep finds an existing owner, the unit is convergent validation
(Phase 8), not a gap to fill.

## Phase 7: Delivery-model weighting

For each surviving candidate, answer one question: does it work as ambient,
inherited, in-editor config that is on by default in every project, or does it
need a persistent process, a separate UI, or a manual launch step? The first
FITS; the second FIGHTS. Record the judgement per candidate in the element
table. An element that FIGHTS the model drops a tier even if technically strong.

## Phase 8: Convergent-validation note

List patterns where the target reached a design we already use (append-only
logs, permission-prompt HITL, file-based memory). These are not action items;
they raise confidence in both designs. Write "None identified" if absent.
