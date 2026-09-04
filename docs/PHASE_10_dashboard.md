# Phase 10 — Dashboard

**Depends on:** Phase 9 (the API it exclusively consumes)
**Unblocks:** your live demo — this is what judges watch for 4 minutes
**Owner:** frontend/product-strongest team member
**Estimated time:** ~1.5-2 days

## Objective
Make the system's behavior legible at a glance. This is one demo screen,
not a product — treat scope discipline as seriously as the backend phases.

## Scope
**In scope:** exactly 5 panels (live feed, metrics summary, learning curve,
audit trail, exceptions), loading/error states for each.
**Out of scope:** auth, settings, onboarding, mobile responsiveness,
multi-merchant switching, animations beyond basic transitions.

## Deliverables mapped to monorepo paths

| Path | What goes here |
|---|---|
| `apps/dashboard/src/App.tsx` | Top-level layout, panel composition |
| `apps/dashboard/src/panels/LiveEventFeed.tsx` | Polling event stream, detect→diagnose→decide→act→outcome per row |
| `apps/dashboard/src/panels/MetricsSummary.tsx` | Baseline vs. agent before/after table |
| `apps/dashboard/src/panels/LearningCurveChart.tsx` | Recharts line chart, recovery rate over batch index |
| `apps/dashboard/src/panels/ArmDistributionChart.tsx` | Stacked area chart, arm selection shift over time |
| `apps/dashboard/src/panels/AuditTrailTable.tsx` | Filterable, paginated table |
| `apps/dashboard/src/panels/ExceptionList.tsx` | Unresolved events with reasons |
| `apps/dashboard/src/hooks/useMetrics.ts`, `useAuditTrail.ts`, `usePolling.ts` | React Query wrappers, shared polling abstraction |
| `apps/dashboard/src/api/client.ts` | Generated from `packages/api-contracts` |
| `apps/dashboard/src/lib/format.ts` | Paise→₹ formatting, date formatting |

## Detailed task breakdown

1. **Wire the typed API client** — import from
   `packages/api-contracts/generated`, never hand-write duplicate response
   interfaces (this is the payoff for Phase 9's contract export).

2. **`usePolling` hook** (abstracted so swapping to WebSocket later is
   contained):
   ```typescript
   function usePolling<T>(fetchFn: () => Promise<T>, intervalMs = 7000) {
     return useQuery({ queryKey: [fetchFn.name], queryFn: fetchFn, refetchInterval: intervalMs });
   }
   ```

3. **`MetricsSummary` panel** — renders the exact before/after table shape
   from `TESTING_METRICS.md` §7: recovery rate, ₹ recovered, avg
   time-to-recovery, lift — for baseline vs. agent, side by side.

4. **`LearningCurveChart`** — consumes
   `GET /v1/metrics/learning-curve?run_id=...`, renders two lines (agent
   trending upward, baseline flat) on the same Recharts `LineChart`.

5. **`AuditTrailTable`** — filters by `cause_category`, `chosen_arm`,
   `outcome_result`; each row expandable to show the full
   diagnose→decide→gate→act→outcome chain for that event — this is your
   answer to "show me the audit trail" live.

6. **`ExceptionList`** — deliberately styled as a credibility artifact, not
   hidden in a tab — "18 of 200 events we could not recover, here's why"
   should be one click away, not buried.

7. **Loading/error states, explicitly, for every panel** — don't let any
   panel render a blank screen while data loads or on API failure; this is
   exactly the kind of thing that breaks visibly and embarrassingly live if
   skipped.

## Edge-case matrix

| Case | Expected behavior |
|---|---|
| API returns zero exceptions | `ExceptionList` renders an explicit "0 exceptions" empty state, not a blank panel (and don't let a 0% exception rate go unquestioned — revisit Phase 2/8 data realism if this happens) |
| `run_id` not yet computed (batch still running) | `MetricsSummary` shows a loading skeleton, not a crash |
| API request fails (network blip during live demo) | Panel shows a retry-able error state, React Query's built-in retry kicks in automatically |

## Design decisions & trade-offs

| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| Data fetching | Polling vs. WebSocket | Polling (5-10s), abstracted behind a hook | WebSocket connection-lifecycle complexity isn't worth the engineering risk in 10 days for a demo dashboard |
| State management | Redux vs. React Query + local state | React Query for server state | Free caching, loading/error states, refetching — exactly what a metrics dashboard needs |
| Chart library | D3 (custom) vs. Recharts | Recharts | Correct, clean charts in far less time than custom D3 |

## Test plan
- **Component tests (Vitest + Testing Library):** `MetricsSummary` renders correct numbers given a mocked API response; `ExceptionList` renders correctly at zero and at non-zero counts.
- **Visual smoke test:** a snapshot/Storybook check on `LearningCurveChart` given a fixed data shape, catching regressions before demo day.

## Definition of Done
- [ ] Dashboard fully populated from a real batch run with zero manual data massaging.
- [ ] Loading and error states handled visibly for every panel.
- [ ] All 5 panels wired to real `/v1/` endpoints via the generated typed client.

## Handoff to Phase 11 & 12
Phase 11 assumes: the dashboard can visibly reflect a fault-injection event
live (e.g., a panel showing a `failed`/`blocked` action clearly, not
crashing). Phase 12 assumes: this is the exact screen rehearsed in
`DEMO_SCRIPT.md`.
