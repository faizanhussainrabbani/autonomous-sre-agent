<!-- markdownlint-disable-file -->
# Task Research: Frontend Design Philosophy — Operator Dashboard (Phase 2.7)

A highly accurate, extremely precise frontend design philosophy for the SREAgent Operator Dashboard. This document is the definitive design reference for generating the initial design template for the dashboard frontend.

## Task Implementation Requests

* Establish a complete, opinionated frontend design philosophy for the SREAgent Operator Dashboard (phase-2-7-operator-dashboard)
* Cover visual language, component architecture, data visualization conventions, interaction patterns, and accessibility requirements
* Include complete application review to understand all frontend requirements
* Produce a document usable as a design template generation brief

## Scope and Success Criteria

* Scope: openspec/changes/phase-2-7-operator-dashboard; full application domain review for requirements elicitation
* Assumptions:
  * Dashboard is an internal SRE operations tool, not a public-facing product
  * Primary users are SRE engineers and SRE leadership (technical, high-context operators)
  * Next.js 15 + Tailwind CSS is the already-decided technology stack (per design.md)
  * No authentication/RBAC in MVP (deferred to Phase 3)
  * Desktop-primary, tablet-responsive layout
* Success Criteria:
  * Design philosophy is precise enough to generate a first-pass component template
  * Covers all 7 DASH task areas (API, Foundation, Incident Feed, Confidence Viz, Timeline, Phase Tracker, Testing)
  * Addresses real-time, operational-density, and trust-building UI requirements
  * Competitive context incorporated (Datadog, Dynatrace, Sedai, BigPanda benchmarks)
  * Includes color system, typography, spacing, and component inventory

## Outline

1. Application Context and User Personas
2. Design Philosophy Principles
3. Visual Language (Color, Typography, Spacing, Iconography)
4. Component Inventory
5. View Architecture (pages, layouts, navigation)
6. Data Visualization Conventions
7. Real-Time Interaction Patterns
8. Accessibility and Performance Constraints
9. Competitive Benchmarking
10. Tailwind Design Token Specification
11. Implementation Guidance

## Potential Next Research

* ~~Competitive dashboard UI patterns~~ — COMPLETE (see subagents/2026-05-30/competitive-and-tech-research.md)
* ~~Tailwind CSS design token patterns~~ — COMPLETE
* ~~React/Next.js component architecture~~ — COMPLETE
* ~~Confidence score visualization best practices~~ — COMPLETE

### Remaining Open Items

* Verify exact WebSocket ownership: FastAPI backend directly exposes `ws://api/ws/incidents` (preferred, eliminates Next.js `server.js` complexity) vs. Next.js proxying
* Clarify kill switch interactivity in Phase 2.7: display-only or interactive (click to halt)
* Confirm confidence history persistence: ephemeral or stored (affects chart backend requirements)

## Research Executed

### File Analysis

* openspec/changes/phase-2-7-operator-dashboard/proposal.md
  * Stack decision: React/Next.js + Tailwind CSS
  * Real-time via WebSocket (bidirectional, future kill switch interactive use)
  * Dashboard is a separate deployment unit from agent binary
  * 5 capability areas: incident feed, confidence viz, timeline view, phase tracker, accuracy dashboard

* openspec/changes/phase-2-7-operator-dashboard/design.md
  * Next.js 15 App Router (SSR + RSC for data-heavy views)
  * Tailwind CSS as styling foundation
  * Goals: <200ms FCP, <1s incident feed population, mobile-responsive
  * Risk: WebSocket disconnection → auto-reconnect with exponential backoff

* openspec/changes/phase-2-7-operator-dashboard/tasks.md
  * DASH-001: FastAPI API endpoints (incidents list, detail, timeline, phases, accuracy, WebSocket)
  * DASH-002: Next.js 15 setup, Tailwind tokens, layout (sidebar nav, header, kill switch badge)
  * DASH-003: Incident feed with real-time updates, severity badges, stage indicators
  * DASH-004: Confidence decomposition (trace correlation, timeline match, RAG similarity, validator agreement) with green/yellow/red color coding
  * DASH-005: Timeline with expandable entries (alert trigger → telemetry → RAG docs → hypotheses → remediation → post-action metrics)
  * DASH-006: Phase/graduation gate tracker with progress bars (met=green, unmet=red)
  * DASH-007: Unit + component + E2E tests

* openspec/changes/phase-2-7-operator-dashboard/specs/dashboard-mvp/spec.md
  * FCP < 200ms; 50+ incidents render within 1 second
  * WebSocket auto-reconnect within 5 seconds; "Reconnected" notification
  * Desktop ≥1024px: sidebar + feed + detail panel simultaneous
  * Tablet 768-1024px: single-column with expandable nav

* openspec/changes/autonomous-sre-agent/specs/operator-dashboard/spec.md
  * Real-time agent status: phase display (Observe/Assist/Autonomous/Predictive), graduation criteria progress %
  * Kill switch: prominent visual indicator, timestamp, activator identity, reason
  * Confidence breakdown per incident: trace correlation, timeline match, RAG similarity, validator agreement; each color-coded green/yellow/red
  * Historical confidence trend chart with human override rate overlay
  * Accuracy metrics: total evaluated, correct, incorrect, accuracy %; breakdown by incident category
  * Agent vs. human comparison view (in Observe/Assist mode)
  * Full incident timeline: alert trigger → telemetry queries → RAG docs (similarity scores) → hypotheses → confidence at each step → remediation → post-action metrics → resolution
  * Graduation gate progress: accuracy %, MTTD, MTTR, escalation rate vs. required thresholds

