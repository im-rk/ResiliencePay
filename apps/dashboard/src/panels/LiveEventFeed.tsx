import React from "react";
import { useSimulationStream } from "../hooks/useSimulationStream";

interface LiveEventFeedProps {
  events: any[];
  isConnected: boolean;
  onSelectEvent: (event: any) => void;
  selectedEventId?: string;
}

export function LiveEventFeed({ events, isConnected, onSelectEvent, selectedEventId }: LiveEventFeedProps) {

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
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', paddingRight: '8px' }}>
      {events.map((evt, idx) => {
        const isSelected = selectedEventId === evt.event_id;
        
        return (
          <div 
            key={`${evt.event_id}-${idx}`}
            onClick={() => onSelectEvent(evt)}
            style={{ 
              padding: '16px', 
              background: isSelected ? 'rgba(99, 102, 241, 0.15)' : 'rgba(255,255,255,0.03)',
              border: `1px solid ${isSelected ? 'var(--color-accent)' : 'var(--glass-border)'}`,
              borderRadius: '8px',
              cursor: 'pointer',
              transition: 'all 0.2s'
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
              <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: '14px' }}>
                {evt.event_id ? evt.event_id.split("-")[0].toUpperCase() : "EVT_UNKNOWN"}
              </span>
              <span className={evt.outcome_result === 'recovered' ? "text-success" : (evt.gate_result === 'blocked' ? "text-danger" : "text-muted")} style={{ fontSize: '12px', fontWeight: 600 }}>
                {evt.outcome_result === 'recovered' ? '₹ RECOVERED' : (evt.gate_result === 'blocked' ? 'BLOCKED' : 'FAILED')}
              </span>
            </div>

            <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', marginBottom: '12px' }}>
              Cause: <strong style={{ color: '#fff' }}>{evt.cause_category || 'UNKNOWN'}</strong>
            </div>

            {/* Breadcrumb Visualizer */}
            <div style={{ display: 'flex', alignItems: 'center', fontSize: '10px', gap: '4px', color: 'var(--color-text-secondary)' }}>
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
