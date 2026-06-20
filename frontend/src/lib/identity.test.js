// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from "vitest";
import { getParticipantId, getIdentity, setIdentity, COLORS, pickColor, HEARTBEAT_MS } from "./identity";

describe("identity", () => {
  beforeEach(() => localStorage.clear());

  it("getParticipantId mints once and is stable", () => {
    const a = getParticipantId();
    const b = getParticipantId();
    expect(a).toBe(b);
    expect(a.length).toBeGreaterThanOrEqual(8);
  });

  it("getIdentity is null until set", () => {
    expect(getIdentity()).toBeNull();
  });

  it("setIdentity persists name+color; getIdentity returns them + participant_id", () => {
    setIdentity({ name: "Daniel", color: COLORS[0] });
    const id = getIdentity();
    expect(id.name).toBe("Daniel");
    expect(id.color).toBe(COLORS[0]);
    expect(id.participant_id).toBe(getParticipantId());
  });

  it("pickColor returns a palette color deterministically by seed", () => {
    expect(COLORS).toContain(pickColor("p1"));
    expect(pickColor("p1")).toBe(pickColor("p1"));
  });

  it("HEARTBEAT_MS is 15000", () => {
    expect(HEARTBEAT_MS).toBe(15000);
  });
});
