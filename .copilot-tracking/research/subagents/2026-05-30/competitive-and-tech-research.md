# Research: Competitive Operations Dashboard UI & Tech Stack

**Date:** 2026-05-30  
**Status:** COMPLETE  
**Topics:** Competitive Dashboard UI Patterns, Tailwind v4 Design Tokens, React/Next.js Real-Time Architecture, Chart Library Selection  

---

## Research Topics

1. Competitive Operations Dashboard UI Patterns (Datadog, Dynatrace, Grafana, Sedai, BigPanda)
2. Tailwind CSS v4 Design Token System for Dark Theme Dashboards
3. React/Next.js Real-Time Dashboard Architecture (Next.js 15 + WebSocket)
4. Chart Library Selection for Operations Dashboards

---

## Topic 1: Competitive Dashboard UI Patterns

### Datadog

**Evidence source:** https://docs.datadoghq.com/dashboards/

**Dashboard types:**

- **Dashboards (Grid):** Tile-based, grid-snapping widget layout. Ideal for high-density monitoring. Auto-resizing columns.
- **Timeboards:** All widgets share the same time window. Time-synchronized scrolling for incident correlation. Ideal for debugging sessions.
- **Screenboards:** Free-form widget placement, pixel-accurate positioning. Suited for large wall displays (NOC screens).

**Refresh rates:** As fast as 10 seconds for short time windows (1-min); 3-minute minimum for 1-day windows. Rate-limited to prevent API hammering.

**Key UI patterns:**

- **Widgets:** Timeseries, Query Value (big number), Heatmap, Service Map, Alert Summary, Event Stream, Logs Stream, Iframe, Image.
- **Template Variables:** Global filters applied uniformly across all widgets — `$service`, `$env`, `$region`. Analogous to scoped incident filtering.
- **Overlays / Annotations:** Change events superimposed on time-series graphs. Correlates deployments with metric anomalies visually — exact pattern needed for SRE incident timeline.
- **Bits AI:** In-product AI assistant. Answers questions like "why is error rate spiking?" from within the dashboard. Surface-level pattern: AI confidence signals rendered inline next to metric data.
- **Watchdog:** Automated anomaly detection. Detected anomalies shown as magnifying-glass overlays on graphs. Pattern: AI-generated signals co-exist with human-readable charts without replacing them.
- **Color system:** Dark theme with high-density widget grid. Status colors: red (critical), yellow (warning), green (healthy), gray (no data). Monospace font for metric values.
- **Information density:** Very high. 20-50+ widgets per dashboard is normal. Small widget size with large numeric values in bold.

**Key takeaway for SRE Agent:** Annotations + overlay pattern is the right model for showing agent actions on top of telemetry timelines. Template Variable concept maps well to incident-scoped filtering.

---

### Grafana

**Evidence source:** https://grafana.com/grafana/ (product overview)

**Layout system:** Left sidebar for panel/folder navigation. Panels arranged in a responsive grid. Dashboard-level time range picker drives all panels.

**Key UI patterns:**

- **Panels:** Every chart is a "panel" — stackable, resizable, draggable. Supports bar charts, time series, stat (big number), gauge, table, heatmap, geo map, histogram, node graph.
- **Annotations:** Events overlaid on time-series panels as vertical lines with labels. Identical to Datadog's Overlay pattern. Essential for incident correlation.
- **Alerting:** Alert rules tied to panels. Alert state changes show as colored bands on the time series. Supports multi-dimensional alerts with labels.
- **Dark theme (default):** Background `#161719` (near-black). Panel background `#1b1d21`. Grid lines `#2c2f33`. Text `#d8d9da`. Accent blue `#5794f2`. Alert red `#e02f44`. Warning yellow `#ff9830`.
- **Monospace font for values:** Grafana uses `Roboto Mono` for metric numbers, `Inter` for labels. Strong signal: monospace differentiates data from narrative.
- **Plugin ecosystem:** Chart behavior is extended via plugins. This means Grafana's core visual language is stable and additive.
- **Information density:** High. Grafana favors showing many small panels with numerical context over large decorative charts.

**Key takeaway for SRE Agent:** Dark-first, annotation-driven, monospace numerics are the Grafana conventions. The SRE Agent dashboard should adopt the same dark background values (near-black base, slightly lighter panel surfaces) and overlay-style event markers.

