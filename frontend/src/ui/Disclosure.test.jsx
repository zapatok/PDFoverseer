// @vitest-environment jsdom
//
// Disclosure primitive: collapsed by default, toggles content on click of a
// real <button> summary (keyboard-accessible by construction, aria-expanded
// reflects state), defaultOpen starts expanded.
//
// Follows the DOM-mount pattern of OverridePanel.test.jsx / DetailPanel
// tests (react-dom/client + act, no testing-library in this project).
import { describe, it, expect, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot } from "react-dom/client";

import Disclosure from "./Disclosure";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function mount(ui) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(ui));
  return { container, root, unmount: () => act(() => root.unmount()) };
}

function click(button) {
  act(() => button.dispatchEvent(new MouseEvent("click", { bubbles: true })));
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("Disclosure", () => {
  it("renders collapsed by default and toggles content on click of the summary", () => {
    const { container } = mount(
      <Disclosure summary="Reorganización">
        <div>contenido oculto</div>
      </Disclosure>,
    );
    expect(container.textContent).not.toContain("contenido oculto");
    const button = container.querySelector("button");
    click(button);
    expect(container.textContent).toContain("contenido oculto");
    click(button);
    expect(container.textContent).not.toContain("contenido oculto");
  });

  it("the summary is a real button (keyboard-accessible by construction)", () => {
    const { container } = mount(
      <Disclosure summary="Reorganización">
        <div>contenido</div>
      </Disclosure>,
    );
    const button = Array.from(container.querySelectorAll("button")).find(
      (b) => b.textContent === "Reorganización",
    );
    expect(button).toBeTruthy();
    expect(button.getAttribute("aria-expanded")).toBe("false");
    click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
  });

  it("defaultOpen starts expanded", () => {
    const { container } = mount(
      <Disclosure summary="Reorganización" defaultOpen>
        <div>contenido inicial</div>
      </Disclosure>,
    );
    expect(container.textContent).toContain("contenido inicial");
    expect(container.querySelector("button").getAttribute("aria-expanded")).toBe("true");
  });
});
