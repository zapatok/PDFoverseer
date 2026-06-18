/**
 * Single source of truth for the backend host (M1 multiplayer / LAN).
 *
 * The host is derived from the page's own hostname so a LAN client (Carla's
 * browser, loaded from the server's IP) hits THAT server — not her own
 * localhost. Falls back to 127.0.0.1 for SSR/tests. Backend port is 8000.
 */
const PORT = 8000;

export function backendHost(hostname) {
  return hostname || "127.0.0.1";
}

export function makeApiBase(hostname, pageProto) {
  const proto = pageProto === "https:" ? "https:" : "http:";
  return `${proto}//${backendHost(hostname)}:${PORT}/api`;
}

export function makeWsBase(hostname, pageProto) {
  const proto = pageProto === "https:" ? "wss:" : "ws:";
  return `${proto}//${backendHost(hostname)}:${PORT}`;
}

const _hostname = typeof window !== "undefined" ? window.location?.hostname : "";
const _proto = typeof window !== "undefined" ? window.location?.protocol : "http:";

export const API_BASE = makeApiBase(_hostname, _proto);
export const WS_BASE = makeWsBase(_hostname, _proto);
