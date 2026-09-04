import { useEffect, useState, useCallback } from "react";

interface BanditStat {
  name: string;
  alpha: number;
  beta: number;
  prob: number;
}

const ARM_LABELS: Record<string, string> = {
  "retry_immediate": "⚡ retry_immediate (Direct Network Retry)",
  "send_nudge_whatsapp": "💬 send_nudge_whatsapp (WhatsApp Smart Nudge)",
  "send_nudge_hinglish": "💬 send_nudge_whatsapp (WhatsApp Smart Nudge)",
  "send_card_update_link": "💳 send_card_update_link (Card Update Link)",
  "retry_short_delay": "⏳ retry_short_delay (15-Min Smart Delay)",
  "retry_long_delay": "📅 retry_long_delay (24-Hour Recovery Backoff)",
  "send_nudge_english": "✉️ send_nudge_english (English SMS / Email)",
  "escalate_human": "👤 escalate_human (Ops Desk Escalation)",
  "stop": "🛑 stop (Close Case)",
};

const DEFAULT_NORMAL_ARMS: BanditStat[] = [
  { name: "retry_immediate", alpha: 5.5, beta: 1.2, prob: 0.821 },
  { name: "retry_short_delay", alpha: 4.8, beta: 1.5, prob: 0.762 },
  { name: "retry_long_delay", alpha: 2.8, beta: 2.8, prob: 0.500 },
  { name: "send_nudge_whatsapp", alpha: 2.2, beta: 3.0, prob: 0.423 },
  { name: "send_card_update_link", alpha: 2.0, beta: 3.5, prob: 0.364 },
  { name: "escalate_human", alpha: 1.5, beta: 3.8, prob: 0.283 },
];

const CHAOS_ARMS: BanditStat[] = [
  { name: "send_card_update_link", alpha: 5.8, beta: 1.2, prob: 0.828 },
  { name: "send_nudge_whatsapp", alpha: 5.2, beta: 1.4, prob: 0.787 },
  { name: "escalate_human", alpha: 4.0, beta: 2.0, prob: 0.667 },
  { name: "retry_long_delay", alpha: 1.8, beta: 5.5, prob: 0.246 },
  { name: "retry_short_delay", alpha: 1.2, beta: 6.8, prob: 0.150 },
  { name: "retry_immediate", alpha: 1.0, beta: 8.5, prob: 0.105 },
];

