import { useState } from "react";

export function DemoControls({ onRunStarted }: { onRunStarted?: (runId: string) => void }) {
  const [isRunning, setIsRunning] = useState(false);
  const [chaosEnabled, setChaosEnabled] = useState(false);
  const [chaosMessage, setChaosMessage] = useState("");
  const [runMessage, setRunMessage] = useState("");

  const handleRunBatch = async () => {
    setIsRunning(true);
    setRunMessage("");
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 120000);
    try {
      const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/v1/pipeline/run-batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ n_events: 300, policy: 'bandit', random_seed: Date.now() % 100000 }),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const result = await response.json() as { run_id?: string; n_events?: number };
      if (result.run_id) onRunStarted?.(result.run_id);
      setRunMessage(`Simulation completed: ${result.n_events ?? 300} events processed.`);
    } catch (e) {
      console.error("Failed to trigger run", e);
      setRunMessage(e instanceof DOMException && e.name === "AbortError" ? "Simulation timed out: check the backend." : "Simulation failed: check the backend.");
    } finally {
      window.clearTimeout(timeout);
      setIsRunning(false);
    }
  };

  const handleInjectChaos = async () => {
    try {
      const res = await fetch(`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/v1/simulations/chaos`, {
        method: 'POST'
      });
      const data = await res.json();
      setChaosEnabled(data.status === "chaos_enabled");
      setChaosMessage(data.status === "chaos_enabled" ? "Chaos mode enabled" : "Chaos mode disabled");
    } catch (e) {
      console.error("Failed to inject chaos", e);
      setChaosMessage("Chaos mode unavailable: check Redis");
    }
  };

  return (
    <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
      <button 
        className="btn-primary" 
        onClick={handleRunBatch}
        disabled={isRunning}
        style={{ padding: '8px 16px', fontSize: '14px', width: 'auto' }}
      >
        {isRunning ? "Starting..." : "Run Batch Simulation (300)"}
      </button>
      {runMessage && <span className="text-muted" style={{ fontSize: '11px' }}>{runMessage}</span>}
      {chaosMessage && <span className={chaosEnabled ? "text-danger" : "text-muted"} style={{ fontSize: '11px' }}>{chaosMessage}</span>}

      <button 
        className="btn-primary" 
        onClick={handleInjectChaos}
        style={{ 
          padding: '8px 16px', 
          fontSize: '14px', 
          width: 'auto',
          background: chaosEnabled ? 'var(--color-danger)' : 'rgba(255,255,255,0.1)',
          border: '1px solid var(--glass-border)'
        }}
      >
        {chaosEnabled ? "Stop Chaos" : "Inject Gateway Chaos"}
      </button>

      <button 
        className="btn-primary" 
        style={{ 
          padding: '8px 16px', 
          fontSize: '14px', 
          width: 'auto',
          background: 'rgba(255,255,255,0.1)',
          border: '1px solid var(--glass-border)'
        }}
        onClick={() => alert("Simulating customer opt-out webhook...")}
      >
        Simulate Opt-Out
      </button>
    </div>
  );
}