* src/sre_agent/domain/models/canonical.py
  * Severity: SEV1-SEV4 (Sev1 most critical)
  * AnomalyType: LATENCY_SPIKE, ERROR_RATE_SURGE, MEMORY_PRESSURE, DISK_EXHAUSTION, CERTIFICATE_EXPIRY, MULTI_DIMENSIONAL, DEPLOYMENT_INDUCED, INVOCATION_ERROR_SURGE, TRAFFIC_ANOMALY, SLOW_RESPONSE, TIMEOUT_PROXIMITY
  * IncidentPhase: DETECTED → CLASSIFIED → DIAGNOSING → DIAGNOSED → VALIDATING → AUTHORIZING → REMEDIATING → VERIFYING → RESOLVED / ESCALATED / FAILED
  * OperationalPhase: OBSERVE → ASSIST → AUTONOMOUS → PREDICTIVE
  * ComputeMechanism: KUBERNETES, SERVERLESS, VIRTUAL_MACHINE, CONTAINER_INSTANCE

* src/sre_agent/domain/models/diagnosis.py
  * ConfidenceLevel thresholds: <0.70 BLOCK, 0.70–0.85 PROPOSE, ≥0.85 AUTONOMOUS
  * ServiceTier: TIER_1 (revenue-critical) through TIER_4 (dev/staging)
  * DiagnosticState: PENDING → RETRIEVING → REASONING → VALIDATING → CLASSIFYING → COMPLETE / FAILED / ESCALATED / RETRIEVAL_MISS / FALLBACK_REASONING / ROOT_CAUSE_UNRESOLVED

* docs/architecture/Technology_Stack.md
  * Operator Layer: Dashboard (React/Next.js), Slack, PagerDuty, Jira
  * Intelligence Layer feeds dashboard via API: LLM Reasoning, RAG Pipeline, Vector DB, Confidence Scoring

* docs/project/roadmap.md
  * Phase 1: OBSERVE (shadow mode, logs only)
  * Phase 2: ASSIST (Sev3-4 autonomous, Sev1-2 human approval)
  * Phase 3: AUTONOMOUS (known incident classes fully autonomous)
  * Phase 4: PREDICTIVE (proactive resource/scaling management)

### External Research

* Datadog Dashboard Docs: https://docs.datadoghq.com/dashboards/
  * Grid/Timeboard/Screenboard layout types. Change event overlays on time-series (annotation pattern). Watchdog AI overlay badges.
  * Dark theme: `#1f2029` bg, `#252631` surface. Status: red `#e74c3c`, warning `#f0ad4e`, healthy `#2ecc71`.
  * Template variables (`$service`, `$env`) as global incident-scope filters — maps to dashboard filtering

* Grafana Design Reference: https://grafana.com/grafana/
  * Dark default: bg `#161719`, panel `#1b1d21`, grid `#2c2f33`, text `#d8d9da`
  * `Roboto Mono` for metric values; `Inter` for labels — confirms monospace/sans split convention
  * Alert red `#e02f44`, warning `#ff9830`, healthy `#73bf69`

* Dynatrace Strato Design System: https://developer.dynatrace.com/design/about-strato-design-system/
  * Production `@dynatrace/strato-design-tokens` npm package; observability chart library built-in
  * "Indicating AI presence" is a documented pattern — AI-generated content uses teal/blue badge or icon
  * Davis AI root cause cards shown inline in incident feeds with distinguishing AI icon

* Sedai Product Docs: https://sedai.io/ + https://docs.sedai.io/
  * **Datapilot → Copilot → Autopilot** mode system maps directly to OBSERVE → ASSIST → AUTONOMOUS
  * "Action Summary" cards: post-action reports (what agent did, metrics changed, outcome) — applicable to SRE Agent audit trail
  * Prominent mode badge always shows current autonomy level; safety constraints always surfaced in UI

* BigPanda Product: https://www.bigpanda.io/product/
  * Pre-populated AI context cards at incident creation time (summary + suggested next steps without drill-down)
  * "Noise reduction" KPI surfaced in header: "47 alerts suppressed, 3 incidents shown"
  * Risk score badges inline with incident/change records

* Tailwind CSS v4: https://tailwindcss.com/blog/tailwindcss-v4
  * `@theme { --color-* }` replaces `extend.colors` — tokens become CSS custom properties on `:root`
  * `@custom-variant dark (&:where([data-theme=dark], ...))` for data-attribute-driven dark mode
  * `--color-*: initial` resets defaults; `@theme inline` for token aliasing
  * Build: 3.78x faster full build; 182x faster incremental

* Zustand v5: https://github.com/pmndrs/zustand
  * `subscribeWithSelector` middleware for WebSocket store subscriptions outside React render cycle
  * 2KB bundle; no Provider boilerplate; selector-based subscriptions prevent high-frequency re-renders

* W3C WAI-ARIA Alert Pattern: https://www.w3.org/WAI/ARIA/apg/patterns/alert/
  * `role="alert"` + `aria-live="assertive"` only for kill switch state (true emergency)
  * `aria-live="polite"` for incident feed count updates
  * Never `role="alert"` for high-frequency events (screen reader flood)

### Project Conventions

* Standards referenced: docs/project/standards/engineering_standards.md (SOLID, hexagonal architecture, Pydantic v2, async-first)
* Technology stack: Next.js 15 App Router + TypeScript + Tailwind CSS

## Key Discoveries

### Application Domain

The SREAgent dashboard is a **Mission-Critical Operations Tool** used by technical SRE practitioners. It occupies the same product category as Datadog, Dynatrace, and Grafana — not a marketing or consumer product. Key implications for design:

1. **Operator density over minimalism**: SREs need maximum information density within a single glance. Multiple incidents, their stages, severities, and confidence scores must be simultaneously scannable.
2. **Trust is the primary UX metric**: The dashboard must communicate confidence levels, evidence quality, and phase authorization at every touchpoint. Low-confidence states must be visually unmistakable.
3. **Action surfaces must be unmistakable**: The kill switch, approval/rejection controls, and phase-transition indicators are high-stakes actions. They must never be hidden or easily misclicked.
4. **Real-time is a table-stakes requirement**: Stale data erodes trust. WebSocket connection state must always be visible. Stale or disconnected states must be prominently flagged.
5. **Timeline auditability**: SRE leadership needs a full audit trail. The timeline view must support drill-down without losing overall context.

### Data Model Requirements for the UI

Key entities the dashboard visualizes:

| Entity | Key Fields for Display |
|--------|----------------------|
| Incident | id, service_name, severity (SEV1-4), phase (DETECTED→RESOLVED), anomaly_type, confidence_score, elapsed_time, compute_mechanism |
| ConfidenceBreakdown | trace_correlation, timeline_match, rag_similarity, validator_agreement; each 0.0–1.0 |
| IncidentTimeline | chronological entries: alert_trigger, telemetry_queries, rag_documents (with similarity scores), hypotheses, confidence_at_step, remediation_actions, post_action_metrics, resolution |
| OperationalPhase | current phase (OBSERVE/ASSIST/AUTONOMOUS/PREDICTIVE), graduation criteria progress |
| GraduationCriteria | criterion_name, current_value, required_value, met (boolean) |
| AccuracyMetrics | total_evaluated, correct, incorrect, accuracy_pct; breakdown by AnomalyType |
| KillSwitch | is_active, activated_at, activated_by, reason |

### Critical UI States

| State | Display Requirement |
|-------|-------------------|
| Kill Switch ACTIVE | Full-width banner, high-contrast warning (red/amber), timestamp, activator, reason |
| WebSocket DISCONNECTED | Persistent banner or badge, last-updated timestamp, reconnection countdown |
| Confidence < 0.70 (BLOCK) | Red confidence indicator, "Awaiting Human" tag on incident card |
| Confidence 0.70–0.85 (PROPOSE) | Amber confidence indicator, "Pending Approval" tag |
| Confidence ≥ 0.85 (AUTONOMOUS) | Green confidence indicator, "Autonomous" tag |
| SEV1 incident | Maximum visual weight, red severity badge, top of feed |
| Phase: OBSERVE | Shadow mode indicator, no remediation actions shown |
| Phase: ASSIST | HITL approval buttons visible for Sev1-2 |

## Technical Scenarios

### Scenario: Color System — Operations Tool Dark Theme

**Description:** An SRE operations dashboard should use a dark-first theme aligned with operator work environments (terminal-adjacent, high-contrast, low eye fatigue during incident bridges).

**Requirements:**
* Must support dark mode as primary (light mode optional/secondary)
* Semantic colors for severity (SEV1-4) and confidence thresholds (block/propose/autonomous)
* High contrast ratios for text on dark backgrounds (WCAG AA minimum)
* Status colors: green=resolved/healthy, amber=warning/propose, red=critical/block/sev1, blue=informational, gray=inactive/unknown

**Preferred Approach:**

Tailwind CSS extended with a custom design token set using CSS variables for dark theme.

```
dashboard/
  src/
    app/
      globals.css          ← @import "tailwindcss" + @theme tokens + @custom-variant dark
      layout.tsx           ← Root layout with data-theme="dark"
```

**Tailwind v4 `@theme` Design Token Specification (`globals.css`):**

> Validated against Grafana (`#161719` / `#e02f44` / `#73bf69`) and Datadog (`#1f2029` / `#e74c3c` / `#2ecc71`) color conventions. Uses oklch color space for perceptual consistency in Tailwind v4.

```css
@import "tailwindcss";

/* ── Dark mode via data attribute (recommended for ops tools) ──────────────── */
@custom-variant dark (&:where([data-theme=dark], [data-theme=dark] *));

@theme {
  /* Reset all Tailwind default colors — use only SRE Agent design tokens */
  --color-*: initial;

  /* ── Base surfaces (Grafana-calibrated dark values) ─────────────────────── */
  --color-canvas:        oklch(14% 0.010 265);   /* ~#161719 — primary bg */
  --color-surface:       oklch(18% 0.012 265);   /* ~#1b1d21 — card/panel */
  --color-elevated:      oklch(22% 0.014 265);   /* ~#21262d — modal/dropdown */
  --color-hover:         oklch(25% 0.015 265);   /* ~#2a2f38 — hover state */
  --color-border:        oklch(30% 0.013 265);   /* ~#30363d — default border */
  --color-border-muted:  oklch(22% 0.010 265);   /* subtle border */

  /* ── Text ────────────────────────────────────────────────────────────────── */
  --color-text-primary:   oklch(88% 0.010 265);  /* ~#e6edf3 — primary */
  --color-text-secondary: oklch(60% 0.012 265);  /* ~#8b949e — muted */
  --color-text-inverse:   oklch(14% 0.010 265);  /* text on colored bg */

  /* ── Severity (SEV1–SEV4) — Grafana + Datadog validated ─────────────────── */
  --color-sev1:          oklch(55% 0.22 27);     /* ~#e02f44 — critical red */
  --color-sev1-bg:       oklch(20% 0.10 27);     /* card tint for SEV1 */
  --color-sev2:          oklch(72% 0.18 65);     /* ~#ff9830 — warning amber */
  --color-sev2-bg:       oklch(22% 0.08 65);
  --color-sev3:          oklch(70% 0.20 145);    /* ~#73bf69 — healthy green */
  --color-sev3-bg:       oklch(20% 0.08 145);
  --color-sev4:          oklch(65% 0.15 250);    /* ~#5794f2 — informational blue */
  --color-sev4-bg:       oklch(20% 0.07 250);

  /* ── Confidence routing thresholds ──────────────────────────────────────── */
  --color-conf-block:      var(--color-sev1);    /* < 0.70: BLOCK (red) */
  --color-conf-propose:    var(--color-sev2);    /* 0.70–0.85: PROPOSE (amber) */
  --color-conf-autonomous: var(--color-sev3);    /* ≥ 0.85: AUTONOMOUS (green) */

  /* ── AI signal (Dynatrace pattern: teal/blue for AI-generated content) ──── */
  --color-ai-signal:     oklch(72% 0.16 195);    /* teal — AI-generated badge */

  /* ── Kill switch ─────────────────────────────────────────────────────────── */
  --color-kill-active:   oklch(65% 0.28 27);     /* high-vis red */
  --color-kill-bg:       oklch(18% 0.12 27);     /* kill switch banner bg */

  /* ── WebSocket / connection status ──────────────────────────────────────── */
  --color-ws-connected:     var(--color-sev3);   /* green */
  --color-ws-disconnected:  var(--color-sev2);   /* amber */
  --color-ws-reconnecting:  var(--color-sev4);   /* blue */
  --color-ws-stale:         oklch(42% 0.010 265); /* gray */

  /* ── Incident pipeline phases ────────────────────────────────────────────── */
  --color-phase-detected:   oklch(42% 0.010 265); /* gray */
  --color-phase-diagnosing: var(--color-sev4);   /* blue */
  --color-phase-remediating: var(--color-sev2);  /* amber */
  --color-phase-verifying:  oklch(65% 0.18 295); /* purple */
  --color-phase-resolved:   var(--color-sev3);   /* green */
  --color-phase-failed:     var(--color-sev1);   /* red */
  --color-phase-escalated:  oklch(72% 0.28 27);  /* bright red */

  /* ── Typography ──────────────────────────────────────────────────────────── */
  --font-sans: "Inter", ui-sans-serif, -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: "JetBrains Mono", "Roboto Mono", ui-monospace, monospace;

  /* ── Base spacing unit (all Tailwind spacing utilities use this) ─────────── */
  --spacing: 0.25rem;   /* 4px base unit */

  /* ── Border radius ───────────────────────────────────────────────────────── */
  --radius-sm:    0.25rem;  /* 4px — badges, chips */
  --radius-md:    0.5rem;   /* 8px — cards, panels */
  --radius-lg:    0.75rem;  /* 12px — modals */
  --radius-full:  9999px;   /* pill shape */
}

/* ── Semantic alias tokens (reference other tokens, must use @theme inline) ── */
@theme inline {
  --color-surface-accent: color-mix(in oklch, var(--color-ai-signal) 15%, transparent);
}

/* ── Root application ────────────────────────────────────────────────────── */
html[data-theme="dark"] {
  background-color: var(--color-canvas);
  color: var(--color-text-primary);
  color-scheme: dark;
}
```

