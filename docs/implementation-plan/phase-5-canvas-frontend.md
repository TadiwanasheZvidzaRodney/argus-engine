# Phase 5 — Visual Canvas Frontend

> **Release:** R1 (read-only), R2 (live mode) · **Duration:** 7–8 weeks · **Depends on:** Phase 4 · **Owner:** Frontend + Design  
> **Entry criteria:** Topology API contract stable; MSW mocks available; design tokens and Storybook from Phase 0.

---

## 1. Objective

Deliver the interactive canvas that makes the graph understandable: nested account/region/VPC/subnet containers, expandable topology, search, inspector, live updates, and a visual language for security, health, and cost overlays that arrive in later phases.

At the end of this phase, a user can navigate a real 5k-node topology, understand relationships, find a resource in seconds, and watch changes appear without reloading.

---

## 2. Architecture mapping

| Architecture component | Phase 5 contribution |
|---|---|
| React Flow / WebGL graph visual topology engine | Canvas, nested groups, custom nodes/edges, layout |
| TanStack Query + Zustand | Server-state cache, graph entity store, UI state |
| WebSockets / SSE | Live delta client, reconnect/resync, change highlighting |
| AWS MCP interactive command engine | Action entry points and diff overlay scaffolding (execution in Phase 6) |
| Live metrics/overlays | Overlay slots and visual states for Phase 7/8 |

---

## 3. Scope

### In scope

- Next.js app shell, tenant/account/region navigation, protected routes.
- React Flow canvas with custom AWS resource nodes and relationship edges.
- Nested containers for account, region, VPC, and subnet.
- ELK-based layout in a web worker, with manual position preservation.
- Viewport-driven lazy loading and progressive expansion.
- Normalized client graph store with delta application and resync.
- Resource inspector with attributes, tags, relationships, raw JSON, and recent changes.
- Search, command palette, filters, highlight, and zoom-to-resource.
- Visual system for service icons, states, edge types, legend, and overlays.
- Performance work for large graphs: culling, level of detail, clustering.
- Accessibility, empty/loading/error states, onboarding tour.
- Playwright E2E, visual regression, and performance budgets.

### Out of scope

- Mutation planning/execution UI (Phase 6 adds actions and diff review).
- Metrics charts and security findings content (Phase 7).
- Cost overlays and 3D view (Phase 8).
- Custom user layouts saved per user (Phase 5 stores view state locally; server-side saved views later).
- Real-time collaboration/presence cursors.
- Mobile-optimized canvas (responsive read-only views only).

---

## 4. Core UX flows

### Flow A — First exploration

1. User signs in and selects tenant, account(s), and region(s).
2. Canvas loads an account/region overview with VPC clusters and resource counts.
3. User expands a VPC → subnets → resources.
4. User selects a resource → inspector opens with details and relationships.
5. User searches for a resource → canvas focuses and highlights it.

### Flow B — Investigate connectivity

1. User selects an EC2 instance.
2. Inspector shows security groups, subnet, route table, IAM role.
3. User clicks a relationship → canvas highlights the path.
4. User opens path mode → source/target selection → shortest path highlighted.

### Flow C — Live change

1. A resource changes in AWS.
2. WS delta arrives; affected node pulses and its state badge updates.
3. If the node is off-screen, a "N changes" toast appears; clicking focuses the change.
4. If a sequence gap is detected, a stale banner appears and the viewport resyncs.

### Flow D — Prepare an action (Phase 6 hook)

1. User drags from an EC2 node toward an S3 bucket.
2. Canvas enters connection mode and proposes relationship types.
3. UI calls the Phase 6 intent API and shows a plan/diff overlay.
4. Until Phase 6 ships, the action entry point is feature-flagged off.

---

## 5. Workstreams and tasks

### WS-FE-A — Application shell and navigation

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P5-01 | App shell and routes | Authenticated layout, workspace switcher, settings, audit links | L | Frontend |
| P5-02 | Tenant/account/region context | Global scope selector, URL synchronization, persisted preference | M | Frontend |
| P5-03 | Navigation and breadcrumbs | Account → region → VPC → subnet → resource breadcrumb | M | Frontend |
| P5-04 | Session and error handling | Token refresh, 401/403 flows, error boundaries, offline banner | M | Frontend |
| P5-05 | Settings and preferences | Theme, reduced motion, default scope, canvas density | S | Frontend |

