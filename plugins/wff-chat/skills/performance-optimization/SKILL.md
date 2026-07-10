---
name: performance-optimization
description: Optimize application performance after measuring. Use when performance requirements exist, when you suspect performance regressions, or when Core Web Vitals or load times need improvement. Use when profiling reveals bottlenecks that need fixing. Triggers on performance, optimize, slow, latency, Core Web Vitals, LCP, INP, CLS, N+1, profiling, bundle size, performance budget.
---

# Performance Optimization

> **Ported skill.** Adapted from [`addyosmani/agent-skills`](https://github.com/addyosmani/agent-skills/blob/main/skills/performance-optimization/SKILL.md)
> (MIT License), commit `a5f0b17`, retrieved 2026-06-18. Adapted to our standards:
> em-dashes removed, the upstream `references/` pointers replaced with inline content,
> the verbose responsive-image block condensed. Examples are illustrative (TS/React);
> the measure-first discipline is language-agnostic. For Python services, profile with
> `cProfile`/`py-spy` and check DB queries before changing import styles.

## Overview

Measure before optimizing. Performance work without measurement is guessing, and
guessing leads to premature optimization that adds complexity without improving what
matters. Profile first, identify the actual bottleneck, fix it, measure again. Optimize
only what measurements prove matters.

## When to Use

- Performance requirements exist in the spec (load time budgets, response time SLAs)
- Users or monitoring report slow behavior
- Core Web Vitals scores are below thresholds
- You suspect a change introduced a regression
- Building features that handle large datasets or high traffic

**When NOT to use:** Do not optimize before you have evidence of a problem. Premature
optimization adds complexity that costs more than the performance it gains.

## Core Web Vitals Targets

| Metric | Good | Needs Improvement | Poor |
|--------|------|-------------------|------|
| **LCP** (Largest Contentful Paint) | <= 2.5s | <= 4.0s | > 4.0s |
| **INP** (Interaction to Next Paint) | <= 200ms | <= 500ms | > 500ms |
| **CLS** (Cumulative Layout Shift) | <= 0.1 | <= 0.25 | > 0.25 |

## The Optimization Workflow

```text
1. MEASURE  -> Establish baseline with real data
2. IDENTIFY -> Find the actual bottleneck (not assumed)
3. FIX      -> Address the specific bottleneck
4. VERIFY   -> Measure again, confirm improvement
5. GUARD    -> Add monitoring or tests to prevent regression
```

### Step 1: Measure

Two complementary approaches, use both:

- **Synthetic (Lighthouse, DevTools Performance tab):** Controlled conditions,
  reproducible. Best for CI regression detection and isolating specific issues.
- **RUM (web-vitals library, CrUX):** Real user data in real conditions. Required to
  validate that a fix actually improved user experience.

```typescript
// Frontend RUM: Web Vitals library in code
import { onLCP, onINP, onCLS } from 'web-vitals';
onLCP(console.log);
onINP(console.log);
onCLS(console.log);

// Backend: simple timing around a suspect call
console.time('db-query');
const result = await db.query(/* ... */);
console.timeEnd('db-query');
```

### Where to Start Measuring

Use the symptom to decide what to measure first:

```text
What is slow?
|-- First page load
|   |-- Large bundle? --> Measure bundle size, check code splitting
|   |-- Slow server response? --> Measure TTFB in the Network waterfall
|   |   |-- Waiting (server) long? --> Profile backend, check queries and caching
|   |   `-- TCP/TLS long? --> Enable HTTP/2, check edge deployment, keep-alive
|   `-- Render-blocking resources? --> Check waterfall for blocking CSS/JS
|-- Interaction feels sluggish
|   |-- UI freezes on click? --> Profile main thread, look for long tasks (>50ms)
|   `-- Animation jank? --> Check layout thrashing, forced reflows
|-- Page after navigation
|   |-- Data loading? --> Measure API response times, check for waterfalls
|   `-- Client rendering? --> Profile component render time, check for N+1 fetches
`-- Backend / API
    |-- Single endpoint slow? --> Profile database queries, check indexes
    |-- All endpoints slow? --> Check connection pool, memory, CPU
    `-- Intermittent slowness? --> Check lock contention, GC pauses, external deps
```

### Step 2: Identify the Bottleneck

**Frontend:**

| Symptom | Likely Cause | Investigation |
|---------|-------------|---------------|
| Slow LCP | Large images, render-blocking resources, slow server | Network waterfall, image sizes |
| High CLS | Images without dimensions, late-loading content, font shifts | Layout shift attribution |
| Poor INP | Heavy JavaScript on main thread, large DOM updates | Long tasks in Performance trace |
| Slow initial load | Large bundle, many network requests | Bundle size, code splitting |

**Backend:**

| Symptom | Likely Cause | Investigation |
|---------|-------------|---------------|
| Slow API responses | N+1 queries, missing indexes, unoptimized queries | Database query log |
| Memory growth | Leaked references, unbounded caches, large payloads | Heap snapshot analysis |
| CPU spikes | Synchronous heavy computation, regex backtracking | CPU profiling |
| High latency | Missing caching, redundant computation, network hops | Trace requests through the stack |

### Step 3: Fix Common Anti-Patterns

#### N+1 Queries (Backend)

```typescript
// BAD: N+1, one query per task for the owner
const tasks = await db.tasks.findMany();
for (const task of tasks) {
  task.owner = await db.users.findUnique({ where: { id: task.ownerId } });
}

// GOOD: single query with join/include
const tasks = await db.tasks.findMany({ include: { owner: true } });
```

#### Unbounded Data Fetching

```typescript
// BAD: fetch all records
const allTasks = await db.tasks.findMany();

// GOOD: paginated with limits
const tasks = await db.tasks.findMany({
  take: 20,
  skip: (page - 1) * 20,
  orderBy: { createdAt: 'desc' },
});
```

#### Image Optimization (Frontend)

Give every image explicit `width`/`height` (prevents CLS). For the LCP image use
`fetchpriority="high"` and modern formats (AVIF/WebP) with `srcset`/`sizes` for
resolution switching; use a `<picture>` with `media` queries when the crop should differ
per breakpoint. Below-the-fold images get `loading="lazy"` and `decoding="async"`.

```html
<!-- BAD: no dimensions, no format optimization -->
<img src="/hero.jpg" />

<!-- GOOD: LCP image, prioritized, responsive -->
<img src="/hero-1200.webp" width="1200" height="600" fetchpriority="high"
     srcset="/hero-800.webp 800w, /hero-1200.webp 1200w, /hero-1600.webp 1600w"
     sizes="(max-width: 1200px) 100vw, 1200px" alt="Hero image description" />

<!-- GOOD: below-the-fold image, lazy -->
<img src="/content.webp" width="800" height="400" loading="lazy" decoding="async"
     alt="Content image description" />
```

#### Unnecessary Re-renders (React)

```tsx
// BAD: new object every render, forces children to re-render
function TaskList() {
  return <TaskFilters options={{ sortBy: 'date', order: 'desc' }} />;
}

// GOOD: stable reference, plus memoization where measured to help
const DEFAULT_OPTIONS = { sortBy: 'date', order: 'desc' } as const;
const TaskItem = React.memo(function TaskItem({ task }: Props) {
  return <div>{/* expensive render */}</div>;
});
function TaskStats({ tasks }: Props) {
  const stats = useMemo(() => calculateStats(tasks), [tasks]);
  return <div>{stats.completed} / {stats.total}</div>;
}
```

#### Large Bundle Size

```typescript
// Modern bundlers (Vite, webpack 5+) tree-shake named imports automatically when the
// dependency ships ESM and is marked `sideEffects: false`. Profile before changing
// import styles; the real gains come from splitting and lazy loading.

const ChartLibrary = lazy(() => import('./ChartLibrary'));   // heavy, rarely used
const SettingsPage = lazy(() => import('./pages/Settings')); // route-level split

function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <SettingsPage />
    </Suspense>
  );
}
```

#### Missing Caching (Backend)

```typescript
// Cache frequently-read, rarely-changed data with a TTL
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes
let cachedConfig: AppConfig | null = null;
let cacheExpiry = 0;

async function getAppConfig(): Promise<AppConfig> {
  if (cachedConfig && Date.now() < cacheExpiry) return cachedConfig;
  cachedConfig = await db.config.findFirst();
  cacheExpiry = Date.now() + CACHE_TTL;
  return cachedConfig;
}

// HTTP caching: long max-age + content-hashed filenames for static assets
app.use('/static', express.static('public', { maxAge: '1y', immutable: true }));
res.set('Cache-Control', 'public, max-age=300'); // API response, 5 minutes
```

## Performance Budget

Set budgets and enforce them in CI:

```text
JavaScript bundle: < 200KB gzipped (initial load)
CSS: < 50KB gzipped
Images: < 200KB per image (above the fold)
Fonts: < 100KB total
API response time: < 200ms (p95)
Time to Interactive: < 3.5s on 4G
Lighthouse Performance score: >= 90
```

```bash
npx bundlesize --config bundlesize.config.json   # bundle size check
npx lhci autorun                                  # Lighthouse CI
```

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "We will optimize later" | Performance debt compounds. Fix obvious anti-patterns now, defer micro-optimizations. |
| "It is fast on my machine" | Your machine is not the user's. Profile on representative hardware and networks. |
| "This optimization is obvious" | If you did not measure, you do not know. Profile first. |
| "Users will not notice 100ms" | Research shows 100ms delays impact conversion rates. Users notice more than you think. |
| "The framework handles performance" | Frameworks prevent some issues but cannot fix N+1 queries or oversized bundles. |

## Red Flags

- Optimization without profiling data to justify it
- N+1 query patterns in data fetching
- List endpoints without pagination
- Images without dimensions, lazy loading, or responsive sizes
- Bundle size growing without review
- No performance monitoring in production
- `React.memo` and `useMemo` everywhere (overusing is as bad as underusing)

## Verification

After any performance-related change:

- [ ] Before and after measurements exist (specific numbers)
- [ ] The specific bottleneck is identified and addressed
- [ ] Core Web Vitals are within "Good" thresholds (frontend work)
- [ ] Bundle size has not increased significantly
- [ ] No N+1 queries in new data fetching code
- [ ] Performance budget passes in CI (if configured)
- [ ] Existing tests still pass (optimization did not break behavior)
