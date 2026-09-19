"use client";

import { useEffect, useRef, useState } from "react";

export type TraceEvent = {
  type: string;
  task_id: string;
  entry?: {
    id: string;
    timestamp: string;
    event_type: string;
    description: string;
    thought?: string;
    tool_call?: {
      call_id: string;
      tool_name: string;
      arguments: Record<string, unknown>;
    };
    tool_result?: {
      call_id: string;
      tool_name: string;
      success: boolean;
      data?: unknown;
      error?: string;
    };
    metadata?: Record<string, unknown>;
  };
  status?: string;
  duration_ms?: number;
  error?: string;
  [key: string]: unknown;
};

export function useAgentTaskWebSocket(
  taskId: string | null,
  token: string | null,
  onEvent?: (event: TraceEvent) => void
) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<TraceEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!taskId) {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setIsConnected(false);
      return;
    }

    // Determine WebSocket protocol and host
    const isHttps = typeof window !== "undefined" && window.location.protocol === "https:";
    const protocol = isHttps ? "wss:" : "ws:";
    const host = typeof window !== "undefined" ? window.location.host : "localhost:8000";
    const apiHost = process.env.NEXT_PUBLIC_API_URL
      ? process.env.NEXT_PUBLIC_API_URL.replace(/^http/, "ws")
      : `${protocol}//${host}`;

    const wsUrl = `${apiHost}/api/v1/agent/tasks/${taskId}/ws${token ? `?token=${encodeURIComponent(token)}` : ""}`;

    let reconnectTimeout: NodeJS.Timeout | null = null;
    let isCleanedUp = false;

    function connect() {
      try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          if (!isCleanedUp) {
            setIsConnected(true);
          }
        };

        ws.onmessage = (event) => {
          try {
            const data: TraceEvent = JSON.parse(event.data);
            setLastEvent(data);
            onEvent?.(data);
          } catch {
            // non-json message (e.g. pong)
          }
        };

        ws.onclose = () => {
          if (!isCleanedUp) {
            setIsConnected(false);
            // Reconnect after 3s if component is still mounted and task is active
            reconnectTimeout = setTimeout(connect, 3000);
          }
        };

        ws.onerror = () => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.close();
          }
        };
      } catch (err) {
        console.warn("WebSocket connection error:", err);
      }
    }

    connect();

    return () => {
      isCleanedUp = true;
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setIsConnected(false);
    };
  }, [taskId, token]);

  return { isConnected, lastEvent };
}
