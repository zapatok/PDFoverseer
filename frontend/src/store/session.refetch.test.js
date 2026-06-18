import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../lib/api", () => ({
  api: { getSession: vi.fn(async () => ({ session_id: "2026-04", cells: { HPV: { odi: { user_override: 42 } } } })) },
}));

import { useSessionStore } from "./session";
import { api } from "../lib/api";

describe("session_refresh / refetchSession", () => {
  beforeEach(() => {
    api.getSession.mockClear();
    useSessionStore.setState({ session: { session_id: "2026-04", cells: {} } });
  });

  it("refetchSession reemplaza la sesión con la del servidor", async () => {
    await useSessionStore.getState().refetchSession("2026-04");
    expect(api.getSession).toHaveBeenCalledWith("2026-04");
    expect(useSessionStore.getState().session.cells.HPV.odi.user_override).toBe(42);
  });

  it("session_refresh dispara un refetch de la sesión activa", async () => {
    useSessionStore.getState()._handleWSEvent({ type: "session_refresh" });
    // refetchSession es fire-and-forget async; espera a que se complete sin asumir
    // un nº fijo de microtasks (robusto si el mock cambia a uno con latencia).
    await vi.waitFor(() => expect(api.getSession).toHaveBeenCalledWith("2026-04"));
  });
});