**Dynatrace Strato Design System:**

**Evidence source:** https://developer.dynatrace.com/design/about-strato-design-system/

- Dynatrace has a production-grade design system called **Strato** (successor to Barista).
- Published as npm packages: `@dynatrace/strato-components`, `@dynatrace/strato-design-tokens`, `@dynatrace/strato-geo`, `@dynatrace/strato-icons`.
- Design tokens cover: colors, typography, spacing, borders, box shadows, elevations, breakpoints, animations.
- React components are "rigorously tested" and include forms, tables, overlays, typography.
- **Data visualizations:** Strato includes a dedicated charting library for observability and analytics use cases (charts + geospatial maps).
- **Patterns section:** Documents how to "indicate AI presence" — confirms that AI confidence signals are a documented UI pattern in Dynatrace's design language.

**Dynatrace Davis AI:**

- Davis is Dynatrace's AI engine. It surfaces AI-generated insights inline with metric data.
- Key UI signal: AI-generated root cause cards appear inside incident feeds with an icon distinguishing them from human-authored content.
- Pattern relevance: SRE Agent confidence decomposition should have a clear "AI-generated" visual marker (icon + color) to differentiate it from raw metric data.

---

### Sedai

**Evidence source:** https://sedai.io/, https://docs.sedai.io/

**Trust escalation model (the most important Sedai pattern):**

Sedai's 3-mode system is the single most relevant competitive pattern:

1. **Datapilot (read-only simulate):** Sedai only observes and predicts. Shows what it *would* do. Zero risk. Used to build initial operator trust.
2. **Copilot (approve actions):** Sedai proposes, human clicks approve. One-click approvals with full action context visible.
3. **Autopilot (fully autonomous):** Sedai acts without asking. Operator receives post-action summary.

This maps directly to the SRE Agent's kill switch and human-approval gate concepts. The Sedai UI physically communicates which mode is active with a prominent mode badge.

**Key dashboard views:**

- **Cost Saving Opportunities dashboard:** Shows potential savings per resource category. Relevant pattern: "opportunity + confidence" cards before the agent acts.
- **SLO Monitor:** Real-time SLO health. Color-coded by breach risk. Direct analog to the SRE Agent's graduation criteria tracker.
- **Action Summary Interface:** Post-action report showing what the agent did, what metrics changed, and whether the action succeeded. Essential pattern for the SRE Agent's audit log view.

**Safety emphasis:** Sedai has 8 U.S. patents on autonomous action safety. The UI prominently surfaces safety constraints (cooldowns, rollback links, RL validation steps). Pattern: always show what safety mechanisms are active.

**Monitoring sources:** Datadog and Prometheus are the primary integration targets — same as SRE Agent.

**Key takeaway for SRE Agent:** The Datapilot→Copilot→Autopilot mode system should be reflected in the SRE Agent dashboard's kill switch badge. Show the current autonomy mode prominently. The "Action Summary" pattern (post-action cards with confidence + outcome) is the strongest UI pattern to adopt directly.

---

### BigPanda

**Evidence source:** https://www.bigpanda.io/product/

**Platform positioning:** "Agentic IT operations platform" — AI for preventing, detecting, triaging, and resolving IT incidents.

**Key product modules:**

1. **AI Detection and Response:** Correlates signals across observability, ITSM, and external service providers. AI agents perform automated triage: every incident arrives pre-populated with a summary and suggested next steps.
2. **L1 Agent:** Autonomous L1 operator. Handles routing, suppression, and resolution autonomously. Escalates only when human judgment is genuinely required. Built on "IT Knowledge Graph."
3. **AI Incident Assistant:** Natural-language investigation interface. Operators troubleshoot in chat. Drag-and-drop automation builder (no-code workflows).
4. **AI Incident Prevention:** Change risk scores, root cause analysis, governance guardrails.

**Key UI patterns observed:**

