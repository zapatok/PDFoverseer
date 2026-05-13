/**
 * WebSocket client with reconnect + JSON event dispatch.
 *
 * createWSClient(sessionId, { onEvent, factory?, initialBackoffMs? }) → client
 *   - onEvent(event): callback for each parsed JSON message
 *   - factory(url): optional WebSocket constructor (for tests)
 *   - client.close(): closes connection and disables reconnect
 *
 * Reconnect: exponential backoff capped at 30s. Connection lifecycle:
 *   open → message → close (auto-reconnect) | manual close (no reconnect)
 */

const WS_BASE = (() => {
  if (typeof window === "undefined") return "ws://127.0.0.1:8000";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  // Vite dev server proxies /api — for /ws we point at the FastAPI port directly
  return `${proto}//127.0.0.1:8000`;
})();

export function createWSClient(sessionId, { onEvent, factory, initialBackoffMs = 1000 } = {}) {
  const url = `${WS_BASE}/ws/sessions/${sessionId}`;
  const makeWS = factory || ((u) => new WebSocket(u));
  let socket = null;
  let backoff = initialBackoffMs;
  let closedByUser = false;
  let reconnectTimer = null;

  function connect() {
    socket = makeWS(url);
    socket.addEventListener("open", () => {
      backoff = initialBackoffMs;
    });
    socket.addEventListener("message", (evt) => {
      try {
        const parsed = JSON.parse(evt.data);
        onEvent(parsed);
      } catch {
        // Ignore non-JSON frames (pings as text are fine, malformed payloads dropped silently)
      }
    });
    socket.addEventListener("close", () => {
      if (closedByUser) return;
      reconnectTimer = setTimeout(() => {
        // Re-check inside the callback: client.close() may have been called
        // between the close-event-firing and this timer firing.
        if (closedByUser) return;
        backoff = Math.min(backoff * 2, 30000);
        connect();
      }, backoff);
    });
    socket.addEventListener("error", () => {
      // close handler will fire after error; don't double-schedule
    });
    client._currentSocket = socket;
  }

  const client = {
    close() {
      closedByUser = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
    },
    _currentSocket: null,
  };

  connect();
  return client;
}
