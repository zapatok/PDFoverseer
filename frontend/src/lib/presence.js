/** Pure presence selectors for multiplayer M2. No side effects. */

/**
 * Returns participants currently focused on the given cell, excluding self.
 * @param {Array|undefined} participants - List from the presence registry.
 * @param {string} hospital
 * @param {string} sigla
 * @param {string} selfId - participant_id to exclude.
 * @returns {Array}
 */
export function participantsInCell(participants, hospital, sigla, selfId) {
  return (participants ?? []).filter(
    (p) =>
      p.focused_cell === `${hospital}|${sigla}` &&
      p.participant_id !== selfId
  );
}

/**
 * Returns all participants (including self) as a stable array.
 * @param {Array|undefined} participants
 * @returns {Array}
 */
export function rosterParticipants(participants) {
  return participants ?? [];
}

/**
 * Derives display initials from a participant name.
 * Takes the first letter of up to the first two whitespace-separated words, uppercased.
 * Returns "?" for empty or undefined input.
 * @param {string|undefined} name
 * @returns {string}
 */
export function initials(name) {
  if (!name) return "?";
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  return words
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("");
}