### WS-FE-B — Canvas engine

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P5-06 | React Flow foundation | Canvas, pan/zoom, minimap, controls, background, selection box | L | Frontend |
| P5-07 | Custom node system | Base resource card, per-service icons, state badges, compact/expanded modes | L | Frontend + Design |
| P5-08 | Custom edge system | Relationship styles, labels on hover, direction, aggregation of parallel edges | M | Frontend |
| P5-09 | Nested containers | Account/region/VPC/subnet group nodes with `parentId`, collapse/expand, extent | L | Frontend |
| P5-10 | Container focus mode | Focus a VPC/subnet, dim outside, breadcrumb navigation | M | Frontend |
| P5-11 | Node interactions | Select, multi-select, hover, context menu, keyboard actions, copy ARN | M | Frontend |
| P5-12 | View state | Persist viewport, expanded containers, filters, and selection in URL/local storage | M | Frontend |

### WS-FE-C — Data and state

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P5-13 | API client and hooks | Generated SDK, TanStack Query hooks, error normalization | M | Frontend |
| P5-14 | Normalized graph store | Zustand entities for nodes/edges/groups, selectors, batched updates | L | Frontend |
| P5-15 | Viewport-driven loading | Load visible scope; fetch children on expand; prefetch on hover | L | Frontend |
| P5-16 | Pagination and truncation UX | "Load more", counts, partial-result indicators | M | Frontend |
| P5-17 | Cache and refetch policy | Stale times, background refetch, manual refresh, focus refetch rules | M | Frontend |
| P5-18 | URL state and shareable views | Encode scope, filters, selection, focus in query params | M | Frontend |
| P5-19 | Optimistic UI | Immediate expand/collapse and selection; reconcile with server data | M | Frontend |

### WS-FE-D — Layout and performance

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P5-20 | ELK layout in worker | Hierarchical layout for nested graphs, deterministic seeds | L | Frontend |
| P5-21 | Incremental layout | Layout only new/changed subgraphs; preserve manual positions | L | Frontend |
| P5-22 | Level of detail | Cluster at low zoom; hide labels/edges by zoom threshold | L | Frontend |
| P5-23 | Rendering performance | `onlyRenderVisibleElements`, memoized node/edge types, batched changes | L | Frontend |
| P5-24 | Large-graph benchmark | 5k nodes/15k edges scenario; frame budget and memory profiling | L | Frontend + QA |
| P5-25 | Edge aggregation | Bundle parallel/duplicate relationships to reduce visual noise | M | Frontend |
| P5-26 | Animation policy | Reduced-motion support; cap animation duration; avoid layout thrash | S | Frontend |

### WS-FE-E — Search, filters, and inspector

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P5-27 | Command palette | Cmd/Ctrl+K, search, recent items, actions, keyboard navigation | L | Frontend |
| P5-28 | Filter panel | Type, account, region, state, tag, security severity placeholder | M | Frontend |
| P5-29 | Search result highlighting | Focus/zoom to node, highlight matches, clear search | M | Frontend |
| P5-30 | Inspector drawer | Overview, attributes, tags, relationships, raw JSON, copy, deep links | L | Frontend |
| P5-31 | Relationship explorer | Group by type, navigate to related node, path highlight | M | Frontend |
| P5-32 | Recent changes panel | Last events for resource from Phase 3 lineage | M | Frontend |
| P5-33 | Empty/error states | No accounts, no resources, permission gaps, API errors, stale data | M | Frontend |

### WS-FE-F — Live updates

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P5-34 | WS client | Singleton, auth ticket, reconnect with backoff, heartbeat | L | Frontend |
| P5-35 | Subscription manager | Subscribe to visible accounts/regions/resources; update on viewport change | L | Frontend |
| P5-36 | Delta application | Apply to graph store, check sequence, batch via rAF, ignore stale deltas | L | Frontend |
| P5-37 | Gap detection and resync | Detect seq gap; show stale banner; refetch viewport | M | Frontend |
| P5-38 | Change highlighting | Pulse/animate changed nodes; change feed; focus on change | M | Frontend |
| P5-39 | Connection UX | Live/paused/offline indicator; manual pause; polling fallback | M | Frontend |
| P5-40 | Live activity log | Debug panel for event stream (feature-flagged) | S | Frontend |

