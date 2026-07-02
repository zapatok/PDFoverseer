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
