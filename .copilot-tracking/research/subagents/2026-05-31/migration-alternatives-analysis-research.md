<!-- markdownlint-disable-file -->

# Migration Alternatives Analysis: mockup-sandbox -> Production Operator Dashboard (Node.js Endpoints Only)

Status: Complete
Date: 2026-05-31
Scope: Evaluate concrete implementation alternatives for evolving the existing mockup-sandbox into a production Operator Dashboard while consuming only the existing Node.js backend surface.

## Research Questions

1. Which migration approach best aligns with current repository conventions in fullstackapp/SRE-Command-Center?
2. Which approach best aligns with phase-2-7 requirements and minimizes migration risk?
3. What file tree changes and sequencing are required per approach?
4. Which approach should be selected based on a scored, evidence-backed decision model?

## Repository Evidence Baseline

Phase and MVP requirements:
- openspec/changes/phase-2-7-operator-dashboard/.openspec.yaml:1-4
- openspec/changes/phase-2-7-operator-dashboard/tasks.md:1-46
- openspec/changes/phase-2-7-operator-dashboard/specs/dashboard-mvp/spec.md:7-56
- openspec/changes/phase-2-7-operator-dashboard/design.md:7-13
- openspec/changes/phase-2-7-operator-dashboard/design.md:23-30
- openspec/changes/phase-2-7-operator-dashboard/proposal.md:9-13

Current Node.js backend and contract stack:
- fullstackapp/SRE-Command-Center/README.md:20-27
- fullstackapp/SRE-Command-Center/README.md:40-45
- fullstackapp/SRE-Command-Center/README.md:76-86
- fullstackapp/SRE-Command-Center/README.md:162-185
- fullstackapp/SRE-Command-Center/README.md:203-209
- fullstackapp/SRE-Command-Center/artifacts/api-server/src/app.ts:109-114
- fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/index.ts:9-12
- fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts:154-181
- fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts:183-241
- fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts:243-278
- fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/phases.ts:35-173
- fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/accuracy.ts:23-93
- fullstackapp/SRE-Command-Center/artifacts/api-server/src/index.ts:21-23
- fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts:14-16
- fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts:179-187
- fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts:212-255
- fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts:265-299
- fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:31-132
- fullstackapp/SRE-Command-Center/lib/api-spec/package.json:5-7
- fullstackapp/SRE-Command-Center/lib/api-client-react/src/index.ts:1-4
- fullstackapp/SRE-Command-Center/lib/api-zod/src/index.ts:1-2

Current mockup-sandbox reality:
- fullstackapp/SRE-Command-Center/README.md:81
- fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/main.tsx:1-5
- fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/App.tsx:99-117
- fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/App.tsx:120-144
- fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/Dashboard.tsx:21-53
- fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/Dashboard.tsx:69-157
- fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/Dashboard.tsx:223-255
- fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/package.json:2-11

Monorepo/package conventions:
- fullstackapp/SRE-Command-Center/package.json:5-10
- fullstackapp/SRE-Command-Center/pnpm-workspace.yaml:37-41

Key observed facts used in scoring:
- Required phase-2-7 API/WS endpoints are already implemented in Node Express and aligned with OpenAPI and generated contracts.
- Mockup sandbox is a component preview/gallery shell and not a production app shell.
- Existing repo conventions already support adding a new artifact package cleanly under artifacts/*.

## Approach 1: In-place Refactor of mockup-sandbox

### Architecture Flow and Principles

Flow:
Browser (artifacts/mockup-sandbox) -> generated API client (lib/api-client-react) -> Node REST (/api/v1/*) and WS (/api/ws/incidents) -> Drizzle/Postgres

Principles:
- Reuse existing package and UI primitives.
- Incrementally replace mock/hardcoded dashboard surfaces with live data hooks.
- Keep contract-first integration via OpenAPI + generated client types.

Evidence:
- Sandbox package purpose is mockup/design oriented: fullstackapp/SRE-Command-Center/README.md:81
- App shell is preview/gallery first: fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/App.tsx:99-117 and fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/App.tsx:120-144
- Dashboard component currently hardcoded/static: fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/Dashboard.tsx:21-53 and fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/Dashboard.tsx:69-157

### Benefits

- Fastest path to first visible production behavior.
- Minimal package scaffolding overhead.
- Can reuse current Tailwind/Radix setup immediately.

### Trade-offs

- High coupling between design-preview infrastructure and production runtime concerns.
- Increased risk of regressions to preview workflows and mockup iteration UX.
- Harder long-term separation of concerns (demo artifacts vs production feature code).

### Complexity, Migration Risk

- Complexity: Medium
- Migration risk: Medium-High
- Why: The current app entry is not production-route oriented; converting preview/gallery logic into production routing/data orchestration requires structural rewiring rather than only feature additions.

### Alignment with Current Conventions and Phase-2-7

- Partial alignment with phase tasks requiring dashboard capabilities and WS client behavior.
- Weak alignment with current monorepo intent where mockup-sandbox is explicitly a sandbox package.

### Required File Tree Changes

Likely changes:
- Modify: artifacts/mockup-sandbox/src/App.tsx
- Add: artifacts/mockup-sandbox/src/features/dashboard/*
- Add: artifacts/mockup-sandbox/src/lib/api/* (client config, ws runtime)
- Add: artifacts/mockup-sandbox/src/routes/* (if introducing app routing)
- Add tests under artifacts/mockup-sandbox/src/**/__tests__

