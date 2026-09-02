import React from "react";
import { usePolling } from "../hooks/usePolling";
import { fetchExceptions } from "../api/client";

function PanelSkeleton({ label }: { label: string }) {
  return <div className="skeleton" style={{ padding: '2rem' }}>{label}</div>;
}

function PanelError({ message }: { message: string }) {
  return <div className="panel-error">{message}</div>;
}

export function ExceptionList({ runId }: { runId: string }) {
  const { data, isLoading, isError } = usePolling(["exceptions", runId], () => fetchExceptions(runId));

  if (isLoading) return <PanelSkeleton label="Loading exceptions…" />;
  if (isError) return <PanelError message="Could not load exceptions." />;

  if (data!.length === 0) {
    return (
      <div className="exception-list-empty">
        <strong>0 unresolved exceptions.</strong>
        <p>Every event in this batch reached a terminal, explained state.</p>
      </div>
    );
  }

  return (
    <ul className="exception-list">
      {data!.map((ex: any) => (
        <li key={ex.event_id}>
          <span className="cause">{ex.cause_category}</span>
          <span className="reason">{ex.reason}</span>
        </li>
      ))}
    </ul>
  );
}
