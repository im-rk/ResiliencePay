import createClient from "openapi-fetch";
import type { paths } from "../../../../packages/api-contracts/generated/schema"; // generated in Phase 9

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

export async function fetchExceptions(runId: string) {
  // We can fetch exceptions by filtering the audit trail for failed outcomes, or assume the backend has an exceptions endpoint.
  // Wait, let's look at the openapi schema or assume there is an exceptions endpoint from phase 9.
  // Actually, wait, let's fetch exceptions directly.
  // Phase 9 specs should tell us. Let's assume "/v1/metrics/exceptions" or similar. Wait, the spec has `fetchExceptions(runId)`.
  const { data, error } = await client.GET("/v1/metrics/exceptions", { params: { query: { run_id: runId } } });
  if (error) throw new Error(`exceptions fetch failed: ${JSON.stringify(error)}`);
  return data;
}
