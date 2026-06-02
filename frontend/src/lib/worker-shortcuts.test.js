import { describe, it, expect } from "vitest";

import { WORKER_SHORTCUTS } from "./worker-shortcuts";

describe("WORKER_SHORTCUTS", () => {
  const matches = new Set(WORKER_SHORTCUTS.flatMap((s) => s.match));

  it("cubre cada tecla que el visor maneja", () => {
    const handled = ["PageDown", "PageUp", "Delete", "e", "E", "m", "M", "Backspace", "+", "=", "-", "_", "0", "5", "9"];
    for (const k of handled) expect(matches.has(k)).toBe(true);
  });

  it("cada entrada tiene chips (keys) y una acción", () => {
    for (const s of WORKER_SHORTCUTS) {
      expect(Array.isArray(s.keys)).toBe(true);
      expect(s.keys.length).toBeGreaterThan(0);
      expect(typeof s.action).toBe("string");
    }
  });
});
