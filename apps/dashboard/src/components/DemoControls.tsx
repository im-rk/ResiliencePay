import { useState } from "react";

export function DemoControls() {
  const [isRunning, setIsRunning] = useState(false);
  const [chaosEnabled, setChaosEnabled] = useState(false);

  const handleRunBatch = async () => {
    setIsRunning(true);
    try {
      await fetch(`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/v1/simulations/run`, {
        method: 'POST'
      });
    } catch (e) {
      console.error("Failed to trigger run", e);
    }
    // Simulation spins up in the background
    setTimeout(() => setIsRunning(false), 2000);
  };

  const handleInjectChaos = async () => {
    try {
      const res = await fetch(`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/v1/simulations/chaos`, {
        method: 'POST'
      });
      const data = await res.json();
      setChaosEnabled(data.status === "chaos_enabled");
    } catch (e) {
      console.error("Failed to inject chaos", e);
    }
  };

  return (
    <div style={{ display: 'flex', gap: '12px' }}>
      <button 
        className="btn-primary" 
        onClick={handleRunBatch}
        disabled={isRunning}
        style={{ padding: '8px 16px', fontSize: '14px', width: 'auto' }}
      >
        {isRunning ? "Starting..." : "Run Batch Simulation (300)"}
      </button>

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
