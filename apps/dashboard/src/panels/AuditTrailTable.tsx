import React from "react";

interface AuditTrailTableProps {
  events: any[];
}

export function AuditTrailTable({ events }: AuditTrailTableProps) {
  return (
    <div className="audit-trail">
      {events.length === 0 ? (
        <div style={{ color: 'var(--color-text-secondary)' }}>No audit entries available. Start a simulation run.</div>
      ) : (
        <table style={{ width: '100%', textAlign: 'left', fontSize: '13px' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--glass-border)' }}>
              <th style={{ padding: '8px', color: 'var(--color-text-secondary)' }}>Event ID</th>
              <th style={{ padding: '8px', color: 'var(--color-text-secondary)' }}>Cause Category</th>
              <th style={{ padding: '8px', color: 'var(--color-text-secondary)' }}>Bandit Arm</th>
              <th style={{ padding: '8px', color: 'var(--color-text-secondary)' }}>Gate Verdict</th>
              <th style={{ padding: '8px', color: 'var(--color-text-secondary)' }}>Execution Status</th>
              <th style={{ padding: '8px', color: 'var(--color-text-secondary)' }}>Reason / Audit Note</th>
            </tr>
          </thead>
          <tbody>
            {events.map((row: any, idx: number) => {
              const eventId = row.event_id ? row.event_id.split("-")[0] : "EVT_UNKNOWN";
              
              let gateVerdict = "N/A";
              if (row.gate_result === "passed") gateVerdict = "PASSED";
              if (row.gate_result === "blocked") gateVerdict = "BLOCKED";
              
              let execStatus = "PENDING";
              if (row.outcome_result === "recovered") execStatus = "RECOVERED";
              if (row.outcome_result === "failed") execStatus = "FAILED";
              if (gateVerdict === "BLOCKED") execStatus = "HALTED";
              if (row.chosen_arm === "DEFER_RETRY") execStatus = "QUEUED";
              if (row.chosen_arm === "WHATSAPP_NUDGE" || row.chosen_arm === "SMS_NUDGE") execStatus = "DISPATCHED";
              
              let auditNote = "";
              if (execStatus === "RECOVERED") auditNote = "Customer completed via link";
              else if (execStatus === "HALTED") auditNote = "Blocked by strict rule";
              else if (execStatus === "QUEUED") auditNote = "Systemic cool-off applied";
              else if (execStatus === "DISPATCHED") auditNote = "Sent communication";
              else auditNote = row.error_code || "Processed";

              return (
                <tr key={`${row.event_id}-${idx}`} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  <td style={{ padding: '8px', fontFamily: 'monospace' }}>{eventId}</td>
                  <td style={{ padding: '8px' }}>{row.cause_category ?? "—"}</td>
                  <td style={{ padding: '8px' }}>{row.chosen_arm ?? "—"}</td>
                  <td style={{ padding: '8px', fontWeight: 'bold' }} className={gateVerdict === "PASSED" ? "text-success" : (gateVerdict === "BLOCKED" ? "text-danger" : "")}>
                    {gateVerdict}
                  </td>
                  <td style={{ padding: '8px' }}>{execStatus}</td>
                  <td style={{ padding: '8px', color: 'var(--color-text-secondary)' }}>{auditNote}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
