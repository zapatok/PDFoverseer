// @vitest-environment jsdom
// §A11 — the "Escanear todos los hospitales" button showed "Escaneando…"
// for ANY global `loading`, including while Generar Excel (generateOutput)
// was running. generateOutput now toggles a dedicated `generating` flag so
// the label can tell the two apart (MonthOverview derives
// `loading && !generating`).
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../lib/api", () => ({
  api: {
    generateOutput: vi.fn(async () => ({ output_path: "x.xlsx", worker_warnings: [] })),
  },
}));
vi.mock("../lib/ws", () => ({ createWSClient: () => ({ close: () => {} }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("../lib/useHistoryStore", () => ({ invalidateHistory: vi.fn() }));

import { useSessionStore } from "./session";
import { api } from "../lib/api";

const getState = () => useSessionStore.getState();

beforeEach(() => {
  vi.clearAllMocks();
  useSessionStore.setState({ loading: false, generating: false, error: null });
});

describe("generateOutput's dedicated `generating` flag", () => {
  it("is true while generateOutput is in flight, false after it resolves", async () => {
    let sawGeneratingDuring = false;
    api.generateOutput.mockImplementationOnce(async () => {
      sawGeneratingDuring = getState().generating;
      return { output_path: "x.xlsx", worker_warnings: [] };
    });
    await getState().generateOutput("2026-04");
    expect(sawGeneratingDuring).toBe(true);
    expect(getState().generating).toBe(false);
  });

  it("is cleared even when generateOutput fails", async () => {
    api.generateOutput.mockRejectedValueOnce(new Error("disk full"));
    await expect(getState().generateOutput("2026-04")).rejects.toThrow();
    expect(getState().generating).toBe(false);
  });
});
