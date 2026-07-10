---
name: frontend-design
description: >
  Create distinctive, production-grade frontend interfaces with high design quality
  and strong UX foundations. Use when building web components, pages, dashboards,
  landing pages, or applications. Covers creative direction, accessibility, interaction
  design, performance optimization, and visual polish. Supports React, Next.js, Vue,
  Svelte, and HTML/CSS.
version: 1.0.0
sources:
  - anthropics/skills/frontend-design (creative direction, anti-slop aesthetics)
  - vercel-labs/agent-skills/react-best-practices (69 React/Next.js perf rules)
  - nextlevelbuilder/ui-ux-pro-max (99 UX guidelines, accessibility, interaction)
---

# Frontend Design Skill

Create distinctive, production-grade frontend interfaces that avoid generic AI aesthetics.
Implement real working code with exceptional attention to aesthetic details, accessibility,
performance, and creative choices.

## Activation

Trigger on: build UI, create component, design page, frontend, landing page, dashboard,
web app, React component, HTML/CSS layout, style UI, beautify, improve UI, review UI,
check accessibility, audit design, review UX

## Design Thinking (REQUIRED Before Coding)

Before writing any code, commit to a clear aesthetic direction:

- **Purpose**: What problem does this interface solve? Who uses it?
- **Tone**: Pick a bold direction: brutally minimal, maximalist chaos, retro-futuristic,
  organic/natural, luxury/refined, playful/toy-like, editorial/magazine, brutalist/raw,
  art deco/geometric, soft/pastel, industrial/utilitarian, etc.
- **Constraints**: Framework, performance budget, accessibility requirements
- **Differentiation**: What makes this UNFORGETTABLE? What will someone remember?

**CRITICAL**: Choose a clear conceptual direction and execute it with precision.
Bold maximalism and refined minimalism both work -- the key is intentionality, not intensity.

### Greenfield only: propose 4 distinct directions

When there is no existing brand, design-system tokens, or reference site to extend
(true greenfield), propose **4 distinct visual directions** instead of committing to
one alone, each specified concretely:

- Background hex / accent hex
- Display + body typeface pairing
- One-line rationale tied to the brief

The four must not share a palette family (four takes on warm-cream is one direction,
not four), and at least one must be deliberately off-distribution from the obvious
choice. Let the user pick, or state a clear recommendation if asked to decide.

This does **not** apply when real tokens or brand colors are given: extend those
directly (see `.claude/rules/design.md`, "Verify output against real tokens") rather
than proposing alternatives to a brand that already exists.

Then implement working code (HTML/CSS/JS, React, Vue, Svelte, etc.) that is:
- Production-grade and functional
- Visually striking and memorable
- Cohesive with a clear aesthetic point-of-view
- Meticulously refined in every detail

## Arguments

- (none) -- Design thinking + full implementation
- `wireframe` -- Low-fidelity exploration: 3+ structurally distinct layout variations before hi-fi
- `prototype` -- Build an interactive, clickable version of an already-chosen direction
- `variations` -- Produce 3+ hi-fi variations across named axes of an established direction
- `review [--focus accessibility|ai-slop|hierarchy-rhythm|interaction-states]` -- Review
  existing UI against UX checklist and aesthetics guidelines; `--focus` scopes a single
  invocation to one dimension (see Mode: Review)
- `polish-pass` -- Orchestrator-dispatched parallel review: four scoped `review --focus`
  invocations run concurrently and are aggregated (see Mode: Polish Pass)
- `a11y` -- Focused accessibility audit (WCAG AA compliance)
- `perf` -- Performance optimization pass (React/Next.js focus)
- `fix <file>` -- Fix UI/UX issues in a specific file

---

## Part 1: Aesthetics Guidelines

Source: Anthropic frontend-design skill (adapted)

### Typography

Choose fonts that are beautiful, unique, and interesting. Avoid generic fonts like
Arial, Inter, Roboto, and system defaults. Opt for distinctive choices that elevate the
interface. Pair a distinctive display font with a refined body font.

### Color & Theme

Commit to a cohesive aesthetic. Use CSS variables for consistency. Dominant colors with
sharp accents outperform timid, evenly-distributed palettes. Design light and dark
variants together to keep brand, contrast, and style consistent.

### Motion

Use animations for effects and micro-interactions. Focus on high-impact moments: one
well-orchestrated page load with staggered reveals (animation-delay) creates more
delight than scattered micro-interactions. Use scroll-triggering and hover states that
surprise.

