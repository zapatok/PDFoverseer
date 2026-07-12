// @vitest-environment jsdom
//
// F5: the inline count editor must never commit a negative value. Follows the
// DOM-mount pattern of DetailPanel.reorgLoop.test.jsx (react-dom/client + act,
// no testing-library in this project).
import { describe, it, expect, vi, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot } from "react-dom/client";

import InlineEditCount from "./InlineEditCount";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function mount(ui) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(ui));
  return { container, unmount: () => act(() => root.unmount()) };
}

function setInputValue(input, value) {
  const setter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    "value",
  ).set;
  setter.call(input, value);
  act(() => input.dispatchEvent(new Event("input", { bubbles: true })));
}

function pressEnter(input) {
  act(() => {
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  });
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("InlineEditCount — negative-input guard (F5)", () => {
  it("Enter with a negative draft does NOT call onCommit", () => {
    const onCommit = vi.fn();
    const { container } = mount(<InlineEditCount value={3} onCommit={onCommit} autoFocus />);
    const input = container.querySelector("input");
    expect(input).toBeTruthy();
    setInputValue(input, "-5");
    pressEnter(input);
    expect(onCommit).not.toHaveBeenCalled();
  });

  it("Enter with a valid non-negative draft commits it", () => {
    const onCommit = vi.fn();
    const { container } = mount(<InlineEditCount value={3} onCommit={onCommit} autoFocus />);
    const input = container.querySelector("input");
    setInputValue(input, "7");
    pressEnter(input);
    expect(onCommit).toHaveBeenCalledWith(7);
  });
});

describe("InlineEditCount — over-cap confirmation (task 5)", () => {
  it("Enter with a value above max shows the confirmation instead of committing", () => {
    const onCommit = vi.fn();
    const { container } = mount(
      <InlineEditCount value={3} onCommit={onCommit} max={6} autoFocus />,
    );
    const input = container.querySelector("input");
    setInputValue(input, "12");
    pressEnter(input);
    expect(onCommit).not.toHaveBeenCalled();
    expect(container.textContent).toContain("¿12 docs en 6 págs?");
  });

  it('"Sí" commits the over-cap value with { allowOverPages: true }', () => {
    const onCommit = vi.fn();
    const { container } = mount(
      <InlineEditCount value={3} onCommit={onCommit} max={6} autoFocus />,
    );
    const input = container.querySelector("input");
    setInputValue(input, "12");
    pressEnter(input);
    const buttons = Array.from(container.querySelectorAll("button"));
    const yes = buttons.find((b) => b.textContent === "Sí");
    expect(yes).toBeTruthy();
    act(() => yes.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(onCommit).toHaveBeenCalledWith(12, { allowOverPages: true });
  });

  it('"No" commits nothing and dismisses the confirmation', () => {
    const onCommit = vi.fn();
    const { container } = mount(
      <InlineEditCount value={3} onCommit={onCommit} max={6} autoFocus />,
    );
    const input = container.querySelector("input");
    setInputValue(input, "12");
    pressEnter(input);
    const buttons = Array.from(container.querySelectorAll("button"));
    const no = buttons.find((b) => b.textContent === "No");
    expect(no).toBeTruthy();
    act(() => no.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(onCommit).not.toHaveBeenCalled();
    expect(container.textContent).not.toContain("¿12 docs en 6 págs?");
  });

  it("typing again clears a stale confirmation", () => {
    const onCommit = vi.fn();
    const { container } = mount(
      <InlineEditCount value={3} onCommit={onCommit} max={6} autoFocus />,
    );
    const input = container.querySelector("input");
    setInputValue(input, "12");
    pressEnter(input);
    expect(container.textContent).toContain("¿12 docs en 6 págs?");
    setInputValue(input, "4");
    expect(container.textContent).not.toContain("¿12 docs en 6 págs?");
  });

  it("an unrelated blur closes the editor AND discards the confirmation (no stuck row)", () => {
    const onCommit = vi.fn();
    const { container } = mount(
      <InlineEditCount value={3} onCommit={onCommit} max={6} autoFocus />,
    );
    const input = container.querySelector("input");
    setInputValue(input, "12");
    pressEnter(input);
    expect(container.textContent).toContain("¿12 docs en 6 págs?");
    // The operator clicks somewhere unrelated (another cell, zoom controls):
    // React ≥17 maps onBlur to the native focusout event.
    act(() => input.dispatchEvent(new FocusEvent("focusout", { bubbles: true })));
    expect(container.querySelector("input")).toBeNull(); // editor closed
    expect(container.textContent).not.toContain("¿12 docs en 6 págs?");
    expect(onCommit).not.toHaveBeenCalled();
    // Re-opening starts fresh: display value as draft, no stale confirmation.
    const button = container.querySelector("button");
    act(() => button.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    const reopened = container.querySelector("input");
    expect(reopened).toBeTruthy();
    expect(reopened.value).toBe("3");
    expect(container.textContent).not.toContain("¿12 docs en 6 págs?");
  });

  it("a second Enter while the question is pending confirms with the flag (keyboard path)", () => {
    const onCommit = vi.fn();
    const { container } = mount(
      <InlineEditCount value={3} onCommit={onCommit} max={6} autoFocus />,
    );
    const input = container.querySelector("input");
    setInputValue(input, "12");
    pressEnter(input);
    expect(container.textContent).toContain("¿12 docs en 6 págs?");
    pressEnter(input); // confirm — must NOT just re-ask the same question
    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenCalledWith(12, { allowOverPages: true });
    expect(container.textContent).not.toContain("¿12 docs en 6 págs?");
    expect(container.querySelector("input")).toBeNull(); // editor closed
  });

  it("Sí/No preventDefault on mousedown so the click never blurs the input", () => {
    const onCommit = vi.fn();
    const { container } = mount(
      <InlineEditCount value={3} onCommit={onCommit} max={6} autoFocus />,
    );
    const input = container.querySelector("input");
    setInputValue(input, "12");
    pressEnter(input);
    const buttons = Array.from(container.querySelectorAll("button"));
    for (const label of ["Sí", "No"]) {
      const btn = buttons.find((b) => b.textContent === label);
      const ev = new MouseEvent("mousedown", { bubbles: true, cancelable: true });
      act(() => btn.dispatchEvent(ev));
      expect(ev.defaultPrevented).toBe(true);
    }
  });
});

describe("InlineEditCount — blur commits a valid draft (§A4)", () => {
  it("typing a valid, different value then blurring commits it (same path as Enter)", () => {
    const onCommit = vi.fn();
    const { container } = mount(<InlineEditCount value={3} onCommit={onCommit} autoFocus />);
    const input = container.querySelector("input");
    setInputValue(input, "7");
    act(() => input.dispatchEvent(new FocusEvent("focusout", { bubbles: true })));
    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenCalledWith(7);
    expect(container.querySelector("input")).toBeNull(); // editor closed
  });

  it("Escape then blur does NOT commit (Escape stays an explicit discard)", () => {
    const onCommit = vi.fn();
    const { container } = mount(<InlineEditCount value={3} onCommit={onCommit} autoFocus />);
    const input = container.querySelector("input");
    setInputValue(input, "7");
    act(() => input.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
    // The editor already closed on Escape; a trailing blur must not resurrect a commit.
    act(() => input.dispatchEvent(new FocusEvent("focusout", { bubbles: true })));
    expect(onCommit).not.toHaveBeenCalled();
  });

  it("blur with an invalid draft (negative) does NOT commit and closes the editor", () => {
    const onCommit = vi.fn();
    const { container } = mount(<InlineEditCount value={3} onCommit={onCommit} autoFocus />);
    const input = container.querySelector("input");
    setInputValue(input, "-5");
    act(() => input.dispatchEvent(new FocusEvent("focusout", { bubbles: true })));
    expect(onCommit).not.toHaveBeenCalled();
    expect(container.querySelector("input")).toBeNull();
  });

  it("blur with the draft unchanged from the current value does NOT commit", () => {
    const onCommit = vi.fn();
    const { container } = mount(<InlineEditCount value={3} onCommit={onCommit} autoFocus />);
    const input = container.querySelector("input");
    // No edit — draft is still "3" (autoFocus seeds it from value).
    act(() => input.dispatchEvent(new FocusEvent("focusout", { bubbles: true })));
    expect(onCommit).not.toHaveBeenCalled();
  });

  it("over-cap pending + blur elsewhere still discards (unchanged from before §A4)", () => {
    const onCommit = vi.fn();
    const { container } = mount(
      <InlineEditCount value={3} onCommit={onCommit} max={6} autoFocus />,
    );
    const input = container.querySelector("input");
    setInputValue(input, "12");
    pressEnter(input);
    expect(container.textContent).toContain("¿12 docs en 6 págs?");
    act(() => input.dispatchEvent(new FocusEvent("focusout", { bubbles: true })));
    expect(onCommit).not.toHaveBeenCalled();
    expect(container.querySelector("input")).toBeNull();
    expect(container.textContent).not.toContain("¿12 docs en 6 págs?");
  });
});

describe("InlineEditCount — select-on-focus (triage D1)", () => {
  it("focusing the input selects its full contents", () => {
    const onCommit = vi.fn();
    const { container } = mount(<InlineEditCount value={3} onCommit={onCommit} autoFocus />);
    const input = container.querySelector("input");
    input.select = vi.fn();
    act(() => input.dispatchEvent(new FocusEvent("focusin", { bubbles: true })));
    expect(input.select).toHaveBeenCalled();
  });
});