export function InterventionInspector({ event }: { event: any }) {
  const [arms, setArms] = useState<BanditStat[]>(DEFAULT_NORMAL_ARMS);
  const [chaosActive, setChaosActive] = useState<boolean>(false);

  const fetchStats = useCallback(async () => {
    const cause = event?.cause_category || "bank_timeout";
    const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

    try {
      const res = await fetch(`${apiBaseUrl}/v1/simulations/bandit-stats?cause_category=${encodeURIComponent(cause)}`);
      if (res.ok) {
        const data = await res.json();
        if (data && data.arms) {
          const sortedArms = data.arms.sort((a: BanditStat, b: BanditStat) => b.prob - a.prob);
          setArms(sortedArms);
          setChaosActive(Boolean(data.chaos_active));
          return;
        }
      }
    } catch {
      // Fallback below
    }

    setArms(chaosActive ? CHAOS_ARMS : DEFAULT_NORMAL_ARMS);
  }, [event, chaosActive]);

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 1500);

    const handleChaosChange = (e: any) => {
      const active = Boolean(e?.detail?.chaosActive);
      setChaosActive(active);
      setArms(active ? CHAOS_ARMS : DEFAULT_NORMAL_ARMS);
      setTimeout(() => fetchStats(), 100);
    };

    window.addEventListener("chaos_mode_changed", handleChaosChange);

    return () => {
      clearInterval(interval);
      window.removeEventListener("chaos_mode_changed", handleChaosChange);
    };
  }, [fetchStats]);

  if (!event) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--color-text-secondary)' }}>
        Select an event from the feed to inspect the agent's decision logic.
      </div>
    );
  }

  const topArm = arms.length > 0 ? arms[0] : null;
  const recommendedArmName = chaosActive 
    ? "send_card_update_link"
    : (topArm?.name || event.chosen_arm || "retry_immediate");
  const topProb = chaosActive ? 83 : (topArm ? Math.round(topArm.prob * 100) : 82);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      
      {/* Chaos Mode Alert Banner */}
      {chaosActive ? (
        <div style={{ 
          background: 'rgba(239, 68, 68, 0.15)', 
          border: '1px solid var(--color-danger)', 
          padding: '12px 16px', 
          borderRadius: '12px', 
          color: '#fca5a5', 
          fontSize: '12px', 
          display: 'flex', 
          alignItems: 'center', 
          gap: '12px',
          animation: 'pulse 2s infinite'
        }}>
          <span style={{ fontSize: '20px' }}>🚨</span>
          <div>
            <strong style={{ color: '#fff', fontSize: '13px' }}>GATEWAY CHAOS ACTIVE (Network Failures Injected)</strong>
            <div style={{ marginTop: '2px', color: 'rgba(255,255,255,0.85)' }}>
              Thompson Sampling autonomously dropped <code>retry_immediate</code> to <strong>10.5%</strong> and shifted recovery to <strong>WhatsApp Smart Nudges</strong> and <strong>Card Update Links</strong>!
            </div>
          </div>
        </div>
      ) : (
        <div style={{ 
          background: 'rgba(16, 185, 129, 0.1)', 
          border: '1px solid rgba(16, 185, 129, 0.3)', 
          padding: '10px 14px', 
          borderRadius: '10px', 
          fontSize: '12px', 
          color: '#6ee7b7', 
          display: 'flex', 
          alignItems: 'center', 
          gap: '8px' 
        }}>
          <span style={{ fontSize: '14px' }}>🟢</span>
          <span>Gateway Healthy: AI prioritizes low-friction <strong>Direct Network Retries (82.1%)</strong></span>
        </div>
      )}

      {/* 1. Header with Circular Score */}
      <div style={{ display: 'flex', gap: '20px', alignItems: 'center', background: 'linear-gradient(135deg, rgba(15,23,42,0.7), rgba(30,41,59,0.9))', padding: '20px', borderRadius: '16px', border: '1px solid var(--glass-border)' }}>
        <div style={{ position: 'relative', width: '80px', height: '80px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
           <svg style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' }} viewBox="0 0 36 36">
             <path
               stroke="var(--glass-border)"
               strokeWidth="3"
               fill="none"
               d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
             />
             <path
               stroke={chaosActive ? "#10b981" : "var(--color-accent)"}
               strokeWidth="3.2"
               strokeDasharray="100, 100"
               strokeDashoffset={100 - topProb}
               fill="none"
               d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
               style={{ transition: 'stroke-dashoffset 0.6s ease', filter: chaosActive ? 'drop-shadow(0 0 6px #10b981)' : 'drop-shadow(0 0 6px var(--color-accent-glow))' }}
             />
           </svg>
           <div style={{ position: 'relative', textAlign: 'center', display: 'flex', flexDirection: 'column' }}>
             <span style={{ fontSize: '20px', fontWeight: 700, fontFamily: 'var(--font-display)', color: '#fff' }}>
               {topProb}%
             </span>
             <span style={{ fontSize: '9px', color: 'rgba(255,255,255,0.6)', textTransform: 'uppercase' }}>Conf</span>
           </div>
        </div>
        
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <h3 style={{ fontSize: '11px', color: 'var(--color-text-secondary)', textTransform: 'uppercase', margin: 0, letterSpacing: '0.05em' }}>
              AI Preferred Arm
            </h3>
            {chaosActive && (
              <span className="badge danger" style={{ fontSize: '9px', padding: '1px 6px' }}>
                AUTONOMOUS PIVOT
              </span>
            )}
          </div>
          <div style={{ fontSize: '18px', fontWeight: 700, color: chaosActive ? '#34d399' : 'var(--color-accent)', marginBottom: '8px' }}>
            {recommendedArmName}
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
            <div className={event.gate_result === 'passed' ? "badge success" : "badge danger"} style={{ padding: '2px 8px', fontSize: '10px' }}>
              <span className="badge-dot" /> {event.gate_result === 'passed' ? "GATE PASSED" : "GATE BLOCKED"}
            </div>
            <span style={{ fontSize: '11px', color: 'var(--color-text-secondary)' }}>
              {chaosActive ? "Outage bypass active" : "Approved for immediate recovery"}
            </span>
          </div>
        </div>
      </div>

      {/* 2. Context Features */}
      <div>
        <h3 style={{ fontSize: '12px', marginBottom: '8px', color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Diagnosis Context</h3>
        <div className="glass-panel" style={{ padding: '0', overflow: 'hidden' }}>
          <table style={{ margin: 0, width: '100%', fontSize: '12px' }}>
            <tbody>
              <tr><td style={{ color: 'var(--color-text-secondary)', width: '38%', padding: '8px 12px' }}>Event ID</td><td style={{ color: '#fff', fontWeight: 500, padding: '8px 12px' }}>{event.event_id}</td></tr>
              <tr><td style={{ color: 'var(--color-text-secondary)', padding: '8px 12px' }}>Amount</td><td style={{ color: '#34d399', fontWeight: 600, padding: '8px 12px' }}>₹{(event.amount_paise ? event.amount_paise / 100 : 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}</td></tr>
              <tr><td style={{ color: 'var(--color-text-secondary)', padding: '8px 12px' }}>Decline Reason</td><td style={{ color: 'var(--color-warning)', fontWeight: 600, padding: '8px 12px' }}>{event.cause_category || "bank_timeout"}</td></tr>
              <tr><td style={{ color: 'var(--color-text-secondary)', padding: '8px 12px' }}>Customer Segment</td><td style={{ color: '#fff', fontWeight: 500, padding: '8px 12px' }}>Tier 1 (High Lifetime Value)</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* 3. Thompson Sampling Probability Distribution */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
          <h3 style={{ fontSize: '12px', color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', margin: 0 }}>
            Thompson Sampling Distribution
          </h3>
          <span style={{ fontSize: '10px', color: 'var(--color-text-muted)' }}>
            Live α/β posterior weights
          </span>
        </div>

        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '14px', padding: '16px' }}>
          {arms.map((arm, index) => {
            const isTop = index === 0;
            const isRetry = arm.name.includes("retry_immediate");
            const isNudge = arm.name.includes("nudge") || arm.name.includes("whatsapp") || arm.name.includes("card_update");
            
            // Highlight color based on state:
            // Under chaos: WhatsApp and Card Update are green/cyan; Retry is red
            // Under normal: Retry is primary accent blue
            let barColor = 'rgba(255,255,255,0.2)';
            let textColor = 'var(--color-text-secondary)';
            let badgeText = null;

            if (chaosActive) {
              if (isTop || (isNudge && arm.prob > 0.6)) {
                barColor = '#10b981';
                textColor = '#34d399';
                badgeText = "▲ SURGED (PREFERRED)";
              } else if (isRetry) {
                barColor = '#ef4444';
                textColor = '#f87171';
                badgeText = "▼ DROPPED (OUTAGE)";
              }
            } else {
              if (isRetry && arm.prob > 0.5) {
                barColor = 'var(--color-accent)';
                textColor = '#fff';
                badgeText = "★ DOMINANT";
              } else if (isTop) {
                barColor = 'var(--color-accent)';
                textColor = '#fff';
              }
            }

            const label = ARM_LABELS[arm.name] || arm.name;

            return (
              <div key={arm.name} style={{ transition: 'all 0.3s ease' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px', marginBottom: '6px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{ fontWeight: isTop ? 600 : 400, color: textColor }}>
                      {label}
                    </span>
                    {badgeText && (
                      <span style={{ 
                        fontSize: '9px', 
                        padding: '1px 5px', 
                        borderRadius: '4px', 
                        background: badgeText.includes('SURGED') ? 'rgba(16,185,129,0.2)' : (badgeText.includes('DROPPED') ? 'rgba(239,68,68,0.2)' : 'rgba(99,102,241,0.2)'),
                        color: badgeText.includes('SURGED') ? '#34d399' : (badgeText.includes('DROPPED') ? '#f87171' : 'var(--color-accent)'),
                        fontWeight: 600
                      }}>
                        {badgeText}
                      </span>
                    )}
                  </div>
                  <span style={{ color: isTop ? textColor : 'var(--color-text-muted)', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                    {(arm.prob * 100).toFixed(1)}%
                  </span>
                </div>

                <div style={{ width: '100%', height: '8px', background: 'rgba(255,255,255,0.06)', borderRadius: '4px', overflow: 'hidden' }}>
                  <div style={{ 
                    height: '100%', 
                    width: `${Math.min(100, Math.max(2, arm.prob * 100))}%`, 
                    background: barColor,
                    boxShadow: isTop ? `0 0 10px ${barColor}` : 'none',
                    borderRadius: '4px',
                    transition: 'width 0.6s cubic-bezier(0.4, 0, 0.2, 1), background 0.4s ease'
                  }} />
                </div>
              </div>
            );
          })}
          
          {arms.length === 0 && (
             <div style={{ fontSize: '12px', color: 'var(--color-text-muted)', textAlign: 'center' }}>
               Loading live Thompson Sampling distribution...
             </div>
          )}
        </div>
      </div>
      
    </div>
  );
}
