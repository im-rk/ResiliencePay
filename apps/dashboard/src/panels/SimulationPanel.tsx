import React from "react";

export function SimulationPanel({ event }: { event: any }) {
  if (!event) {
    return (
      <div style={{ color: 'var(--color-text-secondary)', textAlign: 'center' }}>
        <p>Waiting for intervention...</p>
      </div>
    );
  }

  // Render different simulators based on the arm
  if (event.chosen_arm === "WHATSAPP_NUDGE" || event.chosen_arm === "SMS_NUDGE") {
    return (
      <div style={{ 
        width: '100%', maxWidth: '300px', background: '#e5ddd5', 
        borderRadius: '16px', overflow: 'hidden', color: '#000',
        boxShadow: '0 10px 25px rgba(0,0,0,0.5)'
      }}>
        <div style={{ background: '#075e54', padding: '16px', color: '#fff', fontWeight: 'bold' }}>
          WhatsApp Simulator
        </div>
        <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px', background: 'url("https://user-images.githubusercontent.com/15075759/28719144-86dc0f70-73b1-11e7-911d-60d70fcded21.png")' }}>
          <div style={{ background: '#fff', padding: '8px 12px', borderRadius: '0 8px 8px 8px', maxWidth: '85%', fontSize: '14px', alignSelf: 'flex-start' }}>
            Hi! This is ResiliencePay. Your recent payment of ₹5,000 failed due to {event.cause_category}. 
            <br/><br/>
            No worries! You can complete it using the link below:
            <br/>
            <a href="#" style={{ color: '#0275d8' }}>rzp.io/i/recovery</a>
          </div>
        </div>
      </div>
    );
  }

  if (event.chosen_arm === "DEFER_RETRY" || event.chosen_arm === "SILENT_RETRY") {
    return (
      <div style={{ 
        width: '100%', maxWidth: '300px', background: '#fff', 
        borderRadius: '12px', overflow: 'hidden', color: '#000',
        boxShadow: '0 10px 25px rgba(0,0,0,0.5)',
        border: '1px solid #e2e8f0'
      }}>
        <div style={{ padding: '20px', borderBottom: '1px solid #e2e8f0', textAlign: 'center' }}>
          <div style={{ width: '48px', height: '48px', background: '#0066cc', borderRadius: '8px', margin: '0 auto 16px' }}></div>
          <h4 style={{ margin: 0, fontSize: '18px' }}>Test Merchant</h4>
          <p style={{ margin: '4px 0 0', color: '#64748b', fontSize: '14px' }}>₹5,000.00</p>
        </div>
        <div style={{ padding: '20px', background: '#f8fafc', display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ fontSize: '12px', fontWeight: 'bold', color: '#64748b', textTransform: 'uppercase' }}>
            {event.chosen_arm === "DEFER_RETRY" ? "Retrying later" : "Retrying silently..."}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
             <div className="skeleton" style={{ width: '24px', height: '24px', borderRadius: '50%', animation: 'pulse 1.5s infinite' }}></div>
             <span style={{ fontSize: '14px', color: '#0f172a' }}>Attempting via Razorpay API...</span>
          </div>
        </div>
      </div>
    );
  }

  // Default / No Action
  return (
    <div style={{ color: 'var(--color-text-secondary)', textAlign: 'center' }}>
      <p>No visual artifact for arm:</p>
      <strong style={{ color: '#fff' }}>{event.chosen_arm}</strong>
    </div>
  );
}