**Usage examples with generated Tailwind utilities:**

```tsx
// Severity badges
<span className="bg-sev1 text-text-inverse rounded-sm px-2 py-0.5 text-xs font-semibold">SEV1</span>
<span className="bg-sev2 text-text-inverse rounded-sm px-2 py-0.5 text-xs font-semibold">SEV2</span>

// Incident card with SEV1 tint
<div className="bg-surface border border-sev1/30 rounded-md p-4">
  <div className="bg-sev1-bg rounded p-2">...</div>
</div>

// Connection status badge
<span className="text-ws-connected">● Live</span>
<span className="text-ws-disconnected">⚠ Disconnected</span>

// Confidence score bar fill (dynamic based on score)
const getConfColor = (score: number) =>
  score >= 0.85 ? 'bg-conf-autonomous' :
  score >= 0.70 ? 'bg-conf-propose' : 'bg-conf-block';
```

### Scenario: Typography — Operational Information Hierarchy

**Requirements:**
* Monospace for IDs, timestamps, metric values, log content (Grafana pattern — `Roboto Mono`)
* Sans-serif for labels, headings, navigation (`Inter` — industry standard)
* Strict size hierarchy for at-a-glance parsing
* Compact scale (dashboard text is smaller than typical web text — ops tools are dense)

**Typography Usage Map:**

| Content Type | Font | Size | Weight | Example |
|-------------|------|------|--------|---------|
| Dashboard header | sans | xl (24px) | bold | "SRE Agent" |
| Page title | sans | lg (18px) | semibold | "Active Incidents" |
| Section heading | sans | md (16px) | semibold | "Confidence Breakdown" |
| Card label | sans | base (14px) | medium | "checkout-service" |
| Secondary info | sans | sm (12px) | normal | "diagnosing · 2m 14s" |
| Captions / metadata | sans | xs (11px) | normal | "Last updated 12:34:56" |
| Incident ID | mono | sm (12px) | normal | `INC-2026-0042` |
| Metric values | mono | base (14px) | semibold | `0.87` / `5.2%` |
| Timestamps | mono | xs (11px) | normal | `12:31:42.401` |
| Terminal/log content | mono | xs (11px) | normal | `kubectl rollout restart...` |

**Tailwind font size scale (add to `@theme`):**

```css
@theme {
  --text-xs:   0.6875rem;   /* 11px */
  --text-sm:   0.75rem;     /* 12px */
  --text-base: 0.875rem;    /* 14px — dashboard body default */
  --text-md:   1rem;        /* 16px */
  --text-lg:   1.125rem;    /* 18px */
  --text-xl:   1.5rem;      /* 24px */

  /* Font weights */
  --font-normal:   400;
  --font-medium:   500;
  --font-semibold: 600;
--font-bold: 700;
```

### Scenario: Layout Architecture — Operational Command Center

**Requirements:**
* Persistent left sidebar: navigation + phase indicator + kill switch status
* Header: global connection status, last-updated timestamp, operational phase badge
* Main content area: context-dependent (incident feed, timeline, confidence viz, accuracy)
* Optional detail panel: right-side drawer for incident detail

**Layout Structure:**

```
┌──────────────────────────────────────────────────────────────────┐
│ HEADER: [SRE Agent Logo] [Phase: ASSIST] [● Connected] [12:34:56]│
├────────┬─────────────────────────────────────────────────────────┤
│        │                                                          │
│  NAV   │  MAIN CONTENT AREA                                      │
│        │                                                          │
│ ● Feed │  ┌──────────────────────────────────────────────────┐   │
│ ● Conf │  │ INCIDENT FEED (real-time)                        │   │
│ ● Accy │  │  SEV1 │ checkout-svc │ REMEDIATING │ 87% │ 4m12s│   │
│ ● Phase│  │  SEV2 │ auth-service │ DIAGNOSING  │ 71% │ 1m44s│   │
│        │  │  SEV3 │ worker-pod   │ VERIFYING   │ 91% │ 0m38s│   │
│  ───   │  └──────────────────────────────────────────────────┘   │
│ ⚠ KILL │                                                          │
│ SWITCH │                                                          │
└────────┴─────────────────────────────────────────────────────────┘
```