- Prioritize CSS-only solutions for HTML
- Use Motion (framer-motion) for React when available
- Duration 150-300ms for micro-interactions; complex transitions <=400ms
- Use ease-out for entering, ease-in for exiting; avoid linear for UI transitions
- Prefer spring/physics-based curves for natural feel
- Exit animations shorter than enter (~60-70% of enter duration)
- Stagger list/grid item entrance by 30-50ms per item
- ALL animations must respect `prefers-reduced-motion`

### Spatial Composition

Unexpected layouts. Asymmetry. Overlap. Diagonal flow. Grid-breaking elements. Generous
negative space OR controlled density. Use 4pt/8dp incremental spacing system.

### Backgrounds & Visual Details

Create atmosphere and depth rather than defaulting to solid colors. Gradient meshes,
noise textures, geometric patterns, layered transparencies, dramatic shadows, decorative
borders, custom cursors, grain overlays.

### Hierarchy & Rhythm

Two qualities separate "intentional" from "generic AI-generated" work: hierarchy (what
gets looked at first, second, third) and rhythm (repetition with strategic variation).

- **Hierarchy**: primary/secondary/tertiary distinguishable by size, color, weight,
  position, and density; a first-time viewer should know what to look at and what to do
  within 5 seconds. Flag reversed hierarchy (unimportant elements loudest or most
  prominent) and flat hierarchy (everything the same size, color, and weight).
- **Rhythm**: spacing and type values snap to one consistent scale (4pt/8dp multiples;
  a fixed type scale like 12/14/16/18/24/32); repeated elements (cards, list items,
  feature blocks) share structure exactly rather than being subtly, accidentally
  different; the design breaks its own pattern once, deliberately, rather than staying
  uniform for its full length or varying every section.
- **Palette discipline**: 3-5 colors plus tints/shades. Flag 8+ distinct colors, or
  near-duplicate blues/grays used inconsistently across the file.

### Anti-Patterns (NEVER Use)

Each rule states the positive default first, then the concrete tell to detect and replace it.

- **Typography.** Default: a distinctive display font paired with a refined body font,
  chosen with intent. Detect & replace: Inter, Roboto, Arial, Space Grotesk, or a bare
  system-font stack used as a silent default.
- **Gradients.** Default: a flat color from the design system, or a subtle on-tone
  two-stop gradient. Detect & replace: rainbow or 3+ color gradients; saturated
  purple-to-pink, orange-to-pink, or other trendy blends on heroes, buttons, or large
  surfaces.
- **Layout.** Default: a composition considered for this brief, with distinct
  components and deliberate asymmetry or density where earned. Detect & replace: the
  same centered-card-on-gradient shape and cookie-cutter component patterns that
  repeat across unrelated AI-generated outputs; generic AI-generated aesthetics
  ("AI slop") overall.
- **Emoji.** Default: no emoji, unless the brand already uses them, the emoji is
  functional (a status or category marker), or the user asked. Detect & replace:
  emoji used as structural icons, prepended to headlines or buttons, or as filler
  bullets -- use SVG icons (Heroicons, Lucide) instead. Never mix filled and outline
  icon styles at the same hierarchy level.
- **Cards.** Default: subtle shadow, thin all-around border, or background
  separation. Reserve `border-left: 4px solid` for semantic emphasis (callouts,
  alerts, status). Detect & replace: `border-radius: 12px` paired with
  `border-left: 4px solid` used as the *default* card style -- this specific
  combination reads as "default SaaS template," not a considered choice.
- **Imagery.** Default, in order: real photography (licensed or brand assets);
  professional illustration; an honest placeholder (striped background, monospace
  label like `product shot (1200x800)`). Detect & replace: generic "AI-style"
  character art (giant heads, flat-color blobs, identical posing), or
  placeholder-quality decoration presented as final.
- **Color tokens.** Default: every color traces to a semantic token
  (`--color-primary`, `--color-surface`) or design-system variable. Detect &
  replace: raw hex values written directly in component code -- five slightly
  different blues across one file means colors were invented inline instead of
  reused from tokens.

### Implementation Complexity Rule

Match code complexity to the aesthetic vision:
- **Maximalist designs**: Elaborate code with extensive animations, effects, layered visuals
- **Minimalist designs**: Restraint, precision, careful spacing/typography/subtle details
- Elegance comes from executing the vision well, not from adding more