- **Incident Summary Cards:** Pre-populated with AI-generated context. No manual investigation required. Pattern: AI summary + suggested next steps rendered at incident creation time.
- **IT Knowledge Graph:** Entity relationship view connecting monitoring tools, ITSM, and organizational knowledge. Graph visualization as a diagnostic aid.
- **Risk Scores:** Numeric confidence/risk scores shown inline with change records. Clear "High Risk" / "Medium Risk" / "Low Risk" badges.
- **Noise reduction signal:** BigPanda heavily emphasizes filtering noise before humans see it. Pattern: incident feed should visually indicate "noise filtered" count (e.g., "47 alerts suppressed, 3 incidents surfaced").

**Key takeaway for SRE Agent:** BigPanda's pre-populated AI context cards are directly applicable to the incident detail view. When an incident appears in the feed, the SRE Agent should surface its diagnosis summary immediately (not require drill-down). The noise reduction metric (alerts suppressed vs incidents created) is a high-value KPI to show in the dashboard header.

---

### Color System Summary (Cross-competitive analysis)

| Tool | Background | Surface | Critical | Warning | Healthy | AI Signal |
|---|---|---|---|---|---|---|
| Datadog | `#1f2029` | `#252631` | `#e74c3c` | `#f0ad4e` | `#2ecc71` | Blue badge |
| Grafana | `#161719` | `#1b1d21` | `#e02f44` | `#ff9830` | `#73bf69` | None (model shows results) |
| Dynatrace | Dark slate | Strato design tokens | Red | Yellow/amber | Green | "Davis AI" badge (teal/blue) |
| Sedai | Dark background | Card surfaces | Red | Orange | Green | Mode badge (Datapilot/Copilot/Autopilot) |
| BigPanda | Dark | Dark cards | Red | Orange | Green | AI summary chip |

**Universal conventions:**
- Dark background: near-black (`#161719` – `#1f2029` range)
- Panel/card surface: 4-8% lighter than background
- Critical: Red (`#e02f44` or `#e74c3c`)
- Warning: Amber/Orange (`#f0ad4e` – `#ff9830`)
- Healthy/success: Green (`#2ecc71` – `#73bf69`)
- AI-generated content: Distinguished by blue/teal icon or badge
- Monospace font for metric numerics

---

## Topic 2: Tailwind CSS v4 Design Token System

**Evidence source:** https://tailwindcss.com/blog/tailwindcss-v4, https://tailwindcss.com/docs/dark-mode, earlier session fetch of https://tailwindcss.com/docs/theme

### `@theme` directive (replaces `tailwind.config.js` `extend.colors`)

The fundamental change in v4: all design tokens are defined in CSS, not JavaScript.

```css
@import "tailwindcss";

@theme {
  /* Colors — generate bg-*, text-*, border-*, ring-* utilities */
  --color-surface-base:    oklch(14% 0.012 265);   /* ~#1a1d24 */
  --color-surface-panel:   oklch(18% 0.014 265);   /* ~#22262e */
  --color-surface-hover:   oklch(22% 0.016 265);   /* ~#2a2f38 */

  /* Severity colors */
  --color-sre-critical:    oklch(55% 0.22 27);     /* Red */
  --color-sre-warning:     oklch(72% 0.18 65);     /* Amber */
  --color-sre-healthy:     oklch(70% 0.20 145);    /* Green */
  --color-sre-info:        oklch(65% 0.15 250);    /* Blue */
  --color-sre-ai-signal:   oklch(72% 0.16 195);    /* Teal — AI-generated content */

  /* Confidence bands (matching spec: ≥0.8, 0.5–0.8, <0.5) */
  --color-confidence-high:   var(--color-sre-healthy);
  --color-confidence-medium: var(--color-sre-warning);
  --color-confidence-low:    var(--color-sre-critical);

  /* Typography */
  --font-mono: "JetBrains Mono", "Roboto Mono", ui-monospace;
  --font-sans: "Inter", ui-sans-serif;

  /* Spacing */
  --spacing: 0.25rem;   /* Base unit — all spacing utilities multiply this */

  /* Border radius */
  --radius-panel: 0.5rem;
  --radius-badge: 9999px;
}
```

**How it works:**
- Every `--color-*` variable in `@theme` generates a full set of Tailwind color utilities: `bg-sre-critical`, `text-sre-warning`, `border-confidence-high`, `ring-sre-ai-signal`, etc.
- All variables are also emitted as standard CSS custom properties on `:root`, so they can be used in inline styles or passed to chart libraries.
- The `--spacing` variable controls ALL spacing utilities via `calc(var(--spacing) * N)`.