### Scenario: Incident Card Component Design

**Requirements:**
* Maximum density: all critical info in a single horizontal card row
* Severity badge (SEV1-4) with color and text
* Service name (monospace, prominent)
* Stage pipeline indicator (DETECTED → RESOLVED)
* Confidence score (numeric + color-coded bar)
* Elapsed timer (live countdown)
* Compute mechanism icon (K8s / AWS / Azure)

**Component Structure:**

```tsx
// IncidentCard — displays single incident in feed
interface IncidentCardProps {
  id: string;
  serviceName: string;
  severity: 'SEV1' | 'SEV2' | 'SEV3' | 'SEV4';
  phase: IncidentPhase;          // DETECTED → RESOLVED
  anomalyType: AnomalyType;
  confidenceScore: number;       // 0.0–1.0
  elapsedSeconds: number;        // live, from WebSocket updates
  computeMechanism: ComputeMechanism;
  onSelect: (id: string) => void;
}
```

**Visual Encoding:**

| Field | Visual Encoding |
|-------|----------------|
| Severity | Color badge (SEV1=red, SEV2=amber, SEV3=green, SEV4=blue) + text |
| Phase | Segmented stage bar with active segment highlighted |
| Confidence <0.70 | Red fill on score bar + "HUMAN" tag |
| Confidence 0.70–0.85 | Amber fill + "PENDING" tag |
| Confidence ≥0.85 | Green fill + "AUTO" tag |
| Elapsed time | Monospace live counter, amber >5min, red >15min |
| Compute mechanism | Icon: K8s gear / AWS cube / Azure hexagon |

### Scenario: Confidence Decomposition Component

**Requirements:**
* 4 evidence components: trace_correlation, timeline_match, rag_similarity, validator_agreement
* Each component displayed as a labeled horizontal bar (0.0–1.0)
* Color threshold: green ≥0.8, amber 0.5–0.8, red <0.5
* Aggregate confidence score prominently displayed
* Routing label (BLOCK / PROPOSE / AUTONOMOUS) based on aggregate

**Component:**

```tsx
interface ConfidenceDecompositionProps {
  aggregate: number;                   // 0.0–1.0
  components: {
    trace_correlation: number;
    timeline_match: number;
    rag_similarity: number;
    validator_agreement: number;
  };
}

// Routing label logic:
// aggregate < 0.70  → "BLOCK" (red)
// 0.70 ≤ aggregate < 0.85 → "PROPOSE" (amber)  
// aggregate ≥ 0.85 → "AUTONOMOUS" (green)
```

### Scenario: Incident Timeline Component

**Requirements:**
* Vertical timeline with left-side timestamp column
* Each entry shows: event type icon, event description, expandable detail
* Entry types: ALERT_TRIGGER, TELEMETRY_QUERY, RAG_RETRIEVAL (with similarity score), HYPOTHESIS, CONFIDENCE_CHECKPOINT, REMEDIATION_ACTION, POST_ACTION_METRICS, RESOLUTION
* Expand/collapse per entry
* RAG entries must show similarity score and document title

**Timeline Entry Visual:**

```
12:31:42 ● ALERT_TRIGGER        checkout-svc high error rate (5.2%) [▼ expand]
12:31:43 ● TELEMETRY_QUERY      PromQL: rate(http_errors[5m]) > 0.05
12:31:45 ● RAG_RETRIEVAL        "checkout-svc OOM 2025-11-14" (sim: 0.87) [▼]
12:31:48 ● HYPOTHESIS           Root cause: memory pressure → GC pause → timeout
12:31:48 ○ CONFIDENCE_CHECKPOINT 0.83 → PROPOSE routing
12:31:55 ● REMEDIATION_ACTION   kubectl rollout restart deploy/checkout-svc
12:32:10 ● POST_ACTION_METRICS  error_rate: 5.2% → 0.1% (normalized)
12:32:10 ✓ RESOLUTION           Incident resolved in 28s
```

### Scenario: Kill Switch Status Component

**Requirements:**
* Kill switch ACTIVE state: full-width banner at top of every view
* Banner: high-contrast red, prominent "ALL AGENT ACTIONS HALTED" text
* Must display: timestamp of activation, identity of activator, reason
* Kill switch INACTIVE state: subtle badge in sidebar (gray/muted)

**Kill Switch States:**

```tsx
// ACTIVE — full banner
<KillSwitchBanner
  activatedAt="2026-05-30T12:34:56Z"
  activatedBy="john.doe@company.com"
  reason="Investigating database migration impact"
/>

// INACTIVE — sidebar badge only
<KillSwitchBadge status="inactive" />
```

### Scenario: Graduation Gate Progress Tracker

**Requirements:**
* Display current operational phase
* Show each graduation criterion with: name, current value, required value, % progress, met status
* Color: met=green, unmet=red, near-threshold=amber (within 5% of threshold)
* Visual progress bar per criterion

**Known Graduation Criteria (from spec):**
* Diagnostic accuracy: current% vs. 90% required
* MTTD (Mean Time to Detect): current vs. target threshold
* MTTR (Mean Time to Remediate): current vs. target
* Escalation rate: current% vs. max allowed%
* Human override rate: current% vs. max allowed%

### Scenario: Real-Time WebSocket State Management

**Architecture Decision: FastAPI exposes WebSocket at `ws://api/ws/incidents` — Next.js client connects directly.**

Rationale: Next.js 15 App Router Route Handlers cannot hold WebSocket upgrades (HTTP request/response only). Direct connection to FastAPI avoids `server.js` complexity and keeps the WebSocket close to the data source.

**Requirements:**
* Single WebSocket connection for entire dashboard session
* Events: `incident.created`, `incident.updated`, `incident.resolved`, `kill_switch.changed`, `phase.changed`
* Auto-reconnect with exponential backoff: 1s → 2s → 4s → 8s → 16s → 30s (max), with jitter
* Connection state: CONNECTED, RECONNECTING, DISCONNECTED
* "Last updated" timestamp on each data section

