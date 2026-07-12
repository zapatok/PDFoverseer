// @vitest-environment jsdom
//
// Debounce identity pinning (sibling of OverridePanel's fix, 1532c98): the
// 400 ms note autosave must land on the cell where the note was TYPED, not
// on whatever cell the unkeyed panel points at when the timer fires. The
// hook invokes the latest render's callback, so identity must travel as
// schedule-time args — a closure read of hospital/sigla misdirects the save
// on a fast sigla switch.
//
// Follows the DOM-mount pattern of OverridePanel.test.jsx (react-dom/client
// + act, real Zustand store with setState, fake timers, no testing-library).
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot } from "react-dom/client";

vi.mock("../lib/api", () => ({ api: {} }));
vi.mock("../lib/ws", () => ({ createWSClient: () => ({ close: () => {} }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import NotePanel from "./NotePanel";
import { useSessionStore } from "../store/session";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function mount(ui) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(ui));
  return { container, root, unmount: () => act(() => root.unmount()) };
}

function setTextareaValue(textarea, value) {
  const setter = Object.getOwnPropertyDescriptor(
    window.HTMLTextAreaElement.prototype,
    "value",
  ).set;
  setter.call(textarea, value);
  act(() => textarea.dispatchEvent(new Event("input", { bubbles: true })));
}

// React ≥17 maps onFocus/onBlur to the native focusin/focusout events.
function focusIn(el) {
  act(() => el.dispatchEvent(new FocusEvent("focusin", { bubbles: true })));
}
function focusOut(el) {
  act(() => el.dispatchEvent(new FocusEvent("focusout", { bubbles: true })));
}

const saveNote = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  useSessionStore.setState({
    session: { session_id: "2026-04", cells: { HRB: { odi: {} } } },
    pendingSaves: {},
    saveNote,
  });
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("NotePanel — debounced save pins the cell identity", () => {
  it("a note typed on one cell lands on THAT cell after switching sigla", () => {
    vi.useFakeTimers();
    try {
      const { container, root } = mount(
        <NotePanel hospital="HRB" sigla="odi" cell={{ note: "", note_status: null }} />,
      );
      const textarea = container.querySelector("textarea");
      setTextareaValue(textarea, "revisar firmas"); // debounced save scheduled for HRB|odi
      // Operator clicks another CategoryRow within the 400 ms window: the SAME
      // NotePanel instance re-renders with the new cell's props.
      act(() =>
        root.render(
          <NotePanel hospital="HRB" sigla="art" cell={{ note: "", note_status: null }} />,
        ),
      );
      act(() => vi.advanceTimersByTime(400));
      expect(saveNote).toHaveBeenCalledTimes(1);
      expect(saveNote).toHaveBeenCalledWith("2026-04", "HRB", "odi", {
        text: "revisar firmas",
        status: "por_resolver",
      });
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("NotePanel — resync respects a save in flight (§A9)", () => {
  it("typing + an IMMEDIATE blur (before the 400 ms debounce even fires) never reverts to the old value", () => {
    vi.useFakeTimers();
    try {
      const { container } = mount(
        <NotePanel hospital="HRB" sigla="odi" cell={{ note: "old note", note_status: null }} />,
      );
      const textarea = container.querySelector("textarea");
      focusIn(textarea);
      setTextareaValue(textarea, "typed note");
      // Blur BEFORE any timer advance — the debounced save hasn't even started
      // yet (saveStatus is still "idle"), so a resync gated only on the
      // store's pendingSaves would still see this as "nothing in flight" and
      // wrongly snap back to "old note".
      focusOut(textarea);
      expect(textarea.value).toBe("typed note");
    } finally {
      vi.useRealTimers();
    }
  });

  it("stays on the typed value through the whole save (debounce fire → network in flight → resolve)", () => {
    vi.useFakeTimers();
    try {
      const { container, root } = mount(
        <NotePanel hospital="HRB" sigla="odi" cell={{ note: "old note", note_status: null }} />,
      );
      const textarea = container.querySelector("textarea");
      focusIn(textarea);
      setTextareaValue(textarea, "typed note");
      focusOut(textarea);
      expect(textarea.value).toBe("typed note");

      // Debounce fires → saveNote (the store action) is invoked; the real
      // store action would mark pendingSaves "saving" in that same call —
      // simulate that here since saveNote is a spy.
      act(() => vi.advanceTimersByTime(400));
      expect(saveNote).toHaveBeenCalledTimes(1);
      act(() =>
        useSessionStore.setState({ pendingSaves: { "HRB|odi|note": "saving" } }),
      );
      expect(textarea.value).toBe("typed note"); // still mid-flight, no revert

      // Save resolves: the store would merge cell.note + clear pendingSaves in
      // the SAME set() — a re-render with both reflects that.
      act(() => useSessionStore.setState({ pendingSaves: {} }));
      act(() =>
        root.render(
          <NotePanel hospital="HRB" sigla="odi" cell={{ note: "typed note", note_status: null }} />,
        ),
      );
      expect(textarea.value).toBe("typed note"); // resync is now a harmless no-op
    } finally {
      vi.useRealTimers();
    }
  });

  it("a LEGITIMATE remote cell_updated (no local edit, no pending save) still resyncs", () => {
    const { container, root } = mount(
      <NotePanel hospital="HRB" sigla="odi" cell={{ note: "server v1", note_status: null }} />,
    );
    const textarea = container.querySelector("textarea");
    expect(textarea.value).toBe("server v1");
    // Nothing typed, nothing pending — a remote note update must still land.
    act(() =>
      root.render(
        <NotePanel hospital="HRB" sigla="odi" cell={{ note: "server v2", note_status: null }} />,
      ),
    );
    expect(textarea.value).toBe("server v2");
  });

  it("the dirty bridge resets on a cell IDENTITY change — cell A's typed text never sticks to cell B", () => {
    // Reviewer-confirmed bug: type + blur on cell A BEFORE the debounce fires
    // (dirty=true, saveStatus still "idle"), then switch selection to cell B
    // before the 400 ms window closes. Without an identity-change reset
    // (OverridePanel got one in 2f5e4b7; this panel didn't), `dirty` survived
    // the switch: the textarea kept showing A's draft on B — permanently,
    // even through a legitimate remote cell_updated for B — until unmount.
    // The SAVE itself was never wrong (identity travels as schedule-time
    // args); only the display misattributed the note.
    vi.useFakeTimers();
    try {
      const { container, root } = mount(
        <NotePanel hospital="HRB" sigla="odi" cell={{ note: "nota de odi", note_status: null }} />,
      );
      const textarea = container.querySelector("textarea");
      focusIn(textarea);
      setTextareaValue(textarea, "texto escrito en odi");
      focusOut(textarea); // dirty=true, debounce NOT yet fired
      // Operator switches to cell B before the debounce fires.
      act(() =>
        root.render(
          <NotePanel hospital="HRB" sigla="art" cell={{ note: "nota de art", note_status: null }} />,
        ),
      );
      // B must show ITS OWN note, not A's in-flight draft.
      expect(textarea.value).toBe("nota de art");
      // The scheduled save still lands on A (captured args) — unaffected.
      act(() => vi.advanceTimersByTime(400));
      expect(saveNote).toHaveBeenCalledTimes(1);
      expect(saveNote).toHaveBeenCalledWith("2026-04", "HRB", "odi", {
        text: "texto escrito en odi",
        status: "por_resolver",
      });
      // And a legitimate remote cell_updated for B resyncs normally (§A9 AC).
      act(() =>
        root.render(
          <NotePanel
            hospital="HRB"
            sigla="art"
            cell={{ note: "nota remota de art", note_status: null }}
          />,
        ),
      );
      expect(textarea.value).toBe("nota remota de art");
    } finally {
      vi.useRealTimers();
    }
  });
});
