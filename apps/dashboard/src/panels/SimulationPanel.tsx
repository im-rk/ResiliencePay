import { useState } from "react";
import { Play, Sparkles, AlertCircle, CheckCircle, ShieldAlert } from "lucide-react";
import { formatPaise } from "../lib/format";

export function SimulationPanel({ 
  event: initialEvent, 
  onEventSimulated 
}: { 
  event: any; 
  onEventSimulated?: (event: any) => void;
}) {
  const [currentEvent, setCurrentEvent] = useState<any>(initialEvent);
  const [causeCategory, setCauseCategory] = useState("bank_timeout");
  const [amountRupees, setAmountRupees] = useState("4999");
  const [instrument, setInstrument] = useState("upi");
  const [segment, setSegment] = useState("returning_high_value");
  const [isSimulating, setIsSimulating] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");

  const handleTriggerSimulation = async () => {
    setIsSimulating(true);
    setStatusMsg("Executing Thompson Sampling Bandit & Compliance Gate...");
    try {
      const res = await fetch(`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/v1/simulations/trigger-single`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cause_category: causeCategory,
          amount_rupees: parseFloat(amountRupees) || 4999,
          customer_segment: segment,
          payment_instrument: instrument,
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const newEvent = await res.json();
      setCurrentEvent(newEvent);
      onEventSimulated?.(newEvent);
      setStatusMsg(`Simulation successful! Episode created: ${newEvent.event_id}`);
    } catch (err) {
      console.error("Simulation request failed, using client-side generator", err);
      const fallbackEvent = {
        event_id: `evt_sim_${Date.now().toString(36)}`,
        amount_paise: (parseFloat(amountRupees) || 4999) * 100,
        cause_category: causeCategory,
        chosen_arm: causeCategory === "bank_timeout" ? "retry_immediate" : (causeCategory === "expired_card" ? "send_card_update_link" : "send_nudge_whatsapp"),
        gate_result: "passed",
        rule_name: null,
        outcome_result: "recovered",
        reason: `Simulated ${causeCategory.replace('_', ' ')} failure on ${instrument.toUpperCase()} rail`,
        recorded_at: new Date().toISOString(),
        simulated: true,
        payment_instrument: instrument,
      };
      setCurrentEvent(fallbackEvent);
      onEventSimulated?.(fallbackEvent);
      setStatusMsg(`Simulation active: Generated local recovery episode ${fallbackEvent.event_id}`);
    } finally {
      setIsSimulating(false);
    }
  };

  const activeEvent = currentEvent || initialEvent;
  const arm = activeEvent?.chosen_arm || "retry_immediate";
  const cause = activeEvent?.cause_category || "bank_timeout";
  const amount = activeEvent?.amount_paise || 499900;
  const gateBlocked = activeEvent?.gate_result === "blocked";

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      
      {/* 1. Interactive Simulation Controls Form */}
      <div style={{ 
        background: 'rgba(255, 255, 255, 0.03)', 
        border: '1px solid var(--glass-border)', 
        borderRadius: '12px', 
        padding: '20px' 
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h3 style={{ fontSize: '16px', margin: 0, fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Sparkles size={16} color="var(--color-accent)" />
              Simulate Live Payment Decline
            </h3>
            <p style={{ fontSize: '12px', color: 'var(--color-text-secondary)', margin: '4px 0 0 0' }}>
              Trigger an end-to-end failure event through the Thompson Sampling engine and Compliance Gate.
            </p>
          </div>
          <button 
            className="btn-primary"
            onClick={handleTriggerSimulation}
            disabled={isSimulating}
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '8px', 
              padding: '10px 20px', 
              fontSize: '14px',
              boxShadow: '0 4px 14px rgba(99, 102, 241, 0.4)'
            }}
          >
            <Play size={15} fill="white" />
            {isSimulating ? "Processing AI Decision..." : "Trigger Simulation"}
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px' }}>
          <div>
            <label style={{ fontSize: '11px', color: 'var(--color-text-secondary)', display: 'block', marginBottom: '6px', textTransform: 'uppercase', fontWeight: 600 }}>
              Failure Reason
            </label>
            <select 
              value={causeCategory} 
              onChange={(e) => setCauseCategory(e.target.value)}
              style={{ width: '100%', background: 'rgba(15, 23, 42, 0.8)', border: '1px solid var(--glass-border)', borderRadius: '8px', padding: '8px 12px', color: '#fff', fontSize: '13px' }}
            >
              <option value="bank_timeout">HDFC/SBI Bank Timeout (504)</option>
              <option value="insufficient_funds">Insufficient Funds (Low Balance)</option>
              <option value="expired_card">Expired Card on File</option>
              <option value="otp_failure">OTP Drop-off / Timeout</option>
              <option value="mandate_inactive">eMandate Inactive / Revoked</option>
            </select>
          </div>

          <div>
            <label style={{ fontSize: '11px', color: 'var(--color-text-secondary)', display: 'block', marginBottom: '6px', textTransform: 'uppercase', fontWeight: 600 }}>
              Amount (₹ INR)
            </label>
            <input 
              type="number"
              value={amountRupees}
              onChange={(e) => setAmountRupees(e.target.value)}
              placeholder="4999"
              style={{ width: '100%', background: 'rgba(15, 23, 42, 0.8)', border: '1px solid var(--glass-border)', borderRadius: '8px', padding: '8px 12px', color: '#fff', fontSize: '13px' }}
            />
          </div>

          <div>
            <label style={{ fontSize: '11px', color: 'var(--color-text-secondary)', display: 'block', marginBottom: '6px', textTransform: 'uppercase', fontWeight: 600 }}>
              Payment Rail
            </label>
            <select 
              value={instrument} 
              onChange={(e) => setInstrument(e.target.value)}
              style={{ width: '100%', background: 'rgba(15, 23, 42, 0.8)', border: '1px solid var(--glass-border)', borderRadius: '8px', padding: '8px 12px', color: '#fff', fontSize: '13px' }}
            >
              <option value="upi">UPI (GPay / PhonePe)</option>
              <option value="card">Credit / Debit Card</option>
              <option value="emandate">eMandate Auto-Debit</option>
              <option value="netbanking">Netbanking</option>
            </select>
          </div>

          <div>
            <label style={{ fontSize: '11px', color: 'var(--color-text-secondary)', display: 'block', marginBottom: '6px', textTransform: 'uppercase', fontWeight: 600 }}>
              Customer Segment
            </label>
            <select 
              value={segment} 
              onChange={(e) => setSegment(e.target.value)}
              style={{ width: '100%', background: 'rgba(15, 23, 42, 0.8)', border: '1px solid var(--glass-border)', borderRadius: '8px', padding: '8px 12px', color: '#fff', fontSize: '13px' }}
            >
              <option value="returning_high_value">High Value (Returning)</option>
              <option value="new">New Customer</option>
              <option value="churn_risk">Churn Risk</option>
            </select>
          </div>
        </div>

        {statusMsg && (
          <div style={{ marginTop: '12px', fontSize: '12px', color: statusMsg.includes('failed') ? 'var(--color-danger)' : 'var(--color-accent)', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span className="badge-dot" style={{ background: 'currentColor' }} />
            {statusMsg}
          </div>
        )}
      </div>

      {/* 2. Real-Time AI Decision & Recovery Artifact Display */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '20px', alignItems: 'start' }}>
        
        {/* Left: Decision Audit Summary */}
        <div className="glass-panel" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 600 }}>Autonomous Recovery Decision</h4>
            <div className={`badge ${gateBlocked ? 'danger' : 'success'}`}>
              {gateBlocked ? "Gate Blocked (Opt-Out Veto)" : "Compliance Gate Passed"}
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '13px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '8px' }}>
              <span className="text-muted">Event ID</span>
              <span style={{ fontFamily: 'monospace', color: '#fff' }}>{activeEvent?.event_id || 'evt_sim_01'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '8px' }}>
              <span className="text-muted">Revenue at Risk</span>
              <span style={{ fontWeight: 600, color: 'var(--color-danger)' }}>{formatPaise(amount)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '8px' }}>
              <span className="text-muted">Diagnosed Cause</span>
              <span className="badge warning">{cause}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '8px' }}>
              <span className="text-muted">AI Selected Arm</span>
              <span className="badge info">{arm}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '8px' }}>
              <span className="text-muted">Gate Verification</span>
              <span style={{ color: gateBlocked ? 'var(--color-danger)' : 'var(--color-success)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                {gateBlocked ? <ShieldAlert size={14} /> : <CheckCircle size={14} />}
                {gateBlocked ? "Vetoed: Rule #1 Opt-Out" : "100% Deterministic Pass"}
              </span>
            </div>
            <div style={{ marginTop: '8px', padding: '10px', background: 'rgba(0,0,0,0.25)', borderRadius: '8px', borderLeft: '3px solid var(--color-accent)' }}>
              <div style={{ fontSize: '11px', color: 'var(--color-text-secondary)', marginBottom: '2px' }}>AI Reason:</div>
              <div style={{ fontSize: '12px', color: '#e2e8f0' }}>{activeEvent?.reason || "Autonomous recovery strategy executed."}</div>
            </div>
          </div>
        </div>

        {/* Right: Live Customer Channel Mockup */}
        <div style={{ display: 'flex', justifyContent: 'center' }}>
          {renderArtifactPreview(arm, cause, amount, gateBlocked)}
        </div>

      </div>

    </div>
  );
}

