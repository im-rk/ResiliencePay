
import { useEffect, useRef } from "react";

interface LiveEventFeedProps {
  events: any[];
  isConnected: boolean;
  onSelectEvent: (event: any) => void;
  selectedEventId?: string;
}

export function LiveEventFeed({ events, isConnected, onSelectEvent, selectedEventId }: LiveEventFeedProps) {
  const feedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (feedRef.current) feedRef.current.scrollTop = 0;
  }, [events.length]);

  if (!isConnected && events.length === 0) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--color-text-secondary)' }}>
        <div className="skeleton" style={{ width: '100%', height: '80px', marginBottom: '12px' }}></div>
        <div className="skeleton" style={{ width: '100%', height: '80px', marginBottom: '12px' }}></div>
        <div className="skeleton" style={{ width: '100%', height: '80px', marginBottom: '12px' }}></div>
        <p>Waiting for live events via SSE...</p>
      </div>
    );
  }

  return (
    <div ref={feedRef} className="panel-scroll-content" style={{ display: 'flex', flexDirection: 'column', gap: '16px', paddingRight: '8px' }}>
      {events.map((evt, idx) => {
        const isSelected = selectedEventId === evt.event_id;
        
        let statusClass = "badge awaiting";
        let statusText = "PROCESSING";
        if (evt.outcome_result === 'recovered') {
           statusClass = "badge success";
           statusText = "RECOVERED";
        } else if (evt.gate_result === 'blocked') {
           statusClass = "badge danger";
           statusText = "BLOCKED";
        } else if (evt.outcome_result) {
           statusClass = "badge danger";
           statusText = "FAILED";
        }

        return (
          <div 
            key={`${evt.event_id}-${idx}`}
            onClick={() => onSelectEvent(evt)}
            className={`case-card ${isSelected ? 'selected' : ''}`}
            style={{ 
              background: isSelected ? 'rgba(14, 165, 233, 0.1)' : '',
              borderColor: isSelected ? 'var(--color-accent)' : '',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '15px' }}>
                  {evt.event_id ? evt.event_id.split("-")[0].toUpperCase() : "EVT_UNKNOWN"}
                </span>
              </div>
              <div className={statusClass}>
                <span className="badge-dot" /> {statusText}
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div style={{ fontSize: '13px', color: 'var(--color-text-secondary)' }}>
                Amount: <strong style={{ color: '#fff' }}>₹{(evt.amount_paise ? evt.amount_paise / 100 : 0).toLocaleString()}</strong>
              </div>
              <div style={{ fontSize: '13px', color: 'var(--color-text-secondary)' }}>
                Cause: <strong style={{ color: '#fff' }}>{evt.cause_category || 'UNKNOWN'}</strong>
              </div>
            </div>

            {/* Breadcrumb Visualizer */}
            <div style={{ display: 'flex', alignItems: 'center', fontSize: '10px', gap: '6px', color: 'var(--color-text-secondary)', fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
               <span style={{ color: 'var(--color-success)' }}>Detect</span> →
               <span style={{ color: evt.cause_category ? 'var(--color-success)' : 'inherit' }}>Diagnose</span> →
               <span style={{ color: evt.chosen_arm ? 'var(--color-success)' : 'inherit' }}>Decide</span> →
               <span style={{ color: evt.gate_result === 'passed' ? 'var(--color-success)' : (evt.gate_result === 'blocked' ? 'var(--color-danger)' : 'inherit') }}>Gate</span> →
               <span style={{ color: evt.chosen_arm && evt.gate_result === 'passed' ? 'var(--color-success)' : 'inherit' }}>Act</span> →
               <span style={{ color: evt.outcome_result ? 'var(--color-success)' : 'inherit' }}>Observe</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
