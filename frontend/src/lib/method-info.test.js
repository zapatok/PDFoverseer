import { describe, expect, it } from "vitest";

import { METHOD_INFO } from "./method-info";
import { METHOD_LABEL } from "./method-labels";

describe("METHOD_INFO", () => {
  it("has an explanation for every labelled method", () => {
    for (const token of Object.keys(METHOD_LABEL)) {
      expect(typeof METHOD_INFO[token]).toBe("string");
      expect(METHOD_INFO[token].length).toBeGreaterThan(0);
    }
  });
});
