import { useEffect, useState } from "react";

interface BanditStat {
  name: string;
  alpha: number;
  beta: number;
  prob: number;
}

export function InterventionInspector({ event }: { event: any }) {
  const [arms, setArms] = useState<BanditStat[]>([]);

  useEffect(() => {
    if (event && event.cause_category) {
      const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
      fetch(`${apiBaseUrl}/v1/simulations/bandit-stats?cause_category=${encodeURIComponent(event.cause_category)}`)
        .then(res => res.json())
        .then(data => {
          if (data && data.arms) {
            const sortedArms = data.arms.sort((a: BanditStat, b: BanditStat) => b.prob - a.prob);
            setArms(sortedArms);
          }
        })
        .catch(err => console.error("Failed to load bandit stats", err));
    }
  }, [event]);

  if (!event) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--color-text-secondary)' }}>
        Select an event from the feed to inspect the agent's decision logic.
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      
      {/* Overview */}
      <div style={{ background: 'rgba(0,0,0,0.2)', padding: '16px', borderRadius: '8px', border: '1px solid var(--glass-border)' }}>
        <h3 style={{ fontSize: '12px', color: 'var(--color-text-secondary)', textTransform: 'uppercase', marginBottom: '8px' }}>Bandit Arm Chosen</h3>
        <div style={{ fontSize: '18px', fontWeight: 600, color: 'var(--color-accent)' }}>
          {event.chosen_arm || "NO_ACTION_TAKEN"}
        </div>
        <div style={{ fontSize: '12px', marginTop: '8px' }}>
          Gate Verdict: <span className={event.gate_result === 'passed' ? "text-success" : "text-danger"}>{event.gate_result ? event.gate_result.toUpperCase() : "N/A"}</span>
        </div>
      </div>

      {/* Context Features Evaluated */}
      <div>
        <h3 style={{ fontSize: '14px', marginBottom: '12px' }}>Context Features Evaluated</h3>
        <table style={{ borderCollapse: 'collapse', width: '100%' }}>
          <tbody>
            <tr><td style={{ padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.1)', color: 'var(--color-text-secondary)' }}>Ticket Size Tier</td><td style={{ textAlign: 'right', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>High (\u20B95,000+)</td></tr>
            <tr><td style={{ padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.1)', color: 'var(--color-text-secondary)' }}>Decline Reason</td><td style={{ textAlign: 'right', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>{event.cause_category || "UNKNOWN"}</td></tr>
            <tr><td style={{ padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.1)', color: 'var(--color-text-secondary)' }}>Time of Failure</td><td style={{ textAlign: 'right', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>{new Date().toLocaleTimeString()}</td></tr>
            <tr><td style={{ padding: '8px 0', color: 'var(--color-text-secondary)' }}>Customer Retry History</td><td style={{ textAlign: 'right' }}>Good (0 previous bounces)</td></tr>
          </tbody>
        </table>
      </div>

      {/* Probability Distribution */}
      <div>
        <h3 style={{ fontSize: '14px', marginBottom: '12px' }}>Thompson Sampling Distribution (alpha/beta)</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {arms.map((arm) => (
            <div key={arm.name}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
                <span>{arm.name}</span>
                <span>{(arm.prob * 100).toFixed(1)}%</span>
              </div>
              <div style={{ width: '100%', height: '6px', background: 'rgba(255,255,255,0.1)', borderRadius: '3px', overflow: 'hidden' }}>
                <div style={{ 
                  height: '100%', 
                  width: `${arm.prob * 100}%`, 
                  background: arm.name === event.chosen_arm ? 'var(--color-accent)' : '#94a3b8' 
                }} />
              </div>
            </div>
          ))}
        </div>
      </div>
      
    </div>
  );
}
