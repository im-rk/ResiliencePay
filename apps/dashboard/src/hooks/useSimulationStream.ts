import { useEffect, useState, useRef } from "react";

export function useSimulationStream() {
  const [events, setEvents] = useState<any[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const streamRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const url = `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/v1/simulations/stream`;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;

    const connect = () => {
      if (stopped) return;

      const eventSource = new EventSource(url);
      streamRef.current = eventSource;

      eventSource.onopen = () => {
        setIsConnected(true);
        console.log("Connected to live simulation stream");
      };

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data && (data.event_id || data.audit_id || data.episode_id)) {
            setEvents((prev) => [data, ...prev.filter(e => e.event_id !== data.event_id)].slice(0, 300));
          }
        } catch (err) {
          console.error("Failed to parse SSE data", err);
        }
      };

      eventSource.onerror = (err) => {
        console.error("SSE connection error", err);
        setIsConnected(false);
        eventSource.close();
        if (!stopped) reconnectTimer = setTimeout(connect, 2000);
      };
    };

    connect();

    return () => {
      stopped = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      streamRef.current?.close();
      setIsConnected(false);
    };
  }, []);

  // Return the connected status so UI can show a live indicator
  return { events, isConnected, setEvents };
}
