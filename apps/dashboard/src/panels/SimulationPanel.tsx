
export function SimulationPanel({ event }: { event: any }) {
  if (!event) {
    return (
      <div style={{ color: 'var(--color-text-secondary)', textAlign: 'center' }}>
        <p>Waiting for intervention...</p>
      </div>
    );
  }

  const arm = event.chosen_arm;
  const cause = event.cause_category || "the reported gateway issue";

  if (["send_nudge_hinglish", "send_nudge_english", "WHATSAPP_NUDGE", "SMS_NUDGE"].includes(arm)) {
    const hinglish = arm === "send_nudge_hinglish";
    return (
      <div style={{ 
        width: '100%', maxWidth: '300px', background: '#e5ddd5', 
        borderRadius: '16px', overflow: 'hidden', color: '#000',
        boxShadow: '0 10px 25px rgba(0,0,0,0.5)'
      }}>
        <div style={{ background: '#075e54', padding: '16px', color: '#fff', fontWeight: 'bold' }}>
          {hinglish ? "Hinglish nudge preview" : "Customer message preview"}
        </div>
        <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px', background: 'url("https://user-images.githubusercontent.com/15075759/28719144-86dc0f70-73b1-11e7-911d-60d70fcded21.png")' }}>
          <div style={{ background: '#fff', padding: '8px 12px', borderRadius: '0 8px 8px 8px', maxWidth: '85%', fontSize: '14px', alignSelf: 'flex-start' }}>
            {hinglish ? "Namaste! Aapka payment complete nahi hua." : "Hi! Your recent payment did not go through."} The issue was {cause}.
            <br/><br/>
            No worries! You can complete it using the link below:
            <br/>
            <a href="#" style={{ color: '#0275d8' }}>rzp.io/i/recovery</a>
          </div>
        </div>
      </div>
    );
  }

  if (["retry_immediate", "retry_short_delay", "retry_long_delay", "DEFER_RETRY", "SILENT_RETRY"].includes(arm)) {
    const delayed = arm !== "retry_immediate" && arm !== "SILENT_RETRY";
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
            {delayed ? (arm === "retry_long_delay" ? "Retry scheduled in 3 days" : "Retry scheduled in 4 hours") : "Retrying now"}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
             <div className="skeleton" style={{ width: '24px', height: '24px', borderRadius: '50%', animation: 'pulse 1.5s infinite' }}></div>
             <span style={{ fontSize: '14px', color: '#0f172a' }}>{delayed ? "Waiting for the scheduled retry window..." : "Attempting via Razorpay API..."}</span>
          </div>
        </div>
      </div>
    );
  }

  if (arm === "send_card_update_link") {
    return (
      <div className="simulation-artifact simulation-card-update">
        <div className="simulation-artifact-header">Card update required</div>
        <div className="simulation-artifact-body">
          <div className="payment-card-icon">CARD</div>
          <strong>Your saved card needs attention</strong>
          <p>The payment failed because of {cause}. Update the payment method before trying again.</p>
          <button className="btn-primary" type="button">Update payment method</button>
        </div>
      </div>
    );
  }

  if (arm === "escalate_human") {
    return (
      <div className="simulation-artifact simulation-escalation">
        <div className="simulation-artifact-header">Human review queue</div>
        <div className="simulation-artifact-body">
          <strong>Escalation created</strong>
          <p>This case is routed to an operator because {cause} needs manual attention.</p>
          <span className="simulation-status">PENDING REVIEW</span>
        </div>
      </div>
    );
  }

  if (arm === "stop") {
    return (
      <div className="simulation-artifact simulation-stop">
        <div className="simulation-artifact-header">Recovery stopped safely</div>
        <div className="simulation-artifact-body">
          <strong>No customer action sent</strong>
          <p>The policy selected a terminal stop for {cause}.</p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ color: 'var(--color-text-secondary)', textAlign: 'center' }}>
      <p>No visual artifact for arm:</p>
      <strong style={{ color: '#fff' }}>{event.chosen_arm}</strong>
    </div>
  );
}