---

## Part 2: UX & Accessibility Checklist

Source: nextlevelbuilder/ui-ux-pro-max (adapted, generalized from React Native)

### Priority 1: Accessibility (CRITICAL)

| Rule | Standard |
|------|----------|
| `color-contrast` | Minimum 4.5:1 for normal text, 3:1 for large text (WCAG AA). **Compute it, never eyeball it**: run `.claude/skills/frontend-design/scripts/wcag-contrast.py FG BG` (or `--batch` with a JSON list) for every distinct text/background and UI-component color pairing actually used -- including hover, active, and focus-state color overrides, not just the resting state. A 2026-07-07 trial found five undetected AA failures in agent-delivered output whose own summary claimed contrast had been "verified by hand"; an LLM estimating hex contrast by eye is unreliable, the ratio is a deterministic computation, so a tool call replaces the estimate. Cite the script's printed ratio as evidence in the Pre-Delivery Checklist, not an unverified claim. |
| `focus-states` | Visible focus rings (2-4px) on all interactive elements |
| `alt-text` | Descriptive alt text for meaningful images |
| `aria-labels` | aria-label for icon-only buttons |
| `keyboard-nav` | Tab order matches visual order; full keyboard support |
| `form-labels` | Use `<label>` with `for` attribute; never placeholder-only |
| `skip-links` | Skip to main content for keyboard users |
| `heading-hierarchy` | Sequential h1-h6, no level skipping |
| `color-not-only` | Never convey info by color alone (add icon/text) |
| `reduced-motion` | Respect `prefers-reduced-motion`; reduce/disable animations |
| `screen-reader` | Meaningful labels; logical reading order |
| `escape-routes` | Provide cancel/back in modals and multi-step flows |

### Priority 2: Touch & Interaction (CRITICAL)

| Rule | Standard |
|------|----------|
| `touch-target-size` | Min 44x44px interactive area |
| `touch-spacing` | Minimum 8px gap between touch targets |
| `hover-vs-tap` | Use click/tap for primary interactions; never rely on hover alone |
| `loading-buttons` | Disable button during async; show spinner or progress |
| `error-feedback` | Clear error messages near the problem |
| `cursor-pointer` | Add cursor-pointer to all clickable elements |
| `tap-feedback` | Visual feedback on press within 100ms (ripple, opacity, scale) |
| `disabled-clarity` | Disabled elements: reduced opacity (0.38-0.5) + cursor change + semantic attribute |

### Priority 3: Performance (HIGH)

| Rule | Standard |
|------|----------|
| `image-optimization` | WebP/AVIF, responsive srcset/sizes, lazy load non-critical |
| `image-dimensions` | Declare width/height or aspect-ratio to prevent CLS |
| `font-loading` | font-display: swap/optional; preload critical fonts only |
| `critical-css` | Prioritize above-the-fold CSS |
| `lazy-loading` | Lazy load non-hero components via dynamic import |
| `bundle-splitting` | Split code by route/feature |
| `third-party-scripts` | Load async/defer; audit and remove unnecessary ones |
| `content-jumping` | Reserve space for async content (CLS < 0.1) |
| `virtualize-lists` | Virtualize lists with 50+ items |
| `debounce-throttle` | Debounce/throttle high-frequency events (scroll, resize, input) |

### Priority 4: Style Selection (HIGH)

| Rule | Standard |
|------|----------|
| `style-match` | Match style to product type and audience |
| `consistency` | Same style across all pages |
| `no-emoji-icons` | Use SVG icons (Heroicons, Lucide), not emojis |
| `effects-match-style` | Shadows, blur, radius aligned with chosen style |
| `state-clarity` | Hover/pressed/disabled states visually distinct |
| `elevation-consistent` | Consistent shadow/elevation scale for cards, sheets, modals |
| `dark-mode-pairing` | Design light/dark variants together |
| `icon-style-consistent` | One icon set/visual language across the product |
| `primary-action` | One primary CTA per screen; secondary actions visually subordinate |

### Priority 5: Layout & Responsive (HIGH)

