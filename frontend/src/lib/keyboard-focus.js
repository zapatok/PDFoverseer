/**
 * True when keyboard shortcuts must stay inert: an editable element has focus.
 *
 * `el.isContentEditable` is the spec-correct check, but jsdom (this project's
 * test environment) never implements it — it always reads back `undefined`
 * (jsdom/jsdom#1670) — so the raw `contenteditable` attribute is checked too.
 * That fallback is harmless in real browsers (isContentEditable already
 * covers it there) and is what makes the contentEditable case verifiable
 * under jsdom.
 */
export function focusIsInInput(el = document.activeElement) {
  if (!el) return false;
  if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") return true;
  if (el.isContentEditable) return true;
  const ce = el.getAttribute?.("contenteditable");
  return ce === "true" || ce === "";
}
