import { describe, it, expect, vi } from "vitest";
import { createWSClient } from "./ws";

function makeFakeWS() {
  const listeners = {};
  return {
    addEventListener: (t, fn) => { (listeners[t] ||= []).push(fn); },
    close: () => {},
    _fire: (t, e = {}) => (listeners[t] || []).forEach((fn) => fn(e)),
  };
}

describe("createWSClient onReconnect", () => {
  it("NO llama onReconnect en el primer open; SÍ en el open tras una reconexión", () => {
    const sockets = [];
    const factory = () => { const s = makeFakeWS(); sockets.push(s); return s; };
    const onReconnect = vi.fn();
    createWSClient("2026-04", { onEvent: () => {}, factory, onReconnect, initialBackoffMs: 1 });

    sockets[0]._fire("open");          // primer connect
    expect(onReconnect).not.toHaveBeenCalled();

    sockets[0]._fire("close");         // se cae → agenda reconexión
    return new Promise((r) => setTimeout(r, 5)).then(() => {
      sockets[1]._fire("open");        // reconectado
      expect(onReconnect).toHaveBeenCalledTimes(1);
    });
  });
});
