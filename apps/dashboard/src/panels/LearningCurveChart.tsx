import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, CartesianGrid, ResponsiveContainer } from "recharts";
import { usePolling } from "../hooks/usePolling";
import { fetchLearningCurve } from "../api/client";
import { mergeCurvesByBatchIndex } from "../lib/mergeCurves";

function PanelSkeleton({ label }: { label: string }) {
  return <div className="skeleton" style={{ padding: '2rem' }}>{label}</div>;
}

function PanelError({ message }: { message: string }) {
  return <div className="panel-error">{message}</div>;
}

export function LearningCurveChart({ banditRunId, baselineRunId, compact = false }: { banditRunId: string; baselineRunId: string; compact?: boolean }) {
  const bandit = usePolling(["learning-curve", banditRunId], () => fetchLearningCurve(banditRunId));
  const baseline = usePolling(["learning-curve", baselineRunId], () => fetchLearningCurve(baselineRunId));

  if (bandit.isLoading || baseline.isLoading) return <PanelSkeleton label="Loading learning curve…" />;
  if (bandit.isError || baseline.isError) return <PanelError message="Could not load learning curve." />;

  const merged = mergeCurvesByBatchIndex(bandit.data! as any, baseline.data! as any);

  return (
    <div className={`learning-curve-chart${compact ? " learning-curve-compact" : ""}`} style={{ width: '100%', height: compact ? 80 : 300 }}>
      <ResponsiveContainer>
        <LineChart data={merged} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
          {!compact && <XAxis dataKey="batchIndex" stroke="rgba(255,255,255,0.5)" label={{ value: "Events processed", position: "insideBottom", offset: -5, fill: "rgba(255,255,255,0.5)" }} />}
          {!compact && <YAxis domain={[0, 1]} stroke="rgba(255,255,255,0.5)" tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />}
          <Tooltip 
            formatter={(v) => `${(Number(v ?? 0) * 100).toFixed(1)}%`}
            contentStyle={{ backgroundColor: 'rgba(15, 23, 42, 0.9)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: '#fff' }}
            itemStyle={{ color: '#fff' }}
          />
          {!compact && <Legend verticalAlign="top" height={36} wrapperStyle={{ color: 'rgba(255,255,255,0.8)' }} />}
          <Line type="monotone" dataKey="banditRate" name="Agent (learning)" stroke="#6366f1" strokeWidth={3} dot={false} activeDot={{ r: 6, fill: '#6366f1', stroke: '#fff' }} />
          <Line type="monotone" dataKey="baselineRate" name="Baseline (naive)" stroke="#94a3b8" strokeWidth={2} strokeDasharray="4 4" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
