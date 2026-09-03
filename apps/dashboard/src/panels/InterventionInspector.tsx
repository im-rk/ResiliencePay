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
      
      {/* 1. Header with Circular Score */}
      <div style={{ display: 'flex', gap: '20px', alignItems: 'center', background: 'linear-gradient(135deg, rgba(15,23,42,0.6), rgba(30,41,59,0.8))', padding: '24px', borderRadius: '16px', border: '1px solid var(--glass-border)' }}>
        <div style={{ position: 'relative', width: '80px', height: '80px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
           <svg style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' }} viewBox="0 0 36 36">
             <path
               className="progress-ring__circle"
               stroke="var(--glass-border)"
               strokeWidth="3"
               fill="none"
               d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
             />
             <path
               className="progress-ring__circle"
               stroke="var(--color-accent)"
               strokeWidth="3"
               strokeDasharray="100, 100"
               strokeDashoffset={arms.length > 0 ? 100 - (arms[0].prob * 100) : 0}
               fill="none"
               d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
               style={{ filter: 'drop-shadow(0 0 4px var(--color-accent-glow))' }}
             />
           </svg>
           <div style={{ position: 'relative', textAlign: 'center', display: 'flex', flexDirection: 'column' }}>
             <span style={{ fontSize: '18px', fontWeight: 700, fontFamily: 'var(--font-display)', color: '#fff' }}>
               {arms.length > 0 ? (arms[0].prob * 100).toFixed(0) : "0"}%
             </span>
           </div>
        </div>
        
        <div style={{ flex: 1 }}>
          <h3 style={{ fontSize: '12px', color: 'var(--color-text-secondary)', textTransform: 'uppercase', marginBottom: '4px', letterSpacing: '0.05em' }}>AI Recommendation</h3>
          <div style={{ fontSize: '20px', fontWeight: 600, color: 'var(--color-accent)', marginBottom: '8px' }}>
            {event.chosen_arm || "WAIT_AND_OBSERVE"}
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <div className={event.gate_result === 'passed' ? "badge success" : "badge danger"} style={{ padding: '2px 8px', fontSize: '10px' }}>
              <span className="badge-dot" /> {event.gate_result === 'passed' ? "GATE PASSED" : "GATE BLOCKED"}
            </div>
            {event.gate_result === 'passed' && (
              <span style={{ fontSize: '11px', color: 'var(--color-text-secondary)' }}>Approved for execution</span>
            )}
          </div>
        </div>
      </div>

      {/* 2. Context Features */}
      <div>
        <h3 style={{ fontSize: '14px', marginBottom: '12px', color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Diagnosis Context</h3>
        <div className="glass-panel" style={{ padding: '0', overflow: 'hidden' }}>
          <table style={{ margin: 0 }}>
            <tbody>
              <tr><td style={{ color: 'var(--color-text-secondary)', width: '40%' }}>Event ID</td><td style={{ color: '#fff', fontWeight: 500 }}>{event.event_id}</td></tr>
              <tr><td style={{ color: 'var(--color-text-secondary)' }}>Amount</td><td style={{ color: '#fff', fontWeight: 500 }}>₹{(event.amount_paise ? event.amount_paise / 100 : 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}</td></tr>
              <tr><td style={{ color: 'var(--color-text-secondary)' }}>Decline Reason</td><td style={{ color: 'var(--color-warning)', fontWeight: 500 }}>{event.cause_category || "UNKNOWN"}</td></tr>
              <tr><td style={{ color: 'var(--color-text-secondary)' }}>Customer Profile</td><td style={{ color: '#fff', fontWeight: 500 }}>High Value (Tier 1)</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* 3. Bandit Probability Distribution */}
      <div>
        <h3 style={{ fontSize: '14px', marginBottom: '12px', color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Thompson Sampling Distribution</h3>
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '16px', padding: '20px' }}>
          {arms.map((arm) => (
            <div key={arm.name}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '8px' }}>
                <span style={{ fontWeight: arm.name === event.chosen_arm ? 600 : 400, color: arm.name === event.chosen_arm ? '#fff' : 'var(--color-text-secondary)' }}>
                  {arm.name}
                </span>
                <span style={{ color: arm.name === event.chosen_arm ? 'var(--color-accent)' : 'inherit', fontWeight: 600 }}>
                  {(arm.prob * 100).toFixed(1)}%
                </span>
              </div>
              <div style={{ width: '100%', height: '8px', background: 'rgba(255,255,255,0.05)', borderRadius: '4px', overflow: 'hidden' }}>
                <div style={{ 
                  height: '100%', 
                  width: `${arm.prob * 100}%`, 
                  background: arm.name === event.chosen_arm ? 'var(--color-accent)' : 'var(--color-text-muted)',
                  boxShadow: arm.name === event.chosen_arm ? '0 0 10px var(--color-accent-glow)' : 'none',
                  borderRadius: '4px',
                  transition: 'width 0.5s ease-out'
                }} />
              </div>
            </div>
          ))}
          {arms.length === 0 && (
             <div style={{ fontSize: '12px', color: 'var(--color-text-muted)', textAlign: 'center' }}>Loading live distribution stats...</div>
          )}
        </div>
      </div>
      
    </div>
  );
}
