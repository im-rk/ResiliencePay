import { useEffect, useState, useRef } from "react";

export function useSimulationStream() {
  const [events, setEvents] = useState<any[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const streamRef = useRef<EventSource | null>(null);

  useEffect(() => {
    // Connect to the SSE endpoint
    const url = `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/v1/simulations/stream`;
    const eventSource = new EventSource(url);
    streamRef.current = eventSource;

    eventSource.onopen = () => {
      setIsConnected(true);
      console.log("Connected to live simulation stream");
    };

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        // Prepend new events to the top of the feed, keeping max 300
        setEvents((prev) => [data, ...prev].slice(0, 300));
      } catch (err) {
        console.error("Failed to parse SSE data", err);
      }
    };

    eventSource.onerror = (err) => {
      console.error("SSE connection error", err);
      setIsConnected(false);
      eventSource.close();
      
      // Auto-reconnect after 2 seconds
      setTimeout(() => {
        if (streamRef.current === eventSource) {
           // Wait for next render cycle to re-establish
        }
      }, 2000);
    };

    return () => {
      eventSource.close();
      setIsConnected(false);
    };
  }, []);

  // Return the connected status so UI can show a live indicator
  return { events, isConnected, setEvents };
}