| Rule | Standard |
|------|----------|
| `viewport-meta` | width=device-width initial-scale=1 (never disable zoom) |
| `mobile-first` | Design mobile-first, scale up |
| `breakpoints` | Systematic: 375 / 768 / 1024 / 1440 |
| `readable-font-size` | Minimum 16px body text on mobile |
| `line-length` | 35-60 chars mobile; 60-75 chars desktop |
| `no-horizontal-scroll` | Content fits viewport width |
| `spacing-scale` | 4pt/8dp incremental spacing system |
| `container-width` | Consistent max-width on desktop |
| `z-index-management` | Defined layered scale (0/10/20/40/100/1000) |
| `viewport-units` | Prefer min-h-dvh over 100vh on mobile |

### Priority 6: Typography & Color (MEDIUM)

| Rule | Standard |
|------|----------|
| `line-height` | 1.5-1.75 for body text |
| `font-pairing` | Match heading/body font personalities |
| `font-scale` | Consistent type scale (12/14/16/18/24/32) |
| `weight-hierarchy` | Bold headings (600-700), Regular body (400), Medium labels (500) |
| `color-semantic` | Semantic tokens (primary, secondary, error, surface, on-surface) |
| `color-dark-mode` | Desaturated/lighter tonal variants; never simply inverted |
| `color-accessible-pairs` | Verify all fg/bg pairs meet 4.5:1 (AA) or 7:1 (AAA) |
| `truncation` | Prefer wrapping; when truncating use ellipsis + tooltip |
| `number-tabular` | Tabular/monospaced figures for data columns, prices, timers |

### Priority 7: Animation (MEDIUM)

| Rule | Standard |
|------|----------|
| `duration-timing` | 150-300ms micro; <=400ms complex; never >500ms |
| `transform-only` | Animate transform/opacity only; never width/height/top/left |
| `loading-states` | Skeleton/shimmer when loading >300ms |
| `motion-meaning` | Every animation must express cause-effect, not just decoration |
| `state-transition` | State changes animate smoothly, never snap |
| `spring-physics` | Prefer spring curves over cubic-bezier for natural feel |
| `interruptible` | User tap/gesture cancels in-progress animation immediately |
| `no-blocking` | Never block user input during animation |
| `stagger-sequence` | Stagger list entrance 30-50ms per item |
| `layout-shift-avoid` | Animations must not cause reflow or CLS |

### Priority 8: Forms & Feedback (MEDIUM)

| Rule | Standard |
|------|----------|
| `input-labels` | Visible label per input (not placeholder-only) |
| `error-placement` | Error below the related field |
| `submit-feedback` | Loading then success/error state on submit |
| `required-indicators` | Mark required fields (asterisk) |
| `empty-states` | Helpful message and action when no content |
| `toast-dismiss` | Auto-dismiss toasts 3-5s; aria-live="polite" |
| `confirmation-dialogs` | Confirm before destructive actions |
| `inline-validation` | Validate on blur, not keystroke |
| `progressive-disclosure` | Reveal complex options progressively |
| `error-recovery` | Error messages include cause + how to fix + recovery path |
| `multi-step-progress` | Step indicator or progress bar; allow back navigation |
| `focus-management` | After submit error, auto-focus first invalid field |

### Priority 9: Navigation (HIGH)

| Rule | Standard |
|------|----------|
| `bottom-nav-limit` | Max 5 items; labels with icons |
| `back-behavior` | Predictable and consistent; preserve scroll/state |
| `deep-linking` | All key screens reachable via URL |
| `nav-label-icon` | Both icon and text label; icon-only harms discoverability |
| `nav-state-active` | Current location visually highlighted |
| `modal-escape` | Clear close/dismiss affordance |
| `search-accessible` | Easily reachable; provide recent/suggested queries |
| `breadcrumb-web` | Use breadcrumbs for 3+ level deep hierarchies |
| `state-preservation` | Navigating back restores scroll, filters, input |
| `adaptive-nav` | Large screens (>=1024px) prefer sidebar; small use bottom/top |

### Priority 10: Charts & Data (LOW)

| Rule | Standard |
|------|----------|
| `chart-type-match` | Trend=line, comparison=bar, proportion=pie/donut |
| `accessible-colors` | Supplement color with patterns/shapes |
| `data-table` | Provide table alternative for screen readers |
| `legend-visible` | Always show legend near chart |
| `tooltip-on-interact` | Hover (web) or tap (mobile) shows exact values |
| `responsive-chart` | Reflow/simplify on small screens |
| `empty-data-state` | "No data yet" + guidance, not blank chart |
| `no-pie-overuse` | Avoid pie/donut for >5 categories; use bar chart |

