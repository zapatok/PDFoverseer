import { describe, it, expect } from "vitest";
import { prerenderOrder, LruCache } from "./page-cache";

describe("prerenderOrder", () => {
  it("orders ±1 then ±2, clamped", () => {
    expect(prerenderOrder(5, 100)).toEqual([6, 4, 7, 3]);
  });
  it("clamps at the start", () => {
    expect(prerenderOrder(1, 100)).toEqual([2, 3]);
  });
  it("clamps at the end", () => {
    expect(prerenderOrder(100, 100)).toEqual([99, 98]);
  });
  it("single page → empty", () => {
    expect(prerenderOrder(1, 1)).toEqual([]);
  });
  it("radius param respected", () => {
    expect(prerenderOrder(5, 100, 1)).toEqual([6, 4]);
  });
});

describe("LruCache", () => {
  it("evicts least-recently-used beyond capacity, calling onEvict", () => {
    const evicted = [];
    const c = new LruCache(2, (v) => evicted.push(v));
    c.set("a", 1);
    c.set("b", 2);
    c.get("a"); // refresh a
    c.set("c", 3); // evicts b
    expect(c.get("b")).toBeUndefined();
    expect(c.get("a")).toBe(1);
    expect(evicted).toEqual([2]);
  });
  it("overwriting an existing key onEvicts the replaced value, not identical re-sets", () => {
    const evicted = [];
    const c = new LruCache(4, (v) => evicted.push(v));
    c.set("a", 1);
    c.set("a", 2); // replaces → old value must be evicted (ImageBitmap close())
    expect(evicted).toEqual([1]);
    c.set("a", 2); // identical value re-set → NOT evicted (still live)
    expect(evicted).toEqual([1]);
    expect(c.get("a")).toBe(2);
  });
  it("clear() evicts everything", () => {
    const evicted = [];
    const c = new LruCache(4, (v) => evicted.push(v));
    c.set("a", 1);
    c.set("b", 2);
    c.clear();
    expect(evicted.sort()).toEqual([1, 2]);
    expect(c.get("a")).toBeUndefined();
  });
});
