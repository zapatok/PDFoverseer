// Trackpads fire many small wheel deltas; accumulate until a threshold so one
// gesture = one page, not five. Returns { step: -1|0|1, acc: carryover }.
export const WHEEL_PAGE_THRESHOLD = 120;

export function wheelToPageStep(deltaY, acc) {
  const next = acc + deltaY;
  if (next >= WHEEL_PAGE_THRESHOLD) return { step: 1, acc: 0 };
  if (next <= -WHEEL_PAGE_THRESHOLD) return { step: -1, acc: 0 };
  return { step: 0, acc: next };
}