---

## Part 3: React & Next.js Performance Patterns

Source: Vercel react-best-practices (vercel-labs/agent-skills)

Apply these when writing, reviewing, or refactoring React/Next.js code.

### Category 1: Eliminating Waterfalls (CRITICAL)

- Check cheap sync conditions before awaiting remote values
- Move `await` into branches where actually used (defer-await)
- Use `Promise.all()` for independent async operations
- Start promises early, await late in API routes
- Use `<Suspense>` boundaries to stream content progressively

### Category 2: Bundle Size (CRITICAL)

- Import directly from modules; avoid barrel files (`index.ts` re-exports)
- Use `next/dynamic` or `React.lazy` for heavy components
- Defer third-party scripts (analytics, logging) until after hydration
- Load modules conditionally only when features are activated
- Preload on hover/focus for perceived speed

### Category 3: Server-Side Performance (HIGH)

- Use `React.cache()` for per-request deduplication
- Use LRU cache for cross-request caching
- Avoid duplicate serialization in RSC props
- Hoist static I/O (fonts, logos) to module level
- Never use module-level mutable state in RSC/SSR
- Minimize data passed to client components
- Restructure components to parallelize server fetches
- Use `after()` for non-blocking post-response operations

### Category 4: Client-Side Data (MEDIUM-HIGH)

- Use SWR or React Query for automatic request deduplication
- Deduplicate global event listeners
- Use passive listeners for scroll events
- Version and minimize localStorage data

### Category 5: Re-render Optimization (MEDIUM)

- Don't subscribe to state only used in callbacks
- Extract expensive work into memoized components
- Hoist default non-primitive props outside components
- Use primitive dependencies in effects/memos
- Subscribe to derived booleans, not raw store values
- Derive state during render, not in effects
- Use functional setState for stable callbacks
- Pass function to useState for expensive initial values
- Don't define components inside other components
- Use `startTransition` for non-urgent updates
- Use `useDeferredValue` for expensive renders
- Use refs for transient high-frequency values

### Category 6: Rendering Performance (MEDIUM)

- Animate wrapper divs, not SVG elements directly
- Use `content-visibility: auto` for long off-screen lists
- Extract static JSX outside component functions
- Reduce SVG coordinate precision
- Use ternary (`? :`) not `&&` for conditional rendering
- Prefer `useTransition` over manual loading state
- Use React DOM resource hints for preloading

### Category 7: JavaScript Performance (LOW-MEDIUM)

- Batch DOM/CSS changes via classes or cssText
- Build Map/Set for repeated lookups (O(1) vs O(n))
- Cache object properties and function results in loops
- Combine multiple filter/map into single loop
- Check array length before expensive operations
- Return early from functions
- Hoist RegExp creation outside loops
- Use `requestIdleCallback` for non-critical deferred work

---

## Workflow

### Mode: Wireframe (`wireframe`)

1. Confirm what's being explored (screen, flow, or nav pattern), constraints
   (mobile/desktop, greenfield/existing), the axis of variation (layout, density,
   step count, CTA placement), and the count (3 minimum, 5-6 ceiling)
2. Stay strictly low-fidelity: greyscale only, system sans, labeled boxes for content
   areas, striped placeholders for imagery, skeleton or ipsum copy -- no brand color
   or real content yet
3. Produce 3+ variations differing on the established axis, ordered from most
   by-the-book to most novel; write down each variation's distinguishing structure
   before sketching it
4. Annotate 2-4 points per variation, placed next to it rather than in a separate doc
5. Capture the chosen direction (or hybrid), what was explicitly rejected, and any
   new constraints surfaced; hand off to Mode: Build or Mode: Make a Prototype for
   the hi-fi follow-up

### Mode: Build (default)

1. **Design Thinking**: Establish bold aesthetic direction (see Design Thinking section)
2. **Design System**: Define tokens -- colors, typography, spacing, shadows, radii
3. **Component Architecture**: Plan component hierarchy and data flow
4. **Implementation**: Build with production-grade code following all guidelines
5. **Self-Review Pass**: Verify against UX Checklist priorities 1-5 (CRITICAL + HIGH)
6. **Accessibility Audit**: Run through Priority 1 checklist completely, computing
   every contrast pair with `.claude/skills/frontend-design/scripts/wcag-contrast.py` (see `color-contrast` above)