### WS-FE-G — Visual design and overlays

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P5-41 | AWS iconography | Official icon set with licensing review; fallback glyphs | M | Design |
| P5-42 | Node visual language | Type, state, account/region accents, density modes, severity slot | L | Design + Frontend |
| P5-43 | Edge visual language | Network, IAM, encryption, dependency styles; legend | M | Design |
| P5-44 | Overlay framework | Layer toggles and render slots for security, metrics, cost | M | Frontend |
| P5-45 | Diff overlay scaffolding | Pending/added/removed/error states for Phase 6 | M | Frontend |
| P5-46 | Empty and onboarding states | Guided first-run, sample view, setup checklist | M | Design + Frontend |

### WS-FE-H — Accessibility and quality

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P5-47 | Keyboard navigation | Focus order, shortcuts, escape behavior, canvas alternatives | L | Frontend |
| P5-48 | Screen-reader support | Node labels, inspector semantics, live-region announcements | M | Frontend |
| P5-49 | List/table alternative | Accessible tabular view of the current topology | M | Frontend |
| P5-50 | Color and contrast | Colorblind-safe palette; severity not encoded by color alone | M | Design |
| P5-51 | E2E suite | Playwright flows for exploration, search, inspector, live updates | L | QA + Frontend |
| P5-52 | Visual regression | Storybook/Chromatic snapshots for key components and states | M | Frontend |
| P5-53 | Performance monitoring | RUM metrics, long-task tracking, Web Vitals | M | Frontend + Platform |
| P5-54 | Usability test | 5 target users; task success and time-on-task; iterate | M | Product + Design |

---

## 6. Deliverables

- Authenticated Next.js application shell with scope navigation.
- React Flow canvas with custom nodes, edges, nested containers, and focus mode.
- ELK layout in a web worker with incremental updates and manual position preservation.
- Viewport-driven data loading and normalized graph store.
- Command palette, filters, search highlighting, and inspector.
- Live WebSocket mode with sequence checking, resync, and change highlighting.
- Visual system for services, states, relationships, and overlay slots.
- Accessibility support including keyboard navigation and a table alternative.
- E2E, visual regression, performance, and usability reports.
- Feature flags for live mode, overlays, and future actions.

---

## 7. Interfaces and contracts

### Graph store shape

```ts
type GraphState = {
  nodes: Record<string, GraphNode>;
  edges: Record<string, GraphEdge>;
  groups: Record<string, GraphGroup>;
  children: Record<string, string[]>;   // parent -> child IDs
  expanded: Set<string>;
  seq: number;
  status: "idle" | "loading" | "live" | "stale" | "offline" | "error";
  pendingChanges: string[];
};
```

Rules:

- Server responses hydrate entities; they never replace the whole store unless a full resync is requested.
- WS deltas patch entities and bump `seq` only when contiguous.
- A gap sets `status = "stale"` and triggers a viewport refetch; deltas are queued or dropped until resync.
- UI state (selection, hover, filters, panel open) lives outside the graph entities to avoid unnecessary canvas re-renders.

### Component boundaries

```text
<CanvasPage>
  <ScopeBar />
  <CanvasToolbar />
  <TopologyCanvas>
    <ReactFlow>
      <ContainerNode />
      <ResourceNode />
      <RelationshipEdge />
    </ReactFlow>
  </TopologyCanvas>
  <InspectorDrawer />
  <CommandPalette />
  <ChangeFeed />
  <ConnectionStatus />
</CanvasPage>
```

### Performance budgets

| Metric | Target |
|---|---|
| Initial canvas interactive (1k visible nodes) | < 2s on a mid-tier laptop |
| Pan/zoom frame rate | ≥ 45fps target, 30fps floor |
| Node selection response | < 100ms |
| Search open and first results | < 300ms |
| Delta apply to visible node | < 100ms after receipt |
| Memory for 5k nodes/15k edges | < 500MB browser tab |
| Layout of 1k new nodes | < 1s in worker |