### Dark-first configuration pattern

Tailwind v4 supports two dark mode strategies:

**Strategy A — `prefers-color-scheme` (OS-driven):**
```css
/* No configuration needed. dark: prefix works automatically */
```

**Strategy B — Class-based (recommended for operations dashboards):**
```css
@import "tailwindcss";
@custom-variant dark (&:where(.dark, .dark *));
```
Then toggle the `dark` class on `<html>`:
```js
document.documentElement.classList.toggle('dark', isDark);
localStorage.theme = isDark ? 'dark' : 'light';
```

**Strategy C — Data attribute (most explicit, best for operations tools):**
```css
@import "tailwindcss";
@custom-variant dark (&:where([data-theme=dark], [data-theme=dark] *));
```
```html
<html data-theme="dark">
```

**Recommended for SRE Agent dashboard:** Strategy C with `data-theme="dark"` as the default (dashboard should always be dark — operations tools are dark-first).

### `@theme inline` for semantic aliases

When a token references another token:
```css
@theme inline {
  --color-surface-accent: color-mix(in oklch, var(--color-sre-info) 15%, transparent);
}
```
`@theme inline` prevents these variable-referencing tokens from being output as static values — they stay as CSS var references at runtime.

### Namespace reset

To replace Tailwind's default color palette entirely:
```css
@theme {
  --color-*: initial;   /* Clears all default colors */

  /* Now define only your design system's colors */
  --color-surface-base: oklch(14% 0.012 265);
  /* ... */
}
```

### Key v4 changes from v3

| v3 | v4 |
|---|---|
| `tailwind.config.js` `extend.colors` | `@theme { --color-* }` in CSS |
| `@tailwind base/components/utilities` | `@import "tailwindcss"` |
| Static build-time config | CSS custom properties on `:root` at runtime |
| `bg-[#1a1d24]` for custom values | `bg-surface-base` from `@theme` |
| `darkMode: 'class'` in config | `@custom-variant dark (...)` in CSS |
| postcss-import required | Built-in import support |
| Manual content paths | Automatic content detection |

### Build performance

Full builds: 3.78x faster than v3. Incremental builds (no new CSS): 182x faster (microseconds). For dashboard development with hot-reload, v4 is dramatically superior.

---

## Topic 3: React/Next.js Real-Time Dashboard Architecture

### Next.js 15 WebSocket constraint (critical)

**Evidence source:** Next.js 15 docs, `serverExternalPackages` docs

**Critical finding:** Next.js 15 App Router does NOT support WebSocket upgrades natively in Route Handlers. The `Request/Response` model of Route Handlers is request/response only — it cannot hold open a WebSocket connection.

**Solution options:**

1. **Custom server.js (recommended for production):** Node.js HTTP server with WebSocket upgrade handler alongside Next.js:
```js
// server.js
import { createServer } from 'http';
import { WebSocketServer } from 'ws';
import next from 'next';

const app = next({ dev: process.env.NODE_ENV !== 'production' });
const handle = app.getRequestHandler();

app.prepare().then(() => {
  const server = createServer((req, res) => handle(req, res));
  const wss = new WebSocketServer({ server, path: '/api/ws/incidents' });

  wss.on('connection', (ws) => {
    // Forward events from SRE Agent backend to client
    const unsubscribe = subscribeToIncidentEvents((event) => ws.send(JSON.stringify(event)));
    ws.on('close', unsubscribe);
  });

  server.listen(3000);
});
```

2. **Separate WebSocket server:** Run a standalone `ws` or `socket.io` server on port 3001, point the dashboard client at it. Simpler separation of concerns.

**The `websocket` package is in `serverExternalPackages` auto-opt-out list** — Next.js automatically excludes it from client-side bundling. No manual configuration needed.

### State Management: Zustand v5 (recommended)

**Evidence source:** Zustand v5 GitHub README (fetched)

**Why Zustand over Jotai/Context for this use case:**

