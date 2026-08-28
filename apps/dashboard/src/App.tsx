import React, { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MetricsSummary } from "./panels/MetricsSummary";
import { LearningCurveChart } from "./panels/LearningCurveChart";
import { AuditTrailTable } from "./panels/AuditTrailTable";
import { ExceptionList } from "./panels/ExceptionList";
import "./index.css";

const queryClient = new QueryClient();

// Hardcoded for the demo, or can be passed via URL / state
const DEMO_BANDIT_RUN_ID = "run_demo_bandit";
const DEMO_BASELINE_RUN_ID = "run_demo_baseline";

function Dashboard() {
  return (
    <div className="dashboard-container">
      <header className="dashboard-header">
        <h1>ResiliencePay Dashboard</h1>
      </header>
      
      <main className="dashboard-grid">
        <section className="panel summary-panel">
          <h2>Metrics Summary</h2>
          <MetricsSummary banditRunId={DEMO_BANDIT_RUN_ID} baselineRunId={DEMO_BASELINE_RUN_ID} />
        </section>

        <section className="panel chart-panel">
          <h2>Learning Curve</h2>
          <LearningCurveChart banditRunId={DEMO_BANDIT_RUN_ID} baselineRunId={DEMO_BASELINE_RUN_ID} />
        </section>

        <section className="panel exceptions-panel">
          <h2>Exception List</h2>
          <ExceptionList runId={DEMO_BANDIT_RUN_ID} />
        </section>

        <section className="panel table-panel">
          <h2>Audit Trail</h2>
          <AuditTrailTable />
        </section>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Dashboard />
    </QueryClientProvider>
  );
}
