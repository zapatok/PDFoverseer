// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../lib/api", () => ({
  api: {
    getSession: vi.fn(async () => ({ session_id: "2026-04", cells: {} })),
    createSession: vi.fn(async () => ({})),
    listMonths: vi.fn(async () => ({ months: [] })),
  },
}));
vi.mock("../lib/ws", () => ({ createWSClient: () => ({ close: () => {} }) }));

import { useSessionStore } from "./session";
import { api } from "../lib/api";

describe("refetch on visibilitychange", () => {
  beforeEach(() => api.getSession.mockClear());

  it("re-fetchea cuando la pestaña vuelve a visible", async () => {
    await useSessionStore.getState().openMonth("2026-04", 2026, 4);
    api.getSession.mockClear();

    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
    await Promise.resolve();

    expect(api.getSession).toHaveBeenCalledWith("2026-04");
  });
});
