// @vitest-environment jsdom
//
// §A11 — the "Escanear todos los hospitales" button used to show
// "Escaneando…" for ANY global `loading`, including while Generar Excel
// (generateOutput) was running. It must only say that while an actual pase-1
// scan (runScan) is in flight.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import * as RadixTooltip from "@radix-ui/react-tooltip";

vi.mock("../lib/api", () => ({
  api: {
    listOutputs: vi.fn(async () => []),
    outputUrl: vi.fn(() => ""),
  },
}));
vi.mock("../lib/ws", () => ({ createWSClient: () => ({ close: () => {} }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import MonthOverview from "./MonthOverview";
import { useSessionStore } from "../store/session";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function mount(ui) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  // HospitalCard's sigla chips use ui/Tooltip — needs a Provider ancestor
  // (App.jsx supplies it in the real app).
  act(() => root.render(<RadixTooltip.Provider delayDuration={300}>{ui}</RadixTooltip.Provider>));
  return { container, unmount: () => act(() => root.unmount()) };
}

async function flush() {
  await act(async () => {});
}

function findButton(container, textIncludes) {
  return Array.from(container.querySelectorAll("button")).find((b) =>
    b.textContent.includes(textIncludes),
  );
}

beforeEach(() => {
  useSessionStore.setState({
    months: [{ session_id: "2026-04", year: 2026, month: 4, name: "Abril" }],
    session: { session_id: "2026-04", cells: { HPV: {}, HRB: {}, HLU: {}, HLL: {} } },
    loading: false,
    generating: false,
    scanning: false,
    error: null,
    historyView: false,
    historyDrawer: null,
    loadMonths: vi.fn(),
    openMonth: vi.fn(),
    selectHospital: vi.fn(),
    runScan: vi.fn(),
    generateOutput: vi.fn(async () => ({})),
    setHistoryView: vi.fn(),
    openHistoryDrawer: vi.fn(),
    closeHistoryDrawer: vi.fn(),
    deleteReorgOp: vi.fn(),
    exportManifest: vi.fn(),
  });
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("MonthOverview scan button label (§A11)", () => {
  it("says 'Escaneando…' while runScan is in flight (`scanning` true)", async () => {
    useSessionStore.setState({ loading: true, scanning: true });
    const view = mount(<MonthOverview />);
    await flush();
    const btn = findButton(view.container, "Escanear todos los hospitales") ??
      findButton(view.container, "Escaneando");
    expect(btn.textContent).toContain("Escaneando…");
    view.unmount();
  });

  it("does NOT say 'Escaneando…' while generateOutput's `generating` is true (loading is also true)", async () => {
    useSessionStore.setState({ loading: true, generating: true });
    const view = mount(<MonthOverview />);
    await flush();
    const btn = findButton(view.container, "Escanear todos los hospitales") ??
      findButton(view.container, "Escaneando");
    expect(btn.textContent).not.toContain("Escaneando…");
    view.unmount();
  });

  it("does NOT say 'Escaneando…' during a plain month open (openMonth's `loading` without a scan)", async () => {
    // §A11 second half: openMonth sets loading:true BEFORE deciding whether
    // to fire the pase-1 scan — a plain re-open of an already-scanned month
    // never scans, so the button must not claim it does. (When openMonth DOES
    // fire-and-forget runScan on first open, runScan's own `scanning` flag
    // lights the label — correctly.)
    useSessionStore.setState({ loading: true, scanning: false, generating: false });
    const view = mount(<MonthOverview />);
    await flush();
    const btn = findButton(view.container, "Escanear todos los hospitales") ??
      findButton(view.container, "Escaneando");
    expect(btn.textContent).not.toContain("Escaneando…");
    view.unmount();
  });
});