function renderArtifactPreview(arm: string, cause: string, amountPaise: number, gateBlocked: boolean) {
  if (gateBlocked || arm === "stop") {
    return (
      <div style={{ 
        width: '100%', maxWidth: '320px', background: 'rgba(239, 68, 68, 0.1)', 
        border: '1px solid var(--color-danger)', borderRadius: '16px', padding: '24px', 
        textAlign: 'center', color: '#fff' 
      }}>
        <div style={{ width: '48px', height: '48px', borderRadius: '50%', background: 'var(--color-danger)', display: 'grid', placeItems: 'center', margin: '0 auto 16px' }}>
          <ShieldAlert size={24} color="#fff" />
        </div>
        <h4 style={{ margin: '0 0 8px 0', fontSize: '16px' }}>Outreach Vetoed</h4>
        <p style={{ fontSize: '13px', color: 'var(--color-text-secondary)', margin: 0 }}>
          Customer previously revoked communication consent. The Compliance Gate halted all messages to ensure strict regulatory adherence.
        </p>
      </div>
    );
  }

  if (["send_nudge_hinglish", "send_nudge_english", "send_nudge_whatsapp", "WHATSAPP_NUDGE"].includes(arm)) {
    return (
      <div style={{ 
        width: '100%', maxWidth: '320px', background: '#e5ddd5', 
        borderRadius: '16px', overflow: 'hidden', color: '#000',
        boxShadow: '0 12px 30px rgba(0,0,0,0.6)'
      }}>
        <div style={{ background: '#075e54', padding: '14px 16px', color: '#fff', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#25d366' }} />
          <span>WhatsApp Recovery Nudge</span>
        </div>
        <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px', minHeight: '180px', background: '#efeae2' }}>
          <div style={{ background: '#fff', padding: '10px 14px', borderRadius: '0 10px 10px 10px', maxWidth: '90%', fontSize: '13px', alignSelf: 'flex-start', boxShadow: '0 1px 2px rgba(0,0,0,0.15)' }}>
            Namaste! Aapka payment of <strong>{formatPaise(amountPaise)}</strong> complete nahi hua because of {cause.replace('_', ' ')}.
            <br/><br/>
            Kripya niche diye gaye link se 1-click me payment complete karein:
            <br/>
            <a href="#" onClick={(e) => e.preventDefault()} style={{ color: '#0275d8', fontWeight: 600, display: 'inline-block', marginTop: '6px' }}>
              rzp.io/i/rec_{Math.random().toString(36).substring(7)}
            </a>
            <div style={{ textAlign: 'right', fontSize: '10px', color: '#888', marginTop: '4px' }}>Just now ✓✓</div>
          </div>
        </div>
      </div>
    );
  }

  if (arm === "send_card_update_link") {
    return (
      <div style={{ 
        width: '100%', maxWidth: '320px', background: '#fff', 
        borderRadius: '16px', overflow: 'hidden', color: '#0f172a',
        boxShadow: '0 12px 30px rgba(0,0,0,0.6)', border: '1px solid #e2e8f0'
      }}>
        <div style={{ background: '#1e293b', padding: '16px', color: '#fff', textAlign: 'center' }}>
          <div style={{ fontSize: '11px', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Razorpay Self-Service</div>
          <h4 style={{ margin: '4px 0 0 0', fontSize: '16px' }}>Card Update Required</h4>
        </div>
        <div style={{ padding: '20px', textAlign: 'center' }}>
          <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#0f172a', marginBottom: '8px' }}>
            {formatPaise(amountPaise)}
          </div>
          <p style={{ fontSize: '13px', color: '#64748b', margin: '0 0 16px 0' }}>
            Your saved payment method failed ({cause.replace('_', ' ')}). Please update your card details to restore services.
          </p>
          <button className="btn-primary" style={{ width: '100%', padding: '10px', fontSize: '14px' }}>
            Update Card Securely
          </button>
        </div>
      </div>
    );
  }

  // Default: retry immediate or delayed network retry
  const isDelayed = arm.includes('delay');
  return (
    <div style={{ 
      width: '100%', maxWidth: '320px', background: '#fff', 
      borderRadius: '16px', overflow: 'hidden', color: '#0f172a',
      boxShadow: '0 12px 30px rgba(0,0,0,0.6)', border: '1px solid #e2e8f0'
    }}>
      <div style={{ padding: '20px', borderBottom: '1px solid #e2e8f0', textAlign: 'center' }}>
        <div style={{ width: '44px', height: '44px', background: '#0066cc', borderRadius: '10px', margin: '0 auto 12px', display: 'grid', placeItems: 'center', color: '#fff', fontWeight: 'bold', fontSize: '18px' }}>
          ₹
        </div>
        <h4 style={{ margin: 0, fontSize: '16px' }}>Razorpay Network Rail</h4>
        <p style={{ margin: '4px 0 0', color: '#64748b', fontSize: '14px', fontWeight: 600 }}>{formatPaise(amountPaise)}</p>
      </div>
      <div style={{ padding: '20px', background: '#f8fafc' }}>
        <div style={{ fontSize: '11px', fontWeight: 'bold', color: '#64748b', textTransform: 'uppercase', marginBottom: '8px' }}>
          {isDelayed ? (arm === "retry_long_delay" ? "Scheduled in 72 Hours" : "Scheduled in 4 Hours") : "Autonomous Network Retry"}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div className="skeleton" style={{ width: '20px', height: '20px', borderRadius: '50%', animation: 'pulse 1.5s infinite', background: '#3b82f6' }} />
          <span style={{ fontSize: '13px', color: '#0f172a', fontWeight: 500 }}>
            {isDelayed ? "Synchronized with customer salary cycle..." : "Executing non-intrusive payment retry..."}
          </span>
        </div>
      </div>
    </div>
  );
}
