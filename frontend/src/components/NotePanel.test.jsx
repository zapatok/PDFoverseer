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