7. **Independent re-check for real brand colors**: if the deliverable uses
   specific, non-default brand colors (not plain black/white/gray), a
   same-agent self-review is the weakest point in this workflow -- the author
   is anchored on their own choices. Where feasible, have a fresh-context
   pass (a separate `a11y`-mode invocation, or the `frontend-designer` agent's
   Accessibility Audit mode run as its own dispatch rather than inline) verify
   contrast independently before calling the work done, mirroring the blind
   accessibility-judge pattern that caught the 2026-07-07 regression a
   same-pass self-review missed. For a full pre-ship gate, run Mode: Polish
   Pass instead of this accessibility-only check: it dispatches all four
   review dimensions (accessibility, ai-slop, hierarchy-rhythm,
   interaction-states) in parallel rather than accessibility alone.

### Mode: Make a Prototype (`prototype`)

Distinct from Mode: Build's single final artifact: this builds an interactive,
clickable version of a direction that is already chosen (from Mode: Wireframe, a
prior Build, or an existing design).

1. Confirm the flow (screens, entry point, goal state), fidelity, device frame, and
   the design system to build against; if none exists, run Design Thinking first
2. Map screens and state as a comment block before building: the screen list with
   transitions, and the state variables that drive them
3. Build screen-by-screen with hi-fi visuals matching the design system and
   plausible real content (not Lorem ipsum); one primary CTA per screen
4. Wire every interaction, not just the happy path: navigation, form validation
   (empty/invalid/valid), loading states with faked latency, success/error
   feedback, and visible state changes
5. Persist meaningful state (current screen, form drafts) across reload via
   `localStorage`; verify the full flow by walking it, including keyboard
   navigation and focus behavior
6. Summarize what flows work, what's faked (e.g., a `setTimeout` stand-in for a
   real request), and what's open for the user to decide

### Mode: Generate Variations (`variations`)

Produces hi-fi options across an *already-established* direction, for comparison;
use Mode: Wireframe instead for pre-direction, low-fidelity exploration.

1. Confirm what's being varied (screen, component, or flow), the existing design
   context to root variations in (unless told to break free of it), the count
   (default 3, 5-6 ceiling), and any axis preference
2. Pick 2-4 axes to vary across (visual treatment, layout, interaction model,
   density, tone) and specify each variation concretely before building it --
   distinct palette, type pairing, and layout skeleton per variation
3. Build in order from by-the-book (safe, matches existing conventions) to refined
   (one or two dimensions pushed further) to novel (a genuinely different take);
   cover both ends rather than clustering near the safe end
4. Present all variations in a single file or canvas -- never scattered
   `v1.html`/`v2.html`/`v3.html`
5. Caption each variation in one sentence and end with a clear recommendation; the
   user decides, but state an opinion rather than treating all options as equal

### Mode: Review (`review [--focus <dimension>]`)

1. Read the target files
2. Check against **Aesthetics Guidelines** -- is the design distinctive or generic?
3. Run through **UX Checklist** priorities 1-5 (CRITICAL and HIGH)
4. Check **Performance Patterns** if React/Next.js
5. Output findings as `file:line - [PRIORITY] rule-name: description`

`--focus` scopes a single invocation to one dimension instead of the full review,
so it can run as one of four concurrent dispatches under Mode: Polish Pass:

| `--focus` value | Scope |
| --- | --- |
| `accessibility` | Priority 1 (Accessibility) checklist, completely |
| `ai-slop` | Anti-Patterns section + the AI-Slop Detection Rubric (see `frontend-designer.md`) |
| `hierarchy-rhythm` | Hierarchy & Rhythm section (Part 1) + Priority 6 rows bearing on hierarchy (`weight-hierarchy`, `font-scale`) |
| `interaction-states` | Priority 2 (Touch & Interaction) + the `state-clarity`/`elevation-consistent` rows of Priority 4 (Style Selection) |

When called with `--focus`, report every finding including low-confidence and
low-severity ones, each with a confidence and severity estimate (see Mode: Polish
Pass, step 3); the aggregation step, not this dispatch, filters and prioritizes.

### Mode: Polish Pass (Parallel Review)

**Orchestrator-only**: this mode is run from the calling session, which has the
Agent tool, not from inside a single `frontend-designer` invocation -- that agent's
tool set has no Agent tool for sub-dispatch. See `.claude/rules/design.md`,
"Parallel polish-pass review dispatch," for the full orchestrator procedure.

