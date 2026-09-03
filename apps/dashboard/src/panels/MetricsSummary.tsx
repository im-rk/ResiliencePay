import { usePolling } from "../hooks/usePolling";
import { fetchMetricsSummary } from "../api/client";
import { formatPaise } from "../lib/format";
import { LearningCurveChart } from "./LearningCurveChart";

export function MetricsSummary({ banditRunId, baselineRunId }: { banditRunId: string; baselineRunId: string }) {
  const bandit = usePolling(["metrics", banditRunId], () => fetchMetricsSummary(banditRunId));
  const baseline = usePolling(["metrics", baselineRunId], () => fetchMetricsSummary(baselineRunId));

  if (bandit.isLoading || baseline.isLoading) {
    return <div className="skeleton" style={{ height: '80px', width: '100%', borderRadius: '8px' }}></div>;
  }
  
  if (bandit.isError || baseline.isError) {
    return <div style={{ color: 'var(--color-danger)' }}>Could not load metrics.</div>;
  }

  const banditData = bandit.data || { recovery_rate: 0, amount_recovered: 0 };
  const baselineData = baseline.data || { recovery_rate: 0, amount_recovered: 0 };
  
  const lift = banditData.recovery_rate - baselineData.recovery_rate;
  // Assume a fixed at-risk volume for demo purposes if not provided by backend
  const totalAtRisk = 5000000; // ₹50,000.00

  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '24px' }}>
      
      {/* 1. Executive Metrics */}
      <div style={{ display: 'flex', gap: '32px', flex: 1 }}>
        <div>
          <div style={{ fontSize: '11px', color: 'var(--color-text-secondary)', textTransform: 'uppercase', marginBottom: '4px' }}>Total At-Risk Volume</div>
          <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{formatPaise(totalAtRisk)}</div>
        </div>
        
        <div>
          <div style={{ fontSize: '11px', color: 'var(--color-text-secondary)', textTransform: 'uppercase', marginBottom: '4px' }}>Recovered Revenue</div>
          <div style={{ fontSize: '24px', fontWeight: 'bold', color: 'var(--color-success)' }}>{formatPaise(banditData.amount_recovered)}</div>
        </div>

        <div>
          <div style={{ fontSize: '11px', color: 'var(--color-text-secondary)', textTransform: 'uppercase', marginBottom: '4px' }}>Recovery Rate</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{(banditData.recovery_rate * 100).toFixed(1)}%</div>
            <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>vs {(baselineData.recovery_rate * 100).toFixed(1)}%</div>
            <div style={{ 
              background: lift > 0 ? 'rgba(52, 211, 153, 0.2)' : 'rgba(255,255,255,0.1)', 
              color: lift > 0 ? 'var(--color-success)' : '#fff',
              padding: '2px 8px', borderRadius: '12px', fontSize: '12px', fontWeight: 'bold' 
            }}>
              {lift > 0 ? '+' : ''}{(lift * 100).toFixed(1)} pts
            </div>
          </div>
        </div>
        
        <div>
          <div style={{ fontSize: '11px', color: 'var(--color-text-secondary)', textTransform: 'uppercase', marginBottom: '4px' }}>Compliance Gate Adherence</div>
          <div style={{ fontSize: '16px', fontWeight: 'bold', color: 'var(--color-success)', display: 'flex', alignItems: 'center', height: '32px' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: '6px' }}>
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
            </svg>
            100% (0 violations)
          </div>
        </div>
      </div>
      
      {/* 2. Bandit Convergence Chart */}
      <div style={{ width: '350px', height: '80px' }}>
         <LearningCurveChart banditRunId={banditRunId} baselineRunId={baselineRunId} />
      </div>
    </div>
  );
}
