/** Participant identity stored in localStorage for multiplayer presence (M2). */

export const HEARTBEAT_MS = 15000;

/** Visually distinct hex colors for participant avatars. */
export const COLORS = [
  "#ef4444", // red
  "#f59e0b", // amber
  "#10b981", // jade/emerald
  "#3b82f6", // blue
  "#8b5cf6", // violet
  "#ec4899", // pink
];

const KEY_ID = "po_participant_id";
const KEY_IDENTITY = "po_identity";

/**
 * Returns the stable participant UUID for this browser.
 * Mints one on first call and persists it to localStorage.
 */
export function getParticipantId() {
  let id = localStorage.getItem(KEY_ID);
  if (!id) {
    id =
      typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
        ? crypto.randomUUID()
        : `p_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    localStorage.setItem(KEY_ID, id);
  }
  return id;
}

/**
 * Returns the stored identity or null if not yet set.
 * Shape: { participant_id, name, color }
 */
export function getIdentity() {
  const raw = localStorage.getItem(KEY_IDENTITY);
  if (!raw) return null;
  try {
    const { name, color } = JSON.parse(raw);
    if (!name || !color) return null;
    return { participant_id: getParticipantId(), name, color };
  } catch {
    return null;
  }
}

/**
 * Persists name and color to localStorage.
 * @param {{ name: string, color: string }} identity
 */
export function setIdentity({ name, color }) {
  localStorage.setItem(KEY_IDENTITY, JSON.stringify({ name, color }));
}

/**
 * Deterministically picks a color from COLORS by hashing `seed`.
 * Same seed always returns the same color.
 * @param {string} seed
 * @returns {string}
 */
export function pickColor(seed) {
  const str = String(seed ?? "");
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash += str.charCodeAt(i);
  }
  return COLORS[hash % COLORS.length];
}
