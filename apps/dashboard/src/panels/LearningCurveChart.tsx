import React from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, CartesianGrid, ResponsiveContainer } from "recharts";
import { usePolling } from "../hooks/usePolling";
import { fetchLearningCurve } from "../api/client";
import { mergeCurvesByBatchIndex } from "../lib/mergeCurves";

function PanelSkeleton({ label }: { label: string }) {
  return <div className="panel-skeleton">{label}</div>;
}

function PanelError({ message }: { message: string }) {
  return <div className="panel-error">{message}</div>;
}

export function LearningCurveChart({ banditRunId, baselineRunId }: { banditRunId: string; baselineRunId: string }) {
  const bandit = usePolling(["learning-curve", banditRunId], () => fetchLearningCurve(banditRunId));
  const baseline = usePolling(["learning-curve", baselineRunId], () => fetchLearningCurve(baselineRunId));

  if (bandit.isLoading || baseline.isLoading) return <PanelSkeleton label="Loading learning curve…" />;
  if (bandit.isError || baseline.isError) return <PanelError message="Could not load learning curve." />;

  const merged = mergeCurvesByBatchIndex(bandit.data!, baseline.data!);

  return (
    <div className="learning-curve-chart" style={{ width: '100%', height: 300 }}>
      <ResponsiveContainer>
        <LineChart data={merged} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="batchIndex" label={{ value: "Batch index", position: "insideBottom", offset: -5 }} />
          <YAxis domain={[0, 1]} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
          <Tooltip formatter={(v: number) => `${(v * 100).toFixed(1)}%`} />
          <Legend verticalAlign="top" height={36}/>
          <Line type="monotone" dataKey="banditRate" name="Agent (learning)" stroke="#2563eb" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="baselineRate" name="Baseline (naive)" stroke="#9ca3af" strokeWidth={2} strokeDasharray="4 4" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
