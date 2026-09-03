import createClient from "openapi-fetch";
import type { paths } from "../../../../packages/api-contracts/generated/schema"; // generated in Phase 9

const client = createClient<paths>({ baseUrl: import.meta.env.VITE_API_BASE_URL });

export interface MetricsSummaryData {
  recovery_rate: number;
  amount_recovered: number;
  amount_at_risk: number;
  exception_count: number;
  gate_blocked_count: number;
}

export interface LearningCurvePoint {
  event_index: number;
  cumulative_recovery_rate: number;
  sample_size?: number;
  bandit_arm?: string | null;
}

export interface AuditRow {
  event_id?: string;
  cause_category?: string | null;
  chosen_arm?: string | null;
  gate_result?: string | null;
  outcome_result?: string | null;
  error_code?: string | null;
  reason?: string | null;
}

export interface AuditTrailResponse {
  entries: AuditRow[];
}

export async function fetchMetricsSummary(runId: string) {
  const { data, error } = await client.GET("/v1/metrics/summary", { params: { query: { run_id: runId } } });
  if (error) throw new Error(`metrics summary fetch failed: ${JSON.stringify(error)}`);
  return data as MetricsSummaryData;
}

export async function fetchLearningCurve(runId: string, bucketSize = 20) {
  const { data, error } = await client.GET("/v1/metrics/learning-curve", {
    params: { query: { run_id: runId, bucket_size: bucketSize } },
  });
  if (error) throw new Error(`learning curve fetch failed: ${JSON.stringify(error)}`);
  return data as LearningCurvePoint[];
}

export async function fetchAuditTrail(filters: {
  episode_id?: string; cause_category?: string; chosen_arm?: string; outcome_result?: string; page?: number;
}) {
  const { data, error } = await client.GET("/v1/audit-trail", { params: { query: filters } });
  if (error) throw new Error(`audit trail fetch failed: ${JSON.stringify(error)}`);
  const response = data as AuditTrailResponse & { items?: AuditRow[] };
  return { ...response, entries: response.entries ?? response.items ?? [] };
}

export async function fetchExceptions(runId: string) {
  void runId;
  const response = await fetchAuditTrail({ page: 1 });
  return response.entries.filter((entry) => entry.outcome_result !== "recovered");
}