**State Management: Zustand v5 with `subscribeWithSelector`**

Rationale: `subscribeWithSelector` enables WebSocket event subscriptions outside the React render cycle. Avoids high-frequency re-renders from direct Context state updates. 2KB bundle.

```tsx
// stores/incident-store.ts
import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';

interface IncidentStore {
  incidents: Map<string, Incident>;
  connectionStatus: 'connected' | 'reconnecting' | 'disconnected';
  lastUpdated: Date | null;
  upsertIncident: (incident: Incident) => void;
  removeIncident: (id: string) => void;
  setConnectionStatus: (s: IncidentStore['connectionStatus']) => void;
}

export const useIncidentStore = create<IncidentStore>()(
  subscribeWithSelector((set) => ({
    incidents: new Map(),
    connectionStatus: 'disconnected',
    lastUpdated: null,
    upsertIncident: (incident) =>
      set((state) => ({
        incidents: new Map(state.incidents).set(incident.id, incident),
        lastUpdated: new Date(),
      })),
    removeIncident: (id) =>
      set((state) => {
        const m = new Map(state.incidents);
        m.delete(id);
        return { incidents: m };
      }),
    setConnectionStatus: (connectionStatus) => set({ connectionStatus }),
  }))
);

// hooks/use-incident-stream.ts
'use client';
import { useEffect, useRef, useCallback } from 'react';
import { useIncidentStore } from '@/stores/incident-store';

export function useIncidentStream(wsUrl: string) {
  const wsRef = useRef<WebSocket | null>(null);
  const attemptRef = useRef(0);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { upsertIncident, removeIncident, setConnectionStatus } = useIncidentStore();

  const connect = useCallback(() => {
    setConnectionStatus('reconnecting');
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      attemptRef.current = 0;
      setConnectionStatus('connected');
    };

    ws.onmessage = (evt) => {
      const msg = JSON.parse(evt.data);
      if (msg.type === 'incident.created' || msg.type === 'incident.updated') {
        upsertIncident(msg.incident);
      } else if (msg.type === 'incident.resolved') {
        removeIncident(msg.id);
      }
    };

    ws.onclose = () => {
      setConnectionStatus('disconnected');
      const delay = Math.min(1000 * 2 ** attemptRef.current, 30000);
      const jitter = Math.random() * 500;
      attemptRef.current++;
      timeoutRef.current = setTimeout(connect, delay + jitter);
    };

    ws.onerror = () => ws.close();
  }, [wsUrl, upsertIncident, removeIncident, setConnectionStatus]);

  useEffect(() => {
    connect();
    return () => {
      timeoutRef.current && clearTimeout(timeoutRef.current);
      wsRef.current?.close();
    };
  }, [connect]);
}
```

**ARIA live regions for accessibility:**

```tsx
// Connection status — polite announcement
<div aria-live="polite" aria-atomic="true" className="sr-only">
  {connectionStatus === 'disconnected' ? 'Dashboard disconnected from server' : 'Dashboard connected'}
</div>

// Incident count — polite
<div aria-live="polite" aria-atomic="false" className="sr-only">
  {incidents.size} active incidents
</div>

// Kill switch ONLY — assertive (true emergency)
<div role="alert" aria-live="assertive">
  {killSwitchActive ? 'ALERT: All agent actions suspended' : null}
</div>
```

### Scenario: Chart Library — Confidence Trend Visualization

**Selected: Recharts**

Rationale (vs. alternatives):
- Confidence trend (DASH-004 task 4.3): simple `LineChart` — Recharts handles declaratively
- Confidence decomposition bars (DASH-004 task 4.1-4.2): **CSS `div` elements with Tailwind width utilities** — NOT chart components; avoids SVG complexity and enables direct CSS token integration
- Graduation criteria progress bars (DASH-006): CSS-only (same approach)
- Recharts integrates with Tailwind's CSS variable system: `stroke="var(--color-sev4)"` etc.
- Bundle: ~300KB acceptable for a separate deployment unit

**Rejected: Nivo** — 400KB, heavy animation unsuitable for high-frequency real-time data
**Rejected: Tremor** — full component library conflicts with dashboard's own Tailwind UI
**Available as upgrade: Visx (Airbnb)** — 90KB modular, full D3 power, for complex visualizations in Phase 3+

**Confidence trend chart implementation:**

```tsx
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export function ConfidenceTrendChart({ data }: { data: { time: string; confidence: number; overrideRate: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-muted)" />
        <XAxis dataKey="time" stroke="var(--color-text-secondary)" tick={{ fill: 'var(--color-text-secondary)', fontSize: 11 }} />
        <YAxis domain={[0, 1]} stroke="var(--color-text-secondary)" tick={{ fill: 'var(--color-text-secondary)', fontSize: 11 }} />
        <Tooltip
          contentStyle={{ backgroundColor: 'var(--color-elevated)', border: '1px solid var(--color-border)', borderRadius: '8px' }}
          labelStyle={{ color: 'var(--color-text-primary)' }}
        />
        <Line type="monotone" dataKey="confidence" stroke="var(--color-sev4)" strokeWidth={2} dot={false} name="Avg Confidence" />
        <Line type="monotone" dataKey="overrideRate" stroke="var(--color-sev2)" strokeWidth={1.5} strokeDasharray="4 2" dot={false} name="Human Override Rate" />
      </LineChart>
    </ResponsiveContainer>
  );
}
```

**Confidence decomposition bars (CSS-only, not Recharts):**

```tsx
export function ConfidenceBar({ label, value }: { label: string; value: number }) {
  const colorClass = value >= 0.8 ? 'bg-sev3' : value >= 0.5 ? 'bg-sev2' : 'bg-sev1';
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="w-40 text-text-secondary text-xs font-mono">{label}</span>
      <div className="flex-1 h-2 bg-elevated rounded-full overflow-hidden">
        <div className={`h-full ${colorClass} rounded-full transition-all duration-300`} style={{ width: `${value * 100}%` }} />
      </div>
      <span className="w-10 text-right font-mono text-xs text-text-primary">{value.toFixed(2)}</span>
    </div>
  );
}
```

