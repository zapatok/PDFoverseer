// Viewer page cache (spec §1): pre-render window + bounded LRU.
// Pure/pdfjs-free so it is unit-testable; PdfPage owns the pdfjs wiring.

/**
 * Pages to pre-render around the current one: ±1 first, then ±2 … ±radius,
 * clamped to [1, pageCount], current excluded.
 *
 * @param {number} current - 1-based current page.
 * @param {number} pageCount
 * @param {number} [radius] - window half-width (default 2).
 * @returns {number[]} pages in priority order.
 */
export function prerenderOrder(current, pageCount, radius = 2) {
  const order = [];
  for (let d = 1; d <= radius; d++) {
    if (current + d <= pageCount) order.push(current + d);
    if (current - d >= 1) order.push(current - d);
  }
  return order;
}

/** Tiny LRU keyed by string; onEvict lets callers close() ImageBitmaps. */
export class LruCache {
  constructor(capacity, onEvict = null) {
    this.capacity = capacity;
    this.onEvict = onEvict;
    this.map = new Map(); // Map preserves insertion order → LRU via delete+set
  }

  get(key) {
    if (!this.map.has(key)) return undefined;
    const v = this.map.get(key);
    this.map.delete(key);
    this.map.set(key, v);
    return v;
  }

  set(key, value) {
    if (this.map.has(key)) {
      const old = this.map.get(key);
      this.map.delete(key);
      // Overwrite drops the old value — onEvict it (close() the ImageBitmap)
      // unless the caller re-set the very same object, which stays live.
      if (old !== value) this.onEvict?.(old);
    }
    this.map.set(key, value);
    if (this.map.size > this.capacity) {
      const [oldestKey, oldestVal] = this.map.entries().next().value;
      this.map.delete(oldestKey);
      this.onEvict?.(oldestVal);
    }
  }

  clear() {
    for (const v of this.map.values()) this.onEvict?.(v);
    this.map.clear();
  }
}