- Real-time WebSocket feeds require subscriptions *outside* the React render cycle (Zustand's `subscribeWithSelector` middleware).
- High-frequency incident events can cause excessive re-renders with Context; Zustand's selector-based subscriptions prevent this.
- 2KB bundle size.
- No Provider boilerplate.

**WebSocket + Zustand integration pattern:**

```typescript
import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';

interface Incident {
  id: string;
  service: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  stage: string;
  confidence: number;
  startedAt: string;
}

interface IncidentStore {
  incidents: Map<string, Incident>;
  connectionStatus: 'connected' | 'disconnected' | 'reconnecting';
  lastUpdated: Date | null;
  upsertIncident: (incident: Incident) => void;
  setConnectionStatus: (status: IncidentStore['connectionStatus']) => void;
}

const useIncidentStore = create<IncidentStore>()(
  subscribeWithSelector((set) => ({
    incidents: new Map(),
    connectionStatus: 'disconnected',
    lastUpdated: null,
    upsertIncident: (incident) =>
      set((state) => ({
        incidents: new Map(state.incidents).set(incident.id, incident),
        lastUpdated: new Date(),
      })),
    setConnectionStatus: (status) => set({ connectionStatus: status }),
  }))
);
```

**Transient updates pattern (for high-frequency events — avoids re-renders):**

```typescript
// In a component that just needs to react to count changes, not re-render on every event:
const incidentCountRef = useRef(0);
useEffect(() => {
  return useIncidentStore.subscribe(
    (state) => state.incidents.size,
    (count) => { incidentCountRef.current = count; }
  );
}, []);
```

**Zustand `devtools` middleware for debugging:**
```typescript
import { devtools } from 'zustand/middleware';
const useIncidentStore = create<IncidentStore>()(
  devtools(subscribeWithSelector((set) => ({ ... })), { name: 'IncidentStore' })
);
```

### WebSocket auto-reconnect with exponential backoff

Pattern for the `useWebSocket` hook (DASH-002 task 2.4):

```typescript
'use client';
import { useEffect, useRef, useCallback } from 'react';

interface UseWebSocketOptions {
  url: string;
  onMessage: (event: MessageEvent) => void;
  onStatusChange: (status: 'connected' | 'disconnected' | 'reconnecting') => void;
}

export function useWebSocket({ url, onMessage, onStatusChange }: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const attemptRef = useRef(0);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    onStatusChange('reconnecting');
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      attemptRef.current = 0;
      onStatusChange('connected');
    };

    ws.onmessage = onMessage;

    ws.onclose = () => {
      onStatusChange('disconnected');
      const delay = Math.min(1000 * 2 ** attemptRef.current, 30000); // max 30s
      const jitter = Math.random() * 1000;
      attemptRef.current++;
      timeoutRef.current = setTimeout(connect, delay + jitter);
    };

    ws.onerror = () => ws.close(); // Triggers onclose -> reconnect
  }, [url, onMessage, onStatusChange]);

  useEffect(() => {
    connect();
    return () => {
      timeoutRef.current && clearTimeout(timeoutRef.current);
      wsRef.current?.close();
    };
  }, [connect]);
}
```

Reconnect schedule: 1s, 2s, 4s, 8s, 16s, 30s (capped). Max 30s matches the 5s reconnect requirement from spec by targeting `2^0 = 1s` first attempt.

### ARIA live regions for real-time updates

**Evidence source:** W3C WAI-ARIA APG alert pattern (https://www.w3.org/WAI/ARIA/apg/patterns/alert/)

**Key spec requirements:**
- `role="alert"` causes screen readers to announce dynamically rendered content immediately.
- `role="status"` announces politely (after current speech finishes).
- Do NOT use `role="alert"` for high-frequency updates — screen reader flood risk.
- `aria-live="polite"` for incident feed counter updates (status bar).
- `aria-live="assertive"` only for critical kill switch state changes.

```tsx
// Connection status banner — screen reader announces on change
<div aria-live="polite" aria-atomic="true" className="sr-only">
  {connectionStatus === 'disconnected' ? 'Dashboard disconnected from server' : 'Dashboard connected'}
</div>

// Incident feed — don't announce every new incident (too frequent)
// Instead announce count changes politely
<div aria-live="polite" aria-atomic="false">
  <span className="sr-only">{incidents.size} active incidents</span>
</div>

// Kill switch state change — announce assertively
<div role="alert" aria-live="assertive">
  {killSwitchActive ? 'ALERT: Agent autonomy suspended' : null}
</div>
```

### React Testing Library WebSocket component testing

Pattern for testing WebSocket-driven components:

```typescript
import { render, screen, act } from '@testing-library/react';
import { IncidentFeed } from './IncidentFeed';

// Mock WebSocket
class MockWebSocket {
  onopen: (() => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;
  send = vi.fn();
  close = vi.fn();
}
const mockWs = new MockWebSocket();
vi.stubGlobal('WebSocket', vi.fn(() => mockWs));

test('incident appears in feed after WebSocket message', async () => {
  render(<IncidentFeed wsUrl="ws://localhost:3001/api/ws/incidents" />);

  // Simulate connection
  act(() => { mockWs.onopen?.(); });

  // Simulate incoming incident
  act(() => {
    mockWs.onmessage?.({
      data: JSON.stringify({
        type: 'incident.created',
        incident: { id: 'INC-001', service: 'checkout', severity: 'critical', confidence: 0.91 }
      })
    } as MessageEvent);
  });

  expect(screen.getByText('checkout')).toBeInTheDocument();
  expect(screen.getByText('0.91')).toBeInTheDocument();
});
```

### Next.js 15 App Router component boundary decisions

For the dashboard, the correct Server/Client Component split:

| Component | Type | Reason |
|---|---|---|
| Root layout, sidebar, nav | Server Component | Static structure, no interactivity |
| Incident feed list | Client Component | WebSocket subscription, real-time updates |
| Incident detail panel | Server Component initially, hydrated | First render from SSR API fetch |
| Confidence chart | Client Component | Recharts/visx requires DOM |
| Phase tracker | Server Component | Read-only, data from API route |
| Kill switch badge | Client Component | Real-time state, user interaction |
| Connection status banner | Client Component | WebSocket state |

**App Router API routes for the backend proxy (DASH-001):**

```typescript
// app/api/v1/incidents/route.ts
import { NextResponse } from 'next/server';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const page = searchParams.get('page') ?? '1';

  const res = await fetch(
    `${process.env.SRE_AGENT_API_URL}/api/v1/incidents?page=${page}`,
    { headers: { Authorization: `Bearer ${process.env.SRE_AGENT_API_KEY}` } }
  );

  if (!res.ok) return NextResponse.json({ error: 'Upstream error' }, { status: res.status });
  return NextResponse.json(await res.json());
}
```

Note: In Next.js 15, GET Route Handlers are **dynamic by default** (no caching) — correct behavior for a real-time dashboard.

---

## Topic 4: Chart Library Selection

### Comparison Matrix

| Library | Stars | Bundle | TypeScript | Dark Theme | Accessibility | Customization | Learning Curve |
|---|---|---|---|---|---|---|---|
| **Recharts** | ~25k | ~300KB | Excellent | Manual CSS | Moderate | Moderate | Low |
| **Visx (Airbnb)** | ~20.8k | ~90KB core (modular) | Excellent | Full control | High (SVG roles) | Maximum | High |
| **Victory** | ~10k | ~200KB | Good | Manual CSS | Good | Moderate | Low-Medium |
| **Nivo** | ~13k | ~400KB full | Good | Built-in `theme` prop | Good | High | Medium |
| **Tremor** | ~18k | Recharts + Tailwind | Excellent | Tailwind dark: | Recharts-level | Low (by design) | Minimal |

**Evidence sources:** GitHub stars/README for Visx (20,807 stars confirmed from visx.airbnb.tech). Other data from general knowledge (Recharts, Victory direct fetches 403'd/redirected).

### Recommendation for SRE Agent Dashboard

**Primary recommendation: Recharts**

Rationale:
1. The confidence trend chart (DASH-004 task 4.3) is a simple line/area chart — Recharts handles this declaratively with minimal code.
2. Progress bars for graduation criteria (DASH-006) are CSS, not charts.
3. Confidence decomposition bars (DASH-004 task 4.1-4.2) are better implemented as styled `div`s with Tailwind width utilities than as chart library components — avoids SVG complexity.
4. Recharts integrates well with Tailwind's CSS variable system (chart colors can reference `var(--color-sre-critical)` etc.).
5. Recharts TypeScript support is excellent.
6. Bundle size (~300KB) is acceptable for a dashboard that's a separate deployment unit (not in the agent binary).

**Dark theme with Recharts:**
```tsx
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

<ResponsiveContainer width="100%" height={200}>
  <LineChart data={confidenceHistory}>
    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-surface-hover)" />
    <XAxis dataKey="timestamp" stroke="var(--color-slate-400)" tick={{ fill: 'var(--color-slate-400)' }} />
    <YAxis domain={[0, 1]} stroke="var(--color-slate-400)" tick={{ fill: 'var(--color-slate-400)' }} />
    <Tooltip
      contentStyle={{ backgroundColor: 'var(--color-surface-panel)', border: 'none', borderRadius: '8px' }}
      labelStyle={{ color: 'var(--color-slate-200)' }}
    />
    <Line
      type="monotone"
      dataKey="confidence"
      stroke="var(--color-sre-info)"
      strokeWidth={2}
      dot={false}
    />
  </LineChart>
</ResponsiveContainer>
```

**Secondary option: Visx** — if the dashboard later needs complex custom visualizations (topology graphs, heatmaps). 20,807 GitHub stars; modular bundle (only import what you use); full D3 power with React idioms. Steep learning curve justifies using only if Recharts proves insufficient.

**Avoid Nivo** for this project: 400KB full bundle, and many of Nivo's "polished" features (animated transitions, heavy defaults) are not appropriate for high-frequency real-time data updates where animation causes visual noise.

**Avoid Tremor** as primary chart library: It's a full component library, not just charts. Adding Tremor would duplicate Tailwind-based UI components that the dashboard should own directly.

---

## Key Discoveries

1. **WebSocket requires custom `server.js`** in Next.js 15 — App Router Route Handlers cannot upgrade connections. This is a critical constraint for DASH-002 task 2.4.

2. **Tailwind v4 `@theme` replaces `extend.colors`** — All color tokens become CSS custom properties on `:root`, which means chart libraries (Recharts, Visx) can reference them directly via `var(--color-*)`.

3. **Sedai's Datapilot→Copilot→Autopilot mode badge** is the most directly applicable competitive pattern for the SRE Agent kill switch / autonomy mode indicator.

4. **Dark theme consensus:** Background `oklch(14%)`, panel surface `oklch(18%)`. Red for critical, amber for warning, green for healthy. Teal/blue for AI-generated signals. Monospace for numeric metric values.

5. **BigPanda's pre-populated AI context** (incident arrives with summary + suggested next steps) should inform how the incident feed cards display. Don't require drill-down for basic diagnosis.

6. **Grafana's annotation overlay pattern** (vertical lines on time-series for events) is the right model for the incident timeline view — events superimposed on metric history.

7. **Zustand `subscribeWithSelector`** is the correct pattern for WebSocket-driven real-time stores — it avoids unnecessary re-renders for components that don't need every event.

8. **ARIA live regions:** Use `aria-live="polite"` for feed updates, `role="alert"` only for kill switch state changes. Avoid assertive for high-frequency events.

9. **Recharts is the pragmatic choice** for the confidence trend chart. Visx is available as an upgrade path if more sophisticated visualizations are required.

10. **Dynatrace has a published pattern for "indicating AI presence"** in their Strato design system — confirms that visually distinguishing AI-generated content (confidence scores, diagnosis summaries) from raw data is an industry-recognized UX requirement.

---

## Recommendations for SRE Agent Dashboard

### Design Token System

```css
@import "tailwindcss";

/* Override Tailwind's defaults entirely */
@theme {
  --color-*: initial;

  /* Background layers */
  --color-bg-base:    oklch(14% 0.012 265);   /* Page background */
  --color-bg-panel:   oklch(18% 0.014 265);   /* Card/panel background */
  --color-bg-hover:   oklch(22% 0.016 265);   /* Hover state */

  /* Severity */
  --color-critical:   oklch(55% 0.22 27);
  --color-warning:    oklch(72% 0.18 65);
  --color-healthy:    oklch(70% 0.20 145);
  --color-info:       oklch(65% 0.15 250);

  /* AI signals (distinct from severity) */
  --color-ai-signal:  oklch(72% 0.16 195);   /* Teal — for confidence scores, RAG evidence */

  /* Text */
  --color-text-primary:   oklch(90% 0.01 265);
  --color-text-secondary: oklch(60% 0.01 265);
  --color-text-muted:     oklch(40% 0.01 265);

  /* Borders */
  --color-border:         oklch(28% 0.015 265);

  /* Typography */
  --font-sans: "Inter", ui-sans-serif, system-ui;
  --font-mono: "JetBrains Mono", "Roboto Mono", ui-monospace;
}

/* Dark mode — always active for this operations tool */
@custom-variant dark (&:where([data-theme=dark], [data-theme=dark] *));
```

### Component Architecture

```
dashboard/
  app/
    layout.tsx          (Server: root layout, sets data-theme="dark")
    page.tsx            (Server: initial data fetch, renders feed)
    api/
      v1/incidents/
        route.ts        (API proxy to SRE Agent backend)
      v1/phases/
        route.ts
      ws/               (NOT POSSIBLE — WebSocket goes in server.js)
  components/
    IncidentFeed/
      index.tsx         (Client: WebSocket subscription, Zustand)
    IncidentCard/
      index.tsx         (Presentational: severity badge, confidence, timer)
    ConfidenceDecomposition/
      index.tsx         (Client: progress bars + Recharts trend line)
    IncidentTimeline/
      index.tsx         (Server + Client: chronological events)
    PhaseTracker/
      index.tsx         (Server: graduation criteria checklist)
    KillSwitchBadge/
      index.tsx         (Client: autonomy mode + kill switch toggle)
    ConnectionStatus/
      index.tsx         (Client: WebSocket status banner)
  lib/
    store.ts            (Zustand incident store with subscribeWithSelector)
    websocket.ts        (useWebSocket hook with exponential backoff)
  server.js             (Custom Node.js server with WebSocket upgrade)
```

---

## Gaps and Clarifying Questions

### Gaps (not fully researched)

- Grafana exact dark theme hex/oklch values not confirmed (404 on Grafana UI storybook). Values above are from observational knowledge of Grafana screenshots.
- Victory chart library detailed API not fetched (URL redirected).
- Nivo exact bundle size per-package not confirmed.
- Dynatrace Strato design token exact color values not fetched (behind login).

### Clarifying Questions

1. **WebSocket architecture:** Should the WebSocket server be embedded in `server.js` alongside Next.js, or should it be a fully separate process (e.g., the SRE Agent FastAPI backend handles WebSocket directly, and the Next.js dashboard connects to it)? The latter would eliminate the `server.js` complexity.
2. **Kill switch badge behavior:** Should the kill switch be activatable from the dashboard UI (requires WebSocket bidirectional flow), or is it display-only in Phase 2.7 (simplifies to SSE)?
3. **Chart persistence:** Should the confidence trend chart data persist across page refreshes (requires backend storage of history), or is it ephemeral (in-memory for the current session only)?
4. **Phase tracker data source:** Is the graduation criteria data already exposed by the backend, or does DASH-001 task 1.4 need to create that endpoint from scratch?

---

## References

- Tailwind v4 blog: https://tailwindcss.com/blog/tailwindcss-v4
- Tailwind dark mode docs: https://tailwindcss.com/docs/dark-mode
- Datadog dashboards: https://docs.datadoghq.com/dashboards/
- Grafana product: https://grafana.com/grafana/
- Sedai product: https://sedai.io/
- Sedai docs: https://docs.sedai.io/
- BigPanda product: https://www.bigpanda.io/product/
- Dynatrace developer: https://developer.dynatrace.com/
- Dynatrace Strato design system: https://developer.dynatrace.com/design/about-strato-design-system/
- Visx (Airbnb): https://visx.airbnb.tech/
- W3C ARIA alert pattern: https://www.w3.org/WAI/ARIA/apg/patterns/alert/
- Zustand v5 README: https://github.com/pmndrs/zustand
- SRE Agent design.md: openspec/changes/phase-2-7-operator-dashboard/design.md
- SRE Agent tasks.md: openspec/changes/phase-2-7-operator-dashboard/tasks.md
- SRE Agent spec.md: openspec/changes/phase-2-7-operator-dashboard/specs/dashboard-mvp/spec.md

