import { describe, it, expect } from "vitest";
import { participantsInCell, rosterParticipants, initials } from "./presence";

const ps = [
  { participant_id: "p1", name: "Daniel", color: "#a", focused_cell: "HRB|odi" },
  { participant_id: "p2", name: "Carla Soto", color: "#b", focused_cell: "HRB|odi" },
  { participant_id: "p3", name: "X", color: "#c", focused_cell: null },
];

it("participantsInCell filters by hospital|sigla, excluding self", () => {
  expect(participantsInCell(ps, "HRB", "odi", "p1").map((p) => p.participant_id)).toEqual(["p2"]);
});
it("participantsInCell returns [] for an empty/absent list", () => {
  expect(participantsInCell(undefined, "HRB", "odi", "p1")).toEqual([]);
});
it("participantsInCell excludes participants focused elsewhere or nowhere", () => {
  expect(participantsInCell(ps, "HLL", "art", "p1")).toEqual([]);
});
it("rosterParticipants returns everyone (incl. self)", () => {
  expect(rosterParticipants(ps).length).toBe(3);
});
it("rosterParticipants on undefined returns []", () => {
  expect(rosterParticipants(undefined)).toEqual([]);
});
it("initials: up to two words, uppercased; fallback for empty", () => {
  expect(initials("Carla Soto")).toBe("CS");
  expect(initials("Daniel")).toBe("D");
  expect(initials("")).toBe("?");
  expect(initials(undefined)).toBe("?");
});
