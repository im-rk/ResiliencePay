# Phase 10 — Dashboard — Full Detailed Spec

**Depends on:** Phase 9 (the API it exclusively consumes)
**Unblocks:** your live demo — this is what judges watch for 4 minutes
**Owner:** frontend/product-strongest team member
**Estimated time:** ~1.5–2 days

---

## 1. Why this phase exists and why it matters more than it looks

Every phase before this one produces evidence — a working bandit, a
compliance gate, an audit trail, a batch comparison. None of that evidence
is legible to a judge unless something renders it. This phase is not "the
UI phase" in the sense of decoration; it is the **evidence-presentation
layer**, and the standard to hold it to is: *could a judge, looking at this
screen with zero prior context, understand what the system just did and
why, in under 10 seconds per panel?* If the answer is no, the panel isn't
done, no matter how much backend rigor sits behind it.

This phase also carries a specific risk worth naming directly: it's the
part of the system most likely to be built under the most time pressure
(it's last in the dependency chain), and UI code that's rushed tends to
fail in exactly the way that's most visible — a blank screen, a spinner
that never resolves, a crash on an empty dataset — precisely during a live
demo, in front of the audience whose opinion matters most. Treat the
loading/error/empty states here with the same rigor as Phase 4's gate
rules; they are the equivalent of edge cases in a UI context, and they are
just as likely to be the thing that actually goes wrong live.

---

## 2. Conceptual model — read this before touching code

### 2.1 Why this is "one screen," not "a product," and why that's a real constraint, not a shortcut

A dashboard with navigation, multiple pages, and a component library
signals "we built a SaaS product." A single, dense, well-organized screen
with five panels signals "we built a tool to understand a system" — which
is the actually correct framing for a 4-minute demo. Every additional
screen, route, or navigation affordance is a place your presenter can get
lost live, a place state can go stale, and a place you can spend an hour
you don't have. Discipline here is not a compromise; it's the right design
choice for the medium (a judge watching a screen-share for four minutes,
not a user exploring a product over days).

### 2.2 Why the typed API client (from Phase 9 / `PRODUCTION_ENGINEERING_STANDARDS.md` §1) is not optional polish

If the dashboard hand-writes its own TypeScript interfaces describing what
`/v1/metrics/summary` returns, there are now two independent sources of
truth for that shape — the actual FastAPI/Pydantic DTO, and whatever the
frontend developer typed by hand, possibly from memory, possibly slightly
stale. The moment those two drift (someone renames a field on the backend
and forgets to tell the frontend), you get a runtime bug that is invisible
until someone actually looks at the rendered panel and notices a number is
missing or `undefined` — which is exactly the kind of bug that surfaces
live, at the worst possible time. Importing generated types from
`packages/api-contracts/generated/` makes this class of bug a compile-time
TypeScript error instead, caught the moment you build, not the moment you
demo.

### 2.3 Why polling, not WebSockets — and why this decision needs an explicit abstraction seam

Section design trade-off already made in `TECH_STACK.md`: polling every
5-10 seconds via React Query is the sized-right choice here — a WebSocket's
connection lifecycle (reconnect logic, backpressure, auth handshake) is
real complexity that buys you sub-second updates nobody needs for a
4-minute demo watched by humans. But make this decision **swappable**, not
just "the current implementation" — wrap all data-fetching behind a
`usePolling` hook so that if you ever do want to upgrade to push-based
updates (e.g., if a judge specifically asks "can you make this update
instantly"), it's a contained change inside one hook, not a rewrite of five
panel components.

### 2.4 Why the Exception List is a first-class panel, not an afterthought tab

It would be easy to treat "18 of 200 events we couldn't recover" as
something to hide, bury in a secondary tab, or mention only if asked. Do
the opposite. Per `TESTING_METRICS.md`, a non-zero exception rate is
*evidence of honest measurement* — a 0% exception rate would actually be a
red flag to a sharp judge (real-world recovery is never 100%). Placing this
panel at the same visual priority as the recovery-rate metric is a
deliberate credibility move: it signals "we're not hiding our failure
modes," which is precisely the framing the buildathon's own "what broke and
how you got out" philosophy rewards.

---

## 3. Detailed component design

### 3.1 `apps/dashboard/src/api/client.ts` — the typed client wrapper

```typescript
import createClient from "openapi-fetch";
import type { paths } from "@/packages/api-contracts/generated/schema"; // generated in Phase 9

const client = createClient<paths>({ baseUrl: import.meta.env.VITE_API_BASE_URL });

export async function fetchMetricsSummary(runId: string) {
  const { data, error } = await client.GET("/v1/metrics/summary", { params: { query: { run_id: runId } } });
  if (error) throw new Error(`metrics summary fetch failed: ${JSON.stringify(error)}`);
  return data;
}

export async function fetchLearningCurve(runId: string, bucketSize = 20) {
  const { data, error } = await client.GET("/v1/metrics/learning-curve", {
    params: { query: { run_id: runId, bucket_size: bucketSize } },
  });
  if (error) throw new Error(`learning curve fetch failed: ${JSON.stringify(error)}`);
  return data;
}

export async function fetchAuditTrail(filters: {
  episode_id?: string; cause_category?: string; chosen_arm?: string; outcome_result?: string; page?: number;
}) {
  const { data, error } = await client.GET("/v1/audit-trail", { params: { query: filters } });
  if (error) throw new Error(`audit trail fetch failed: ${JSON.stringify(error)}`);
  return data;
}
```

**Note the explicit error-throwing on every call** — `openapi-fetch`
returns a `{data, error}` tuple rather than throwing; converting it to a
thrown error here means React Query's built-in error state handling (used
by every panel below) works correctly without each panel needing its own
`if (error) ...` branch on the raw tuple.

### 3.2 `apps/dashboard/src/hooks/usePolling.ts`

```typescript
import { useQuery, UseQueryOptions } from "@tanstack/react-query";

export function usePolling<T>(
  queryKey: readonly unknown[],
  fetchFn: () => Promise<T>,
  intervalMs = 7000,
  options?: Partial<UseQueryOptions<T>>
) {
  return useQuery({
    queryKey,
    queryFn: fetchFn,
    refetchInterval: intervalMs,
    retry: 2, // React Query's built-in retry — handles a single transient network blip transparently
    ...options,
  });
}
```

### 3.3 `apps/dashboard/src/panels/MetricsSummary.tsx`

```tsx
import { usePolling } from "@/hooks/usePolling";
import { fetchMetricsSummary } from "@/api/client";
import { formatPaise } from "@/lib/format";

export function MetricsSummary({ banditRunId, baselineRunId }: { banditRunId: string; baselineRunId: string }) {
  const bandit = usePolling(["metrics", banditRunId], () => fetchMetricsSummary(banditRunId));
  const baseline = usePolling(["metrics", baselineRunId], () => fetchMetricsSummary(baselineRunId));

  if (bandit.isLoading || baseline.isLoading) return <MetricsSkeleton />;
  if (bandit.isError || baseline.isError) return <PanelError message="Could not load metrics — retrying automatically." />;

  const lift = bandit.data!.recovery_rate - baseline.data!.recovery_rate;

  return (
    <div className="metrics-summary">
      <table>
        <thead><tr><th></th><th>Baseline</th><th>Agent</th><th>Lift</th></tr></thead>
        <tbody>
          <tr>
            <td>Recovery rate</td>
            <td>{(baseline.data!.recovery_rate * 100).toFixed(1)}%</td>
            <td>{(bandit.data!.recovery_rate * 100).toFixed(1)}%</td>
            <td className={lift > 0 ? "positive" : "negative"}>{(lift * 100).toFixed(1)} pts</td>
          </tr>
          <tr>
            <td>₹ recovered</td>
            <td>{formatPaise(baseline.data!.amount_recovered)}</td>
            <td>{formatPaise(bandit.data!.amount_recovered)}</td>
            <td>{formatPaise(bandit.data!.amount_recovered - baseline.data!.amount_recovered)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
```

**Explicit loading and error branches, before the happy path** — this is
the pattern to repeat in every panel below without exception. A panel that
only handles the happy path is a panel that will show a broken UI the
moment a request is slow or fails, which is a near-certainty at some point
during a live demo relying on network calls.

### 3.4 `apps/dashboard/src/panels/ExceptionList.tsx`

```tsx
export function ExceptionList({ runId }: { runId: string }) {
  const { data, isLoading, isError } = usePolling(["exceptions", runId], () => fetchExceptions(runId));

  if (isLoading) return <PanelSkeleton label="Loading exceptions…" />;
  if (isError) return <PanelError message="Could not load exceptions." />;

  if (data!.length === 0) {
    // Deliberately explicit — see section 2.4. A 0-length result renders a
    // clear, honest empty state, not a blank div that looks like a bug.
    return (
      <div className="exception-list-empty">
        <strong>0 unresolved exceptions.</strong>
        <p>Every event in this batch reached a terminal, explained state.</p>
      </div>
    );
  }

  return (
    <ul className="exception-list">
      {data!.map((ex) => (
        <li key={ex.event_id}>
          <span className="cause">{ex.cause_category}</span>
          <span className="reason">{ex.reason}</span>
        </li>
      ))}
    </ul>
  );
}
```

### 3.5 `apps/dashboard/src/panels/AuditTrailTable.tsx`

```tsx
export function AuditTrailTable() {
  const [filters, setFilters] = useState<AuditFilters>({});
  const { data, isLoading, isError } = usePolling(["audit-trail", filters], () => fetchAuditTrail(filters), 10000);

  return (
    <div className="audit-trail">
      <AuditFilterBar filters={filters} onChange={setFilters} />
      {isLoading && <PanelSkeleton label="Loading audit trail…" />}
      {isError && <PanelError message="Could not load audit trail." />}
      {data && (
        <table>
          <thead>
            <tr><th>Time</th><th>Cause</th><th>Arm</th><th>Gate</th><th>Simulated</th><th>Outcome</th></tr>
          </thead>
          <tbody>
            {data.entries.map((row) => (
              <tr key={row.audit_id} className={row.gate_result === false ? "row-blocked" : ""}>
                <td>{formatTime(row.recorded_at)}</td>
                <td>{row.cause_category ?? "—"}</td>
                <td>{row.chosen_arm ?? "—"}</td>
                <td>{row.gate_result === false ? "Blocked" : "Passed"}</td>
                <td>{row.simulated ? "Simulated" : "Real"}</td>
                <td>{row.outcome_result ?? "pending"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
```

**Every "Simulated" vs "Real" cell renders unconditionally, from the DTO's
explicit `simulated` boolean** (see `PRODUCTION_ENGINEERING_STANDARDS.md`
§1) — never inferred client-side from the arm name. This is the dashboard's
half of the "structurally impossible to mislabel a simulated action as
real" guarantee that starts at the database schema.

### 3.6 `apps/dashboard/src/panels/LearningCurveChart.tsx`

```tsx
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, CartesianGrid } from "recharts";

export function LearningCurveChart({ banditRunId, baselineRunId }: { banditRunId: string; baselineRunId: string }) {
  const bandit = usePolling(["learning-curve", banditRunId], () => fetchLearningCurve(banditRunId));
  const baseline = usePolling(["learning-curve", baselineRunId], () => fetchLearningCurve(baselineRunId));

  if (bandit.isLoading || baseline.isLoading) return <PanelSkeleton label="Loading learning curve…" />;
  if (bandit.isError || baseline.isError) return <PanelError message="Could not load learning curve." />;

  const merged = mergeCurvesByBatchIndex(bandit.data!, baseline.data!); // [{batchIndex, banditRate, baselineRate}, ...]

  return (
    <LineChart width={600} height={300} data={merged}>
      <CartesianGrid strokeDasharray="3 3" />
      <XAxis dataKey="batchIndex" label={{ value: "Batch index", position: "insideBottom" }} />
      <YAxis domain={[0, 1]} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
      <Tooltip formatter={(v: number) => `${(v * 100).toFixed(1)}%`} />
      <Legend />
      <Line type="monotone" dataKey="banditRate" name="Agent (learning)" stroke="#2563eb" strokeWidth={2} />
      <Line type="monotone" dataKey="baselineRate" name="Baseline (naive)" stroke="#9ca3af" strokeWidth={2} strokeDasharray="4 4" />
    </LineChart>
  );
}
```

---

## 4. Full edge-case matrix (expanded)

| # | Case | Expected behavior | How to test |
|---|---|---|---|
| 1 | API returns zero exceptions | Explicit "0 unresolved exceptions" empty state, not a blank panel | Component test in §5.1 |
| 2 | `run_id` not yet computed (batch still running) | `MetricsSummary` shows a loading skeleton, not a crash or `undefined` values rendered as text | Component test with a pending/never-resolving mocked query |
| 3 | API request fails mid-demo (network blip) | Panel shows a retry-able error state; React Query's `retry: 2` attempts recovery automatically before surfacing the error | Component test forcing a fetch rejection, asserting the error UI renders and doesn't crash the rest of the page |
| 4 | `AuditTrailTable` filter combination returns 0 rows | Table renders an explicit "no matching audit entries" row, not an empty `<tbody>` that looks broken | Component test with a mocked empty response |
| 5 | Learning curve data for bandit and baseline have different batch-index ranges (e.g., different `n`) | `mergeCurvesByBatchIndex` aligns on the shorter series' range, does not crash on a length mismatch | Unit test for the merge function with mismatched-length inputs |
| 6 | A single audit row has `simulated: null` (data integrity issue upstream) | Renders as "—" or "Unknown," never silently coerced to `false` (which would misleadingly imply "real") | Component test with `simulated: null` in mock data, assert the cell does NOT render "Real" |
| 7 | Amount value is `0` (a genuinely zero recovery) | `formatPaise(0)` renders "₹0.00", not blank or "N/A" — zero is a valid, meaningful value here, not a missing-data sentinel | Unit test on `formatPaise` |

---

## 5. Test plan — with actual test code to implement

### 5.1 `apps/dashboard/src/panels/__tests__/ExceptionList.test.tsx`

```tsx
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ExceptionList } from "../ExceptionList";
import * as apiClient from "@/api/client";

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

test("renders explicit empty state at zero exceptions", async () => {
  vi.spyOn(apiClient, "fetchExceptions").mockResolvedValue([]);
  renderWithClient(<ExceptionList runId="run-1" />);
  expect(await screen.findByText(/0 unresolved exceptions/i)).toBeInTheDocument();
});

test("renders exception rows at non-zero count", async () => {
  vi.spyOn(apiClient, "fetchExceptions").mockResolvedValue([
    { event_id: "e1", cause_category: "hard_decline", reason: "3 attempts exhausted" },
  ]);
  renderWithClient(<ExceptionList runId="run-1" />);
  expect(await screen.findByText("hard_decline")).toBeInTheDocument();
});

test("renders error state on fetch failure without crashing", async () => {
  vi.spyOn(apiClient, "fetchExceptions").mockRejectedValue(new Error("network error"));
  renderWithClient(<ExceptionList runId="run-1" />);
  expect(await screen.findByText(/could not load exceptions/i)).toBeInTheDocument();
});
```

### 5.2 `apps/dashboard/src/lib/__tests__/format.test.ts`

```typescript
import { formatPaise } from "../format";

test("formats zero as a valid currency value, not a placeholder", () => {
  expect(formatPaise(0)).toBe("₹0.00");
});

test("formats a typical amount correctly", () => {
  expect(formatPaise(149900)).toBe("₹1,499.00");
});
```

### 5.3 `apps/dashboard/src/lib/__tests__/mergeCurves.test.ts`

```typescript
import { mergeCurvesByBatchIndex } from "../mergeCurves";

test("aligns series of mismatched length without crashing", () => {
  const bandit = [{ batchIndex: 0, rate: 0.2 }, { batchIndex: 1, rate: 0.5 }, { batchIndex: 2, rate: 0.7 }];
  const baseline = [{ batchIndex: 0, rate: 0.2 }, { batchIndex: 1, rate: 0.22 }];
  const merged = mergeCurvesByBatchIndex(bandit, baseline);
  expect(merged).toHaveLength(2); // aligned to the shorter series
  expect(merged[1]).toMatchObject({ banditRate: 0.5, baselineRate: 0.22 });
});
```

### 5.4 `apps/dashboard/src/panels/__tests__/AuditTrailTable.test.tsx`

```tsx
test("never renders simulated=null as Real", async () => {
  vi.spyOn(apiClient, "fetchAuditTrail").mockResolvedValue({
    entries: [{ audit_id: 1, cause_category: "otp_failure", chosen_arm: "retry_immediate",
                gate_result: true, simulated: null, outcome_result: "recovered", recorded_at: "2026-08-20T10:00:00Z" }],
  });
  renderWithClient(<AuditTrailTable />);
  const cell = await screen.findByText(/otp_failure/i);
  const row = cell.closest("tr")!;
  expect(within(row).queryByText("Real")).not.toBeInTheDocument();
});
```

---

## 6. Observability — what to surface visibly, not just log

Every panel should render the `request_id` (from
`PRODUCTION_ENGINEERING_STANDARDS.md` §5) in a small, unobtrusive corner
element or a "debug info" expandable section — this turns "something looks
wrong" during a live demo into "here's the exact request ID, let's grep the
logs together," a materially stronger position than "let me check
something" while judges wait.

---

## 7. Definition of Done (full checklist)

- [ ] All 5 panels (live feed, metrics summary, learning curve, audit trail, exceptions) wired to real `/v1` endpoints via the generated typed client — no hand-written response interfaces.
- [ ] Every panel has explicit loading, error, and empty states — verified by a test per state, per panel, not just the happy path.
- [ ] `ExceptionList` at zero count renders an explicit, positively-framed empty state, not a blank panel.
- [ ] `AuditTrailTable` never renders `simulated: null` as "Real" — verified by a dedicated test.
- [ ] `formatPaise(0)` renders as a valid currency value, not a placeholder — verified by a unit test.
- [ ] `mergeCurvesByBatchIndex` handles mismatched-length input series without crashing.
- [ ] `usePolling` is the single, swappable seam for all data-fetching — no panel implements its own ad hoc polling logic.
- [ ] A `docker-compose up` fresh run, followed by one batch execution, produces a fully populated dashboard with zero manual data massaging.

---

## 8. Prompts for your coding agent

Use these as focused, sequential prompts. `CLAUDE.md`'s repo-wide standards
apply automatically; these assume that context is already loaded (see
`docs/AGENT_KICKOFF_PROMPT.md`).

### Prompt 1 — Typed API client and polling hook
```
Implement apps/dashboard/src/api/client.ts and
apps/dashboard/src/hooks/usePolling.ts per docs/phases/PHASE_10_dashboard_DETAILED.md
sections 3.1 and 3.2. The client must import types from
packages/api-contracts/generated/schema.ts (generated in Phase 9) — do not
hand-write response interfaces; if that generated file doesn't exist yet in
this session, tell me explicitly rather than stubbing a parallel type
definition that will drift. Every client function must convert
openapi-fetch's {data, error} tuple into a thrown error on failure, so
React Query's built-in error handling works uniformly across every panel.
```

### Prompt 2 — Format and merge utilities with edge-case tests first
```
Implement apps/dashboard/src/lib/format.ts (formatPaise and a date
formatter) and apps/dashboard/src/lib/mergeCurves.ts
(mergeCurvesByBatchIndex) per docs/phases/PHASE_10_dashboard_DETAILED.md.
Write the tests in section 5.2 and 5.3 of that doc FIRST, including the
zero-amount and mismatched-length-series cases, then implement the
functions to satisfy them. formatPaise(0) must render as a valid currency
string, never a placeholder like "N/A" or an empty string — zero paise is
meaningful data, not missing data.
```

### Prompt 3 — MetricsSummary and LearningCurveChart panels
```
Implement apps/dashboard/src/panels/MetricsSummary.tsx and
LearningCurveChart.tsx per docs/phases/PHASE_10_dashboard_DETAILED.md
sections 3.3 and 3.6. Both panels must handle loading and error states
explicitly, BEFORE the happy-path render — do not write a panel that only
handles the successful-fetch case and add error handling later. Use
Recharts for the chart exactly as specified, with the agent's line
solid/blue and the baseline's line dashed/gray so they're visually
distinguishable even in a black-and-white screenshot.
```

### Prompt 4 — ExceptionList and AuditTrailTable with the simulated-null test
```
Implement apps/dashboard/src/panels/ExceptionList.tsx and
AuditTrailTable.tsx per docs/phases/PHASE_10_dashboard_DETAILED.md sections
3.4 and 3.5. ExceptionList's zero-count state must be an explicit,
positively-framed message ("0 unresolved exceptions... every event reached
a terminal, explained state"), not a blank div. AuditTrailTable must render
the simulated/real distinction directly from the DTO's boolean field,
never inferred from arm name client-side, and must render simulated:null
as an explicit "Unknown" or "—", never silently as "Real". Write
apps/dashboard/src/panels/__tests__/ExceptionList.test.tsx and
AuditTrailTable.test.tsx exactly per sections 5.1 and 5.4 of the doc,
including the simulated-null test — this specific test is the most
important one in this prompt, don't skip it even under time pressure.
```

### Prompt 5 — Full wiring, request_id surfacing, and Definition of Done pass
```
Wire all 5 panels into apps/dashboard/src/App.tsx as a single dense
dashboard layout (not multiple routes/pages — see
docs/phases/PHASE_10_dashboard_DETAILED.md section 2.1 for why this is a
deliberate constraint, not a shortcut). Add a small, unobtrusive
request_id display per section 6 of the doc, sourced from the
X-Request-ID response header on the most recent API call. Then run
`docker-compose up` (or the local dev equivalent), execute one Phase 8
batch run, and confirm the dashboard populates fully with zero manual data
massaging — show me a description of what actually rendered, not just "it
works." Finally work through the Definition of Done checklist in section 7
of the doc and report back which items pass, with actual test output for
every relevant test file.
```