### Migration Sequencing

1. Introduce production app routes and keep preview route behind /preview/* fallback.
2. Integrate API client and WS runtime, replace hardcoded feed and KPI blocks first.
3. Add timeline/detail and phase tracker from live endpoints.
4. Add reconnect, reconcile, and perf instrumentation for phase-2-7 SLAs.
5. Backfill component and e2e tests.

## Approach 2: New Production Dashboard Package; Keep sandbox for Design

### Architecture Flow and Principles

Flow:
Browser (new artifacts/operator-dashboard) -> generated API client (lib/api-client-react) + shared zod contracts -> Node REST/WS -> Express + Drizzle

Principles:
- Preserve bounded contexts: sandbox remains design playground; new package handles production runtime.
- Maximize reuse of existing contract-first stack and generated clients.
- Align with workspace package conventions by introducing a new artifact package.

Evidence:
- Monorepo supports artifact packages: fullstackapp/SRE-Command-Center/pnpm-workspace.yaml:37-41
- Existing architecture expects contract-first shared libs: fullstackapp/SRE-Command-Center/README.md:20-27 and fullstackapp/SRE-Command-Center/README.md:241-244
- Generated client and schema entry points are ready for reuse: fullstackapp/SRE-Command-Center/lib/api-client-react/src/index.ts:1-4 and fullstackapp/SRE-Command-Center/lib/api-zod/src/index.ts:1-2
- Existing Node endpoints and WS are in place: fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:31-132 and fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts:14-16

### Benefits

- Clean separation of production concerns from sandbox/design concerns.
- Lowest long-term maintenance risk.
- Strongest fit to monorepo conventions and package boundaries.
- Allows phased migration by cherry-picking reusable visual components from sandbox.

### Trade-offs

- Slightly higher short-term setup overhead than in-place refactor.
- Potential duplication during transition (styles/components until shared abstractions are extracted).

### Complexity, Migration Risk

- Complexity: Medium
- Migration risk: Low-Medium
- Why: Adds a package but avoids destabilizing existing mockup preview pipeline and avoids full rewrite risk.

### Alignment with Current Conventions and Phase-2-7

- High alignment with package-based monorepo structure and contract-first design.
- High alignment with phase-2-7 MVP goals (real-time feed, confidence/timeline/phase tracking), implemented against existing Node endpoints.
- Resolves FastAPI-vs-Node mismatch in the spec references by using implemented Node surfaces already documented in the Command Center stack.

### Required File Tree Changes

Likely additions:
- Add: artifacts/operator-dashboard/package.json
- Add: artifacts/operator-dashboard/src/main.tsx (or framework entry)
- Add: artifacts/operator-dashboard/src/app/* (layout, routes, pages)
- Add: artifacts/operator-dashboard/src/features/incidents/*
- Add: artifacts/operator-dashboard/src/features/timeline/*
- Add: artifacts/operator-dashboard/src/features/confidence/*
- Add: artifacts/operator-dashboard/src/features/phases/*
- Add: artifacts/operator-dashboard/src/lib/api-client.ts (configure base URL/auth)
- Add: artifacts/operator-dashboard/src/lib/ws/incidents.ts
- Add tests under artifacts/operator-dashboard/src/**/__tests__ and e2e specs

Likely updates:
- Update: fullstackapp/SRE-Command-Center/README.md (run instructions for both sandbox and production dashboard package)
- Optional: extract reusable visual primitives from sandbox into shared lib package later

