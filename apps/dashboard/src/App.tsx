import { useEffect, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Activity, LayoutDashboard, Search, ShieldCheck, TerminalSquare } from "lucide-react";
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

type ViewTab = 'dashboard' | 'cases' | 'audit' | 'simulation';

function Dashboard() {
  const [activeTab, setActiveTab] = useState<ViewTab>('dashboard');
  const [selectedEvent, setSelectedEvent] = useState<any>(null);
  const { events, isConnected, setEvents } = useSimulationStream();

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
    <div className="app-container">
      {/* Top Navigation */}
      <nav className="top-nav">
        <div style={{ display: 'flex', alignItems: 'center', gap: '32px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{ width: '32px', height: '32px', borderRadius: '8px', background: 'linear-gradient(135deg, var(--color-accent), #3b82f6)', display: 'grid', placeItems: 'center' }}>
              <ShieldCheck size={18} color="white" />
            </div>
            <div>
              <h1 style={{ fontSize: '18px', margin: 0, lineHeight: 1.2 }}>ResiliencePay</h1>
              <div style={{ fontSize: '11px', color: 'var(--color-accent)', fontWeight: 600, letterSpacing: '0.05em' }}>AI RECOVERY AGENT</div>
            </div>
          </div>
          
          <div className="nav-tabs">
            <button className={`nav-tab ${activeTab === 'dashboard' ? 'active' : ''}`} onClick={() => setActiveTab('dashboard')}>
              <LayoutDashboard size={16} /> Dashboard
            </button>
            <button className={`nav-tab ${activeTab === 'cases' ? 'active' : ''}`} onClick={() => setActiveTab('cases')}>
              <Search size={16} /> Recovery Cases
            </button>
            <button className={`nav-tab ${activeTab === 'audit' ? 'active' : ''}`} onClick={() => setActiveTab('audit')}>
              <Activity size={16} /> Audit Ledger
            </button>
            <button className={`nav-tab ${activeTab === 'simulation' ? 'active' : ''}`} onClick={() => setActiveTab('simulation')}>
              <TerminalSquare size={16} /> Simulator
            </button>
          </div>
        </div>
        
        <div style={{ display: 'flex', gap: '24px', alignItems: 'center' }}>
          <DemoControls />
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', paddingLeft: '24px', borderLeft: '1px solid var(--glass-border)' }}>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-text-primary)' }}>Demo Admin</div>
              <div style={{ fontSize: '10px', color: isConnected ? 'var(--color-success)' : 'var(--color-danger)', display: 'flex', alignItems: 'center', gap: '4px', justifyContent: 'flex-end' }}>
                <span className="badge-dot" style={{ background: isConnected ? 'var(--color-success)' : 'var(--color-danger)' }} />
                {isConnected ? "Live Stream Active" : "Stream Disconnected"}
              </div>
            </div>
            <div style={{ width: '36px', height: '36px', borderRadius: '50%', background: 'rgba(255,255,255,0.1)', border: '1px solid var(--glass-border)', display: 'grid', placeItems: 'center', color: 'var(--color-text-primary)' }}>
              DA
            </div>
          </div>
        </div>
      </nav>

      <main className="view-container animate-fade-in">
        {/* DASHBOARD VIEW */}
        {activeTab === 'dashboard' && (
          <div className="animate-fade-in">
            <div style={{ marginBottom: '32px' }}>
              <h2 style={{ fontSize: '24px', marginBottom: '8px' }}>Executive Overview</h2>
              <p className="text-muted">Real-time revenue recovery metrics and AI performance.</p>
            </div>
            <MetricsSummary banditRunId={DEMO_BANDIT_RUN_ID} baselineRunId={DEMO_BASELINE_RUN_ID} />
          </div>
        )}

        {/* CASES VIEW */}
        {activeTab === 'cases' && (
          <div className="animate-fade-in" style={{ display: 'flex', gap: '24px', height: 'calc(100vh - 180px)' }}>
            <div style={{ flex: '1', display: 'flex', flexDirection: 'column' }}>
              <h2 style={{ fontSize: '20px', marginBottom: '16px' }}>Active Cases</h2>
              <div className="glass-panel" style={{ flex: 1, padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                <div style={{ flex: 1, overflowY: 'auto' }}>
                   <LiveEventFeed events={events} isConnected={isConnected} onSelectEvent={setSelectedEvent} selectedEventId={selectedEvent?.event_id} />
                </div>
              </div>
            </div>
            
            <div style={{ flex: '1.2', display: 'flex', flexDirection: 'column' }}>
               <h2 style={{ fontSize: '20px', marginBottom: '16px' }}>Case Inspector</h2>
               <div className="glass-panel" style={{ flex: 1, overflowY: 'auto' }}>
                  <InterventionInspector event={selectedEvent} />
               </div>
            </div>
          </div>
        )}

        {/* AUDIT VIEW */}
        {activeTab === 'audit' && (
          <div className="animate-fade-in" style={{ height: 'calc(100vh - 180px)', display: 'flex', flexDirection: 'column' }}>
            <div style={{ marginBottom: '24px' }}>
              <h2 style={{ fontSize: '24px', marginBottom: '8px' }}>Immutable Audit Ledger</h2>
              <p className="text-muted">Cryptographically verifiable log of all AI decisions, compliance checks, and recovery actions.</p>
            </div>
            <div className="glass-panel" style={{ flex: 1, padding: 0, overflowY: 'auto' }}>
               <AuditTrailTable events={events} />
            </div>
          </div>
        )}

        {/* SIMULATION VIEW */}
        {activeTab === 'simulation' && (
          <div className="animate-fade-in" style={{ height: 'calc(100vh - 180px)', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
            <div className="glass-panel" style={{ width: '100%', maxWidth: '800px' }}>
               <div style={{ marginBottom: '24px', textAlign: 'center' }}>
                 <h2 style={{ fontSize: '24px', marginBottom: '8px' }}>Customer Simulation</h2>
                 <p className="text-muted">Generate synthetic payment failures to test the recovery agent live.</p>
               </div>
               <SimulationPanel event={selectedEvent} />
            </div>
          </div>
        )}
      </main>
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
