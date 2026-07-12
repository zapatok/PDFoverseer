// @vitest-environment jsdom
//
// Smoke test for the ui/Popover primitive (§A3): a controlled Radix Popover
// wrapper with a minimal trigger+content API. Follows the DOM-mount pattern
// used across this project's component tests (react-dom/client + act, no
// testing-library).
import { describe, it, expect, vi, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot } from "react-dom/client";

import Popover from "./Popover";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// jsdom has no ResizeObserver; Radix's Popper positioning (used by Popover
// Content) touches it during layout — stub a no-op like other Radix-in-jsdom
// setups do.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

function mount(ui) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(ui));
  return { container, root, unmount: () => act(() => root.unmount()) };
}

afterEach(() => {
  document.body.innerHTML = "";
});

function Harness() {
  const [open, setOpen] = React.useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <Popover.Trigger>
        <button type="button">Abrir</button>
      </Popover.Trigger>
      <Popover.Content>
        <p>Contenido del popover</p>
        <input type="text" aria-label="campo" />
      </Popover.Content>
    </Popover>
  );
}

describe("ui/Popover — smoke", () => {
  it("closed: renders the trigger, no content in the document", () => {
    const { container } = mount(<Harness />);
    expect(container.querySelector("button").textContent).toBe("Abrir");
    expect(document.body.textContent).not.toContain("Contenido del popover");
  });

  it("opens on trigger click and portals its content to body (not under the trigger's container)", () => {
    const { container } = mount(<Harness />);
    const trigger = container.querySelector("button");
    act(() => trigger.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(document.body.textContent).toContain("Contenido del popover");
    // Portal: the content is NOT a descendant of the mount container.
    expect(container.textContent).not.toContain("Contenido del popover");
  });

  it("Escape closes the popover", () => {
    const { container } = mount(<Harness />);
    const trigger = container.querySelector("button");
    act(() => trigger.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(document.body.textContent).toContain("Contenido del popover");
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    expect(document.body.textContent).not.toContain("Contenido del popover");
  });
});
