import React, { useState } from "react";
import { usePolling } from "../hooks/usePolling";
import { fetchAuditTrail } from "../api/client";
import { formatTime } from "../lib/format";

function PanelSkeleton({ label }: { label: string }) {
  return <div className="panel-skeleton">{label}</div>;
}

function PanelError({ message }: { message: string }) {
  return <div className="panel-error">{message}</div>;
}

function AuditFilterBar({ filters, onChange }: { filters: any, onChange: (f: any) => void }) {
  return (
    <div className="filter-bar">
      {/* Simple stub for filters */}
      <span>Filters: None</span>
    </div>
  );
}

export function AuditTrailTable() {
  const [filters, setFilters] = useState<any>({});
  const { data, isLoading, isError } = usePolling(["audit-trail", filters], () => fetchAuditTrail(filters), 10000);

  return (
    <div className="audit-trail">
      <AuditFilterBar filters={filters} onChange={setFilters} />
      {isLoading && <PanelSkeleton label="Loading audit trail…" />}
      {isError && <PanelError message="Could not load audit trail." />}
      {data && data.entries && data.entries.length === 0 && (
        <div className="empty-audit">No matching audit entries</div>
      )}
      {data && data.entries && data.entries.length > 0 && (
        <table>
          <thead>
            <tr><th>Time</th><th>Cause</th><th>Arm</th><th>Gate</th><th>Simulated</th><th>Outcome</th></tr>
          </thead>
          <tbody>
            {data.entries.map((row: any) => (
              <tr key={row.audit_id} className={row.gate_result === false ? "row-blocked" : ""}>
                <td>{formatTime(row.recorded_at)}</td>
                <td>{row.cause_category ?? "—"}</td>
                <td>{row.chosen_arm ?? "—"}</td>
                <td>{row.gate_result === false ? "Blocked" : "Passed"}</td>
                <td>{row.simulated === true ? "Simulated" : row.simulated === false ? "Real" : "Unknown"}</td>
                <td>{row.outcome_result ?? "pending"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
