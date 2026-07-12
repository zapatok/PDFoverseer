import { describe, it, expect } from "vitest";

import { REORG_SHORTCUTS } from "./reorg-shortcuts";

describe("REORG_SHORTCUTS", () => {
  const matches = new Set(REORG_SHORTCUTS.flatMap((s) => s.match));

  it("cubre cada tecla que el visor maneja en modo reorg", () => {
    const handled = ["[", "]", "Enter", "Escape"];
    for (const k of handled) expect(matches.has(k)).toBe(true);
  });

  it("cada entrada tiene chips (keys) y una acción", () => {
    for (const s of REORG_SHORTCUTS) {
      expect(Array.isArray(s.keys)).toBe(true);
      expect(s.keys.length).toBeGreaterThan(0);
      expect(typeof s.action).toBe("string");
    }
  });
});