---

## 8. Data and schema changes

- No new backend tables.
- Frontend persists view state in URL and IndexedDB/localStorage (non-sensitive only).
- Saved views and shared links use URL-encoded state; no server-side persistence in Phase 5.
- Analytics events (privacy-reviewed): canvas load, search, expand, inspector open, filter use, live pause, resync.
- Feature flags: `canvas.live`, `canvas.overlays`, `canvas.actions`, `canvas.3d`.

---

## 9. Exit gate / acceptance criteria

- [ ] A user can sign in, select accounts/regions, and explore a real topology.
- [ ] Account → region → VPC → subnet → resource nesting works with collapse/expand and breadcrumbs.
- [ ] Layout is deterministic, readable, and preserves manual positions across refreshes.
- [ ] 5k-node graph with 15k edges meets the performance budgets above.
- [ ] Viewport loading fetches only visible/expanded scope; no full-graph download.
- [ ] Search finds resources by name, ARN, tag, and IP; selection zooms and highlights.
- [ ] Inspector shows attributes, tags, relationships, raw payload link, and recent changes.
- [ ] Live mode applies deltas, highlights changes, and resyncs on sequence gaps.
- [ ] Polling/manual refresh fallback works when WebSocket is unavailable.
- [ ] Keyboard navigation, screen-reader labels, reduced motion, and table alternative pass an accessibility audit.
- [ ] E2E and visual regression suites are green in CI.
- [ ] Usability test meets task-success targets; top issues fixed or scheduled.
- [ ] R1 demo: a user unfamiliar with the system can find a publicly exposed resource and explain its network path in < 3 minutes.

---

## 10. Test and validation plan

| Layer | Tests |
|---|---|
| Unit | Graph store reducers, delta application, sequence logic, selectors, layout helpers |
| Component | Storybook states for nodes, edges, inspector, toolbar, empty/error |
| Integration | Mocked API + mock WS server; expand, search, inspect, live update, resync |
| E2E | Playwright against staging with seeded tenants and topology fixtures |
| Performance | Playwright trace + Chrome DevTools; 5k/15k scenario; memory and long tasks |
| Accessibility | axe-core, keyboard-only run, screen-reader smoke test |
| Visual | Chromatic/Percy snapshots for light/dark, density, severity states |
| Resilience | WS disconnect, slow API, partial failure, stale cursor, offline |

**Mock WS harness:** Build a deterministic test server that can emit deltas at controlled rates, create sequence gaps, disconnect, and replay. It is reused in Phase 6 for action progress.

---

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| React Flow DOM performance at 5k+ nodes | LOD/clustering, viewport culling, caps, WebGL evaluation for macro view |
| Nested layout instability | ELK in worker, deterministic seeds, preserve manual positions, incremental layout |
| Delta application causes render storms | Batched rAF updates, normalized store, selectors, only update changed nodes |
| Live updates confuse users | Change highlights, activity feed, pause control, stale banner |
| Canvas is inaccessible | Table alternative, keyboard navigation, ARIA live announcements |
| AWS icon licensing | Use official AWS Architecture Icons under their terms; review before release |
| Frontend/backend contract drift | Generated SDK, MSW parity, contract tests in CI |
| Scope creep into actions | Feature-flag action entry points; defer to Phase 6 |

---

## 12. Metrics

- Canvas load time p50/p95.
- Time to first meaningful topology.
- Frame rate and long-task count during pan/zoom.
- Search success rate (result clicked within 10s).
- Inspector open rate and relationship navigation rate.
- Live delta apply latency (client receipt to paint).
- Resync rate and stale-time duration.
- WebSocket disconnect rate and reconnect success.
- Task success and time-on-task in usability tests.
- Frontend error rate and Web Vitals (LCP, INP, CLS).

---

## 13. Handoff to Phase 6

Phase 6 can assume:

- A stable canvas with node/edge selection, drag handles, and context menus.
- A diff overlay framework with pending/added/removed/error visual states.
- A WS client that can carry new message types (action progress).
- Inspector and relationship navigation for action context.
- Feature flag infrastructure for action entry points.
