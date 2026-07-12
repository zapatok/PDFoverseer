// A1 — store-level `cellFiles` cache with stale-while-revalidate. This is the
// ONE place that calls `api.getCellFiles`; FileList/DetailPanel/PDFLightbox
// (Task 11) read the cache instead of fetching on their own.
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../lib/api", () => ({
  api: { getCellFiles: vi.fn() },
}));

import { api } from "../lib/api";
import { useSessionStore } from "./session";

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function resetStore() {
  useSessionStore.setState({ cellFiles: {}, _cellFilesFetch: new Map() });
}

describe("store cellFiles — SWR cache (§A1)", () => {
  beforeEach(() => {
    api.getCellFiles.mockReset();
    resetStore();
  });

  it("(a) fetchCellFiles puebla cellFiles[key]", async () => {
    api.getCellFiles.mockResolvedValueOnce([{ name: "a.pdf" }]);
    await useSessionStore.getState().fetchCellFiles("2026-04", "HPV", "odi");
    expect(useSessionStore.getState().cellFiles["HPV|odi"]).toEqual({
      files: [{ name: "a.pdf" }],
      error: null,
    });
    expect(api.getCellFiles).toHaveBeenCalledWith("2026-04", "HPV", "odi");
  });

  it("(b) SWR: un refetch de la MISMA celda conserva los files previos hasta que el nuevo resuelve", async () => {
    api.getCellFiles.mockResolvedValueOnce([{ name: "a.pdf" }]);
    await useSessionStore.getState().fetchCellFiles("2026-04", "HPV", "odi");

    const d = deferred();
    api.getCellFiles.mockReturnValueOnce(d.promise);
    const inFlight = useSessionStore.getState().fetchCellFiles("2026-04", "HPV", "odi");

    // Todavía no resuelve el segundo fetch — los files viejos siguen ahí, sin
    // null intermedio (eso es lo que mata el flash de Skeleton en FileList).
    expect(useSessionStore.getState().cellFiles["HPV|odi"].files).toEqual([{ name: "a.pdf" }]);

    d.resolve([{ name: "b.pdf" }]);
    await inFlight;
    expect(useSessionStore.getState().cellFiles["HPV|odi"].files).toEqual([{ name: "b.pdf" }]);
  });

  it("(c) dedup: bumps que llegan con un fetch en vuelo colapsan en, a lo sumo, 1 llamada extra", async () => {
    const d = deferred();
    api.getCellFiles.mockReturnValueOnce(d.promise);
    const p1 = useSessionStore.getState().fetchCellFiles("2026-04", "HPV", "odi");

    // Dos bumps más mientras el primer fetch sigue en vuelo.
    useSessionStore.getState().fetchCellFiles("2026-04", "HPV", "odi");
    useSessionStore.getState().fetchCellFiles("2026-04", "HPV", "odi");
    expect(api.getCellFiles).toHaveBeenCalledTimes(1);

    api.getCellFiles.mockResolvedValueOnce([{ name: "b.pdf" }]);
    d.resolve([{ name: "a.pdf" }]);
    await p1;
    await Promise.resolve();
    await Promise.resolve();

    // 1 inicial + 1 follow-up de dedup — NUNCA 3 (uno por cada bump).
    expect(api.getCellFiles).toHaveBeenCalledTimes(2);
  });

  it("(d) patchCellFile muta la entrada (optimista de los steppers)", () => {
    useSessionStore.setState({
      cellFiles: {
        "HPV|odi": { files: [{ name: "a.pdf", effective_count: 1 }], error: null },
      },
    });
    useSessionStore.getState().patchCellFile("HPV", "odi", "a.pdf", { effective_count: 2, origin: "Manual" });
    const entry = useSessionStore.getState().cellFiles["HPV|odi"];
    expect(entry.files[0]).toEqual({ name: "a.pdf", effective_count: 2, origin: "Manual" });
  });

  it("(d2) patchCellFile no revienta sin entrada previa (no-op)", () => {
    expect(() =>
      useSessionStore.getState().patchCellFile("HPV", "odi", "a.pdf", { effective_count: 2 }),
    ).not.toThrow();
    expect(useSessionStore.getState().cellFiles["HPV|odi"]).toBeUndefined();
  });

  it("(e) error de fetch → error en la entrada, files previos intactos", async () => {
    api.getCellFiles.mockResolvedValueOnce([{ name: "a.pdf" }]);
    await useSessionStore.getState().fetchCellFiles("2026-04", "HPV", "odi");

    api.getCellFiles.mockRejectedValueOnce(new Error("boom"));
    await useSessionStore.getState().fetchCellFiles("2026-04", "HPV", "odi");

    const entry = useSessionStore.getState().cellFiles["HPV|odi"];
    expect(entry.files).toEqual([{ name: "a.pdf" }]);
    expect(entry.error).toMatch(/boom/);
  });

  it("(f) primer open de una celda sin entrada previa dispara el fetch", async () => {
    expect(useSessionStore.getState().cellFiles["HPV|odi"]).toBeUndefined();
    api.getCellFiles.mockResolvedValueOnce([{ name: "a.pdf" }]);
    await useSessionStore.getState().fetchCellFiles("2026-04", "HPV", "odi");
    expect(api.getCellFiles).toHaveBeenCalledTimes(1);
    expect(useSessionStore.getState().cellFiles["HPV|odi"].files).toEqual([{ name: "a.pdf" }]);
  });

  it("no fetchea sin session_id/hospital/sigla", async () => {
    await useSessionStore.getState().fetchCellFiles(null, "HPV", "odi");
    await useSessionStore.getState().fetchCellFiles("2026-04", null, "odi");
    await useSessionStore.getState().fetchCellFiles("2026-04", "HPV", null);
    expect(api.getCellFiles).not.toHaveBeenCalled();
  });
});