### Migration Sequencing

1. Scaffold new package under artifacts/operator-dashboard with dev/build/typecheck scripts consistent with workspace.
2. Wire generated API client and WS consumer to existing Node endpoints.
3. Implement phase-2-7 critical views in order: incident feed -> incident detail/timeline -> accuracy/phase tracker.
4. Add reconnect + missed-event reconciliation to satisfy real-time requirement scenarios.
5. Run side-by-side validation with sandbox and deprecate only duplicated mock data paths.

## Approach 3: Greenfield Dashboard App Replacing sandbox

### Architecture Flow and Principles

Flow:
Browser (new app replacing artifacts/mockup-sandbox) -> generated API client + WS -> Node REST/WS -> Express backend

Principles:
- Clean-slate app architecture with no legacy carryover.
- Immediate deprecation/removal of sandbox package.

Evidence:
- Current sandbox is explicitly identified as a sandbox in monorepo layout: fullstackapp/SRE-Command-Center/README.md:81
- Current preview/gallery behavior is custom and would be removed in replacement: fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/App.tsx:99-144

### Benefits

- Cleanest production-oriented codebase from day 1.
- Eliminates technical debt from mockup code patterns.

### Trade-offs

- Highest disruption risk; loses existing design-preview utility.
- Larger migration blast radius (scripts/docs/workflows that assume mockup-sandbox).
- Harder rollback if production app slips schedule.

### Complexity, Migration Risk

- Complexity: High
- Migration risk: High
- Why: Full replacement plus package/workflow renaming/removal has broad repo impact without clear MVP benefit over Approach 2.

### Alignment with Current Conventions and Phase-2-7

- Medium alignment with phase-2-7 delivery goals.
- Weak-to-medium alignment with current repo practice of keeping a dedicated sandbox artifact for design iteration.

### Required File Tree Changes

Likely changes:
- Remove/replace: artifacts/mockup-sandbox/*
- Add: replacement production app package files
- Update all docs/scripts references pointing to @workspace/mockup-sandbox

### Migration Sequencing

1. Build replacement app in parallel branch.
2. Migrate all commands/docs/scripts from mockup-sandbox to new app.
3. Remove mockup package and resolve downstream breakages.
4. Recreate design-preview workflow elsewhere if still needed.

## Decision Criteria and Scores

Scoring scale: 1 (worst) to 5 (best)

| Criteria | Weight | Approach 1 In-place Refactor | Approach 2 New Package + Keep Sandbox | Approach 3 Greenfield Replace |
|---|---:|---:|---:|---:|
| Phase-2-7 requirement fit (real-time, timeline, phase tracking, performance) | 0.25 | 3 | 5 | 4 |
| Alignment with current repo/package conventions | 0.20 | 2 | 5 | 3 |
| Delivery speed to MVP | 0.15 | 4 | 4 | 2 |
| Migration risk/blast radius | 0.20 | 2 | 4 | 1 |
| Long-term maintainability | 0.20 | 2 | 5 | 4 |
| Weighted total | 1.00 | 2.55 | 4.65 | 2.80 |

## Selected Recommendation

Selected: Approach 2 (new production dashboard package while retaining sandbox).

Evidence-backed rationale:
- It best matches current monorepo boundaries and intended artifact roles (sandbox for mockups, production package for runtime features): fullstackapp/SRE-Command-Center/README.md:76-86.
- It leverages already-implemented Node endpoints and WebSocket stream without backend rewrites: fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:31-132 and fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts:14-16.
- It preserves design iteration velocity while implementing MVP requirements from phase-2-7 tasks/spec scenarios.
- It minimizes migration risk compared with replacing sandbox and avoids over-coupling production runtime to preview-gallery mechanics currently in App.tsx.

## Why Non-selected Options Were Rejected

Approach 1 rejected:
- Although faster initially, it forces production logic into a preview/gallery-oriented shell and increases long-term coupling and regression risk to design tooling.

Approach 3 rejected:
- Provides little MVP advantage over Approach 2 but carries materially higher disruption risk by deleting/replacing existing sandbox workflows and references.

## Clarifying Questions (if execution follows)

1. Should the new production package use Vite React (matching current frontend stack) or enforce Next.js as stated in phase-2-7 design/tasks text?
2. Should sandbox component assets be copied first, or should a shared UI package be extracted immediately?
3. What production URL/path strategy is preferred for running both sandbox and production dashboard in dev and CI?
