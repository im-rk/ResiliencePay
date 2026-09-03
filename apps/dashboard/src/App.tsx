import { useEffect, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MetricsSummary } from "./panels/MetricsSummary";
import { AuditTrailTable } from "./panels/AuditTrailTable";
import { LiveEventFeed } from "./panels/LiveEventFeed";
import { InterventionInspector } from "./panels/InterventionInspector";
import { SimulationPanel } from "./panels/SimulationPanel";
import { DemoControls } from "./components/DemoControls";
import { Login } from "./components/Login";
import { useSimulationStream } from "./hooks/useSimulationStream";
import "./index.css";

const queryClient = new QueryClient();

const DEMO_BANDIT_RUN_ID = "run_demo_bandit";
const DEMO_BASELINE_RUN_ID = "run_demo_baseline";

function Dashboard() {
  const [selectedEvent, setSelectedEvent] = useState<any>(null);
  const { events, isConnected, setEvents } = useSimulationStream();

  // Stage Safety Net: Press Shift + S to load a perfect cached run if live demo fails
  useEffect(() => {
    const handleKeyDown = async (e: KeyboardEvent) => {
      if (e.shiftKey && e.key === 'S') {
        console.log("Stage Safety Net Activated: Loading cached simulation run...");
        try {
          const res = await fetch(`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/v1/audit-trail?page=1&size=300`);
          const data = await res.json();
          if (data && data.entries) {
            setEvents(data.entries);
            alert("Stage Safety Net: Cached run loaded successfully.");
          }
        } catch (err) {
          console.error("Safety net failed", err);
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [setEvents]);

  return (
    <div className="dashboard-container animate-fade-in">
      <header className="dashboard-header glass-panel" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', borderRadius: '0 0 16px 16px', borderTop: 'none', padding: '16px 24px' }}>
        <div>
          <h1 style={{ marginBottom: '4px', textAlign: 'left', fontSize: '20px' }}>ResiliencePay Console</h1>
          <p className="text-muted" style={{ margin: 0, textAlign: 'left', fontSize: '12px' }}>High-Density Operations & Experimentation</p>
        </div>
        
        <DemoControls />
        
        <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '12px', fontWeight: 500 }}>Demo Admin</div>
            <div className={isConnected ? "text-success" : "text-danger"} style={{ fontSize: '10px' }}>
              ● {isConnected ? "Live Stream Active" : "Stream Disconnected"}
            </div>
          </div>
        </div>
      </header>

      {/* Top Bar: Executive Benchmarks */}
      <div className="metrics-top-bar glass-panel" style={{ marginBottom: '16px', padding: '16px' }}>
         <MetricsSummary banditRunId={DEMO_BANDIT_RUN_ID} baselineRunId={DEMO_BASELINE_RUN_ID} />
      </div>
      
      <main className="dashboard-grid-dense">
        {/* Left Column: Live Event Feed */}
        <section className="glass-panel feed-panel" style={{ display: 'flex', flexDirection: 'column' }}>
          <h2 style={{ fontSize: '16px', marginBottom: '16px' }}>Live Event Feed</h2>
          <div className="panel-scroll" style={{ flex: 1 }}>
            <LiveEventFeed events={events} isConnected={isConnected} onSelectEvent={setSelectedEvent} selectedEventId={selectedEvent?.event_id} />
          </div>
        </section>

        {/* Center Column: Inspector */}
        <section className="glass-panel inspector-panel" style={{ display: 'flex', flexDirection: 'column' }}>
          <h2 style={{ fontSize: '16px', marginBottom: '16px' }}>Intervention Inspector</h2>
          <div className="panel-scroll" style={{ flex: 1 }}>
            <InterventionInspector event={selectedEvent} />
          </div>
        </section>

        {/* Right Column: Simulator */}
        <section className="glass-panel simulator-panel" style={{ display: 'flex', flexDirection: 'column' }}>
          <h2 style={{ fontSize: '16px', marginBottom: '16px' }}>Customer Simulation</h2>
          <div className="panel-scroll simulation-scroll" style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <SimulationPanel event={selectedEvent} />
          </div>
        </section>
      </main>

      {/* Bottom Drawer: Audit Trail */}
      <footer className="glass-panel audit-footer" style={{ marginTop: '16px', padding: '16px' }}>
        <h2 style={{ fontSize: '16px', marginBottom: '16px' }}>Immutable Audit Ledger</h2>
        <div className="audit-scroll" style={{ maxHeight: '240px' }}>
          <AuditTrailTable events={events} />
        </div>
      </footer>
    </div>
  );
}

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  return (
    <QueryClientProvider client={queryClient}>
      {isAuthenticated ? (
        <Dashboard />
      ) : (
        <Login onLogin={() => setIsAuthenticated(true)} />
      )}
    </QueryClientProvider>
  );
}
