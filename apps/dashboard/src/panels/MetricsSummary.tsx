import React from "react";
import { usePolling } from "../hooks/usePolling";
import { fetchMetricsSummary } from "../api/client";
import { formatPaise } from "../lib/format";

function MetricsSkeleton() {
  return <div className="panel-skeleton">Loading metrics…</div>;
}

function PanelError({ message }: { message: string }) {
  return <div className="panel-error">{message}</div>;
}

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
