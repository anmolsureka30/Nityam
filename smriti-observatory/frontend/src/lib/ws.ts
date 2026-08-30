import type { ObservatoryEvent } from "./types";

const RECONNECT_DELAY_MS = 1000;

export function connectSessionSocket(
  baseUrl: string,
  sessionId: string,
  onEvent: (event: ObservatoryEvent) => void,
): () => void {
  let socket: WebSocket | null = null;
  let closedByCaller = false;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  const connect = () => {
    socket = new WebSocket(`${baseUrl}/ws/sessions/${sessionId}`);
    socket.onmessage = (message) => {
      onEvent(JSON.parse(message.data as string) as ObservatoryEvent);
    };
    socket.onclose = () => {
      if (!closedByCaller) {
        reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
      }
    };
  };
  connect();

  return () => {
    closedByCaller = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    socket?.close();
  };
}