## Selected Design Approach

**Approach: "Operations Command Center" — Dark-First, Density-Optimized, Trust-Signaling**

### Philosophy Statement

The SREAgent Operator Dashboard is designed for one purpose: **enabling SRE engineers to trust and supervise an autonomous agent during high-stakes infrastructure incidents**. Every design decision is subordinate to this goal.

The design philosophy has five pillars:

**1. Density with Hierarchy**
Information density is a virtue in operations tools, not a vice. The dashboard shows as many incidents as possible simultaneously, but uses consistent visual hierarchy (size, weight, color) to ensure critical information (SEV1, low confidence, kill switch active) is always in the operator's primary attention zone.

**2. Semantic Color as Truth**
Color is never decorative. Every color carries semantic meaning:
- Red = critical / blocked / human required
- Amber = warning / pending / requires attention
- Green = healthy / autonomous / resolved
- Blue = informational / in-progress
- Gray = inactive / unknown / observing
- Teal = AI-generated content (Dynatrace Strato "indicating AI presence" pattern)

Color blind accessibility: every color-coded state is accompanied by a text label or icon (never color alone).

**3. Trust Through Transparency**
The confidence decomposition, timeline audit trail, and graduation progress tracker exist to make the agent's reasoning legible. The dashboard makes invisible decisions visible. The operator must always be able to answer: "Why did the agent do that?" (Sedai "Action Summary" pattern)

**4. Action Surfaces are Unmistakable**
The kill switch, HITL approval/rejection buttons, and phase-transition triggers are the highest-stakes interactive elements. They are positioned consistently, sized generously, and require deliberate interaction.

**5. Real-Time or Clearly Stale**
Connection status is always visible. When WebSocket disconnects, every affected section shows a stale indicator with last-known timestamp. The "last updated" field is always monospace-formatted and visible. Operators must never unknowingly act on stale data.

### Technology Decisions (Final)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Framework | Next.js 15 + App Router | SSR for FCP < 200ms; RSC for data-heavy views; decided in design.md |
| Styling | Tailwind CSS v4 + `@theme` tokens | CSS-variable tokens integrate with chart libraries; 182x faster incremental builds |
| Dark theme | `data-theme="dark"` on `<html>` | Explicit data-attribute (ops tools are dark-first; no OS preference override) |
| State (real-time) | Zustand v5 + `subscribeWithSelector` | 2KB; no Provider; selector subscriptions prevent high-frequency re-renders |
| WebSocket | Native browser WebSocket → FastAPI | Next.js App Router cannot host WS; direct FastAPI connection eliminates `server.js` |
| Charts | Recharts (trend lines only) + CSS bars | CSS bars for decomposition/progress; Recharts for time-series trend only |
| Icons | Heroicons v2 | MIT; Tailwind ecosystem; SVG-based for crisp rendering on dark backgrounds |
| Fonts | Inter (sans) + JetBrains Mono (mono) | Grafana convention: monospace for metric values, sans for labels |
| Accessibility | WCAG 2.1 AA; color + label/icon always paired | `aria-live="polite"` for feed, `role="alert"` for kill switch only |
| Testing | Vitest + React Testing Library + Playwright E2E | RTL for component (DASH-007); Playwright for browser E2E |

#### Rejected Alternatives

| Alternative | Rejected Reason |
|-------------|----------------|
| Zustand → React Context + custom hook | Context causes full subtree re-renders on every incident event; too expensive for 50+ incident feed |
| Tailwind v3 `extend.colors` | CSS variables not emitted as custom properties in v3; can't use tokens in chart library `stroke=` attributes |
| Nivo charts | 400KB bundle; heavy animation transitions are visual noise in real-time data updates |
| Tremor | Full UI component library — conflicts with dashboard's own Tailwind-based design system |
| socket.io | Adds 200KB overhead; native WebSocket sufficient; overkill for this use case |

### Component Inventory (Final)

| Component | Description | DASH Task |
|-----------|-------------|-----------|
| `AppLayout` | Root layout: sidebar + header + kill switch banner slot | DASH-002 |
| `Sidebar` | Navigation, phase badge, kill switch status badge | DASH-002 |
| `Header` | Connection status, last updated timestamp, operational phase banner | DASH-002 |
| `KillSwitchBanner` | Full-width `role="alert"` banner (active state only) | DASH-002 |
| `ConnectionStatusBadge` | Connected/Reconnecting/Disconnected indicator | DASH-002 |
| `IncidentFeed` | Real-time incident list, sorted by severity, WebSocket-driven | DASH-003 |
| `IncidentCard` | Single incident: severity badge, service, stage bar, confidence, elapsed timer | DASH-003 |
| `SeverityBadge` | SEV1-4 color + text badge (color + text always paired) | DASH-003 |
| `IncidentStageBar` | Segmented pipeline stage indicator (DETECTED → RESOLVED) | DASH-003 |
| `ConfidenceScore` | Numeric score + CSS bar + routing label (BLOCK / PENDING / AUTO) | DASH-003/004 |
| `ConfidenceDecomposition` | 4 CSS bars: trace_correlation, timeline_match, rag_similarity, validator_agreement | DASH-004 |
| `ConfidenceTrendChart` | Recharts LineChart: rolling avg confidence + human override rate overlay | DASH-004 |
| `IncidentTimeline` | Vertical chronological timeline with expandable entries | DASH-005 |
| `TimelineEntry` | Single timeline event: type icon, description, expand/collapse detail | DASH-005 |
| `AIBadge` | Teal "AI" badge for AI-generated content (Dynatrace pattern) | DASH-004/005 |
| `PhaseStatusCard` | Current operational phase (OBSERVE/ASSIST/AUTONOMOUS/PREDICTIVE) + visual indicator | DASH-006 |
| `GraduationCriteriaList` | Criteria checklist with CSS progress bars (green=met, red=unmet, amber=near) | DASH-006 |
| `AccuracyMetricsPanel` | Total evaluated, correct, incorrect, accuracy%; breakdown by AnomalyType | Accuracy spec |
| `AgentVsHumanTable` | Side-by-side comparison table (visible in OBSERVE/ASSIST mode only) | Accuracy spec |
| `IncidentDetailPanel` | Drawer/page: full diagnosis + ConfidenceDecomposition + IncidentTimeline | DASH-003 |
| `ElapsedTimer` | Live elapsed time counter (monospace; amber >5min, red >15min) | DASH-003 |