1. Confirm scope: the file or component that just finished a Build or Fix pass
2. Dispatch `frontend-designer` four times concurrently, in a single message, one
   call per `review --focus` value: `accessibility`, `ai-slop`, `hierarchy-rhythm`,
   `interaction-states` -- each targeting the same file(s)
3. Instruct every dispatch to report every finding, including low-confidence and
   low-severity ones, each tagged with a confidence and severity estimate --
   coverage over filtering; prioritization happens in step 4, not inside any one
   dispatch
4. Wait for all four, merge duplicate findings across dimensions (e.g., a removed
   focus ring surfacing from both `accessibility` and `interaction-states`), and
   group into Blockers (accessibility/WCAG failures), Quality issues (AI slop,
   broken hierarchy, missing interaction states), and Polish recommendations
   (subtler tone/spacing suggestions)
5. Fix blockers and quality issues; report the aggregated, deduped, prioritized
   result to the user rather than four separate agent transcripts

### Mode: Accessibility (`a11y`)

1. Read the target files
2. Run through Priority 1 (Accessibility) completely
3. Check Priority 2 (Touch & Interaction) for interactive elements
4. Check Priority 8 (Forms & Feedback) for any form elements
5. Verify color contrast (computed via `.claude/skills/frontend-design/scripts/wcag-contrast.py` for every
   pairing found in the file, including hover/active/focus overrides), focus
   states, aria attributes, keyboard navigation
6. Output findings grouped by severity, citing the script's printed ratio for
   any contrast finding

### Mode: Performance (`perf`)

1. Read the target files
2. Run through Priority 3 (Performance) from UX Checklist
3. Apply React/Next.js Performance Patterns (Part 3) if applicable
4. Check bundle size, waterfall, and rendering patterns
5. Output findings with estimated impact level

### Mode: Fix (`fix <file>`)

1. Read the specified file
2. Identify UX/accessibility/performance issues
3. Apply fixes following the guidelines
4. Run the project's linter to verify no regressions
5. Present summary of changes

## Pre-Delivery Checklist

Before delivering any frontend work:

- [ ] Design direction is clear and intentional (not generic)
- [ ] Color contrast meets WCAG AA (4.5:1 text, 3:1 large text) -- **computed via
      `.claude/skills/frontend-design/scripts/wcag-contrast.py`, not estimated**, for every color pairing used
      (resting, hover, active, focus); paste the script's PASS/FAIL lines as
      evidence, do not just check the box
- [ ] All interactive elements have visible focus states
- [ ] Touch targets >= 44x44px
- [ ] No horizontal scroll on mobile
- [ ] `prefers-reduced-motion` respected
- [ ] No emoji used as structural icons
- [ ] Semantic color tokens used (no raw hex in components)
- [ ] Images have dimensions/aspect-ratio set (CLS prevention)
- [ ] Forms have visible labels, error placement below fields
- [ ] Tested at 375px width and landscape orientation
- [ ] Dark mode contrast verified independently

## Reference catalogs

Static design catalogs live in [`context/`](context/README.md), extracted from
`ui-ux-pro-max-skill` (MIT). Load the one that fits the task instead of inventing
options: `styles.csv` (84 style families with palettes and prompt keywords),
`typography.csv` (74 font pairings with imports), `charts.csv` (25 chart types
with a11y grades), `ui-reasoning.csv` (161 product-type UX decision rules), and
`app-interface.csv` (30 interface Do/Don't rules with code). See
[`context/README.md`](context/README.md) for the full index and usage.

## Attribution

This skill synthesizes guidance from:
- [Anthropic Skills: frontend-design](https://github.com/anthropics/skills) -- Creative direction, anti-slop aesthetics
- [Vercel Labs: react-best-practices](https://github.com/vercel-labs/agent-skills) -- 69 React/Next.js performance rules (MIT)
- [nextlevelbuilder: ui-ux-pro-max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) -- 99 UX guidelines, accessibility, interaction patterns
- [Trystan-SA: claude-design-system-prompt](https://github.com/Trystan-SA/claude-design-system-prompt) (MIT, commit `3c3ddb0`) -- Anti-Patterns detect-and-replace format and the card/imagery entries; the Wireframe, Make a Prototype, and Generate Variations workflow modes; the Polish Pass parallel-review structure; the greenfield 4-directions aesthetic protocol
