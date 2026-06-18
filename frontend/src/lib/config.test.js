import { describe, it, expect } from "vitest";
import { backendHost, makeApiBase, makeWsBase } from "./config";

describe("config host derivation", () => {
  it("usa el hostname de la página (LAN), no 127.0.0.1", () => {
    expect(backendHost("192.168.1.50")).toBe("192.168.1.50");
  });
  it("cae a 127.0.0.1 cuando no hay hostname (SSR/test)", () => {
    expect(backendHost("")).toBe("127.0.0.1");
    expect(backendHost(undefined)).toBe("127.0.0.1");
  });
  it("arma API y WS base con el host derivado y puerto 8000", () => {
    expect(makeApiBase("192.168.1.50", "http:")).toBe("http://192.168.1.50:8000/api");
    expect(makeWsBase("192.168.1.50", "http:")).toBe("ws://192.168.1.50:8000");
    expect(makeWsBase("192.168.1.50", "https:")).toBe("wss://192.168.1.50:8000");
  });
});