### Page / Route Architecture

```
dashboard/
  src/
    app/
      layout.tsx              ← AppLayout: sidebar + header + kill switch banner (Client)
      page.tsx                ← redirect → /incidents
      incidents/
        page.tsx              ← IncidentFeed — primary real-time view (Client)
        [id]/
          page.tsx            ← Incident detail: ConfidenceDecomposition + Timeline (mixed)
      confidence/
        page.tsx              ← ConfidenceTrendChart + history analytics (Client)
      accuracy/
        page.tsx              ← AccuracyMetricsPanel + AgentVsHumanTable (Server + Client)
      phases/
        page.tsx              ← PhaseStatusCard + GraduationCriteriaList (Server Component)
    stores/
      incident-store.ts       ← Zustand store (subscribeWithSelector)
      kill-switch-store.ts    ← Kill switch + phase state
    hooks/
      use-incident-stream.ts  ← WebSocket hook (exponential backoff reconnect)
      use-elapsed-timer.ts    ← Live elapsed time counter
    components/
      layout/                 ← AppLayout, Sidebar, Header, KillSwitchBanner
      incidents/              ← IncidentFeed, IncidentCard, SeverityBadge, IncidentStageBar
      confidence/             ← ConfidenceScore, ConfidenceDecomposition, ConfidenceTrendChart
      timeline/               ← IncidentTimeline, TimelineEntry
      phases/                 ← PhaseStatusCard, GraduationCriteriaList, GraduationCriteriaItem
      accuracy/               ← AccuracyMetricsPanel, AgentVsHumanTable
      shared/                 ← AIBadge, ElapsedTimer, ConnectionStatusBadge
    lib/
      api-client.ts           ← Typed fetch wrappers for FastAPI REST endpoints
      ws-events.ts            ← WebSocket event type definitions
```

### Next.js 15 Server/Client Component Split

| Component | Type | Reason |
|-----------|------|--------|
| Sidebar, nav structure | Server | Static structure, no interactivity |
| IncidentFeed | Client | WebSocket subscription, live updates |
| IncidentCard | Client | Live elapsed timer |
| PhaseStatusCard | Server | Read-only, SSR from API |
| GraduationCriteriaList | Server | Read-only, SSR from API |
| ConfidenceTrendChart | Client | Recharts requires DOM |
| KillSwitchBanner | Client | Real-time state + `role="alert"` |
| ConnectionStatusBadge | Client | WebSocket connection state |
| AccuracyMetricsPanel | Server | Static aggregate metrics |

### Accessibility Requirements

* WCAG 2.1 Level AA compliance
* All color-coded states paired with text label or icon (color blindness safety — never color alone)
* Keyboard navigable: tab order through incident cards, expand/collapse entries
* `aria-live="polite"` for incident feed count; `role="alert"` for kill switch only
* Minimum 4.5:1 contrast ratio (all text on dark backgrounds)
* Focus indicators: `focus-visible:ring-2 focus-visible:ring-sev4` (Tailwind)

### Performance Requirements (from spec)

| Metric | Target |
|--------|--------|
| First Contentful Paint | < 200ms |
| Incident feed populated (initial load) | < 500ms |
| 50+ incidents render time | < 1000ms |
| WebSocket update propagation | < 1s end-to-end |
| No frozen frame | > 100ms threshold |
| WebSocket reconnection | < 5s (first retry at 1s) |

### Competitive Benchmark Patterns Adopted

| Platform | Pattern Adopted |
|----------|----------------|
| Grafana | Dark theme bg/panel values; monospace for metric values; panel-based information density |
| Datadog | Severity color conventions (red/amber/green/blue); change event annotations on timelines |
| Dynatrace Strato | Teal "AI presence" badge for AI-generated content; "indicating AI" as explicit design pattern |
| Sedai | Autonomy mode badge (OBSERVE/ASSIST/AUTONOMOUS); "Action Summary" post-remediation cards |
| BigPanda | Pre-populated AI context on incident creation; noise reduction KPI in header |

## Actionable Next Steps for Implementation

1. **Initialize Next.js 15** in `dashboard/` — TypeScript strict mode, App Router
2. **Install dependencies**: `zustand`, `recharts`, `@heroicons/react`, configure Google Fonts (Inter + JetBrains Mono)
3. **Create `src/app/globals.css`** with the full `@theme` token specification from this document
4. **Set `<html data-theme="dark">`** in root `layout.tsx`
5. **Implement Zustand stores**: `incident-store.ts`, `kill-switch-store.ts`
6. **Implement `useIncidentStream` hook** (exponential backoff WebSocket reconnect)
7. **Implement `AppLayout`**: sidebar + header + kill switch banner slot
8. **Implement `IncidentFeed` + `IncidentCard`**: primary MVP view with real-time WebSocket updates
9. **Implement `ConfidenceDecomposition`**: CSS bars for incident detail (DASH-004)
10. **Implement `IncidentTimeline`**: vertical expandable timeline (DASH-005)
11. **Implement `PhaseStatusCard` + `GraduationCriteriaList`**: graduation tracker (DASH-006)
12. **Implement `ConfidenceTrendChart`**: Recharts LineChart for rolling confidence (DASH-004)
13. **Create API client** (`lib/api-client.ts`) typed wrappers for FastAPI REST endpoints
14. **Add tests**: Vitest + RTL for components; Playwright E2E for browser flows (DASH-007)
