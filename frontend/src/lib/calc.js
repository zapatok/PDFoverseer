// Minimal arithmetic evaluator for the viewer calculator (triage I8).
// Grammar: expr := term (('+'|'-') term)* ; term := factor (('*'|'/') factor)* ;
// factor := number | '(' expr ')' | '-' factor. No eval(), ever.

export function evaluate(input) {
  const raw = String(input);
  // Digit-space-digit would become concatenation after the whitespace strip
  // ("2 3" → 23: a silent wrong value). Reject it up front. Legit spacing
  // ("12 + 3") survives: there the whitespace borders an operator, not two
  // digits, so \d\s+\d never matches.
  if (/\d\s+\d/.test(raw)) return null;
  const s = raw.replace(/\s+/g, "");
  if (!s) return null;
  let i = 0;

  function number() {
    const start = i;
    while (i < s.length && /[0-9.]/.test(s[i])) i++;
    if (start === i) return NaN;
    const n = Number(s.slice(start, i));
    return Number.isFinite(n) ? n : NaN;
  }

  function factor() {
    if (s[i] === "-") { i++; return -factor(); }
    if (s[i] === "(") {
      i++;
      const v = expr();
      if (s[i] !== ")") return NaN;
      i++;
      return v;
    }
    return number();
  }

  function term() {
    let v = factor();
    while (s[i] === "*" || s[i] === "/") {
      const op = s[i++];
      const r = factor();
      v = op === "*" ? v * r : v / r;
    }
    return v;
  }

  function expr() {
    let v = term();
    while (s[i] === "+" || s[i] === "-") {
      const op = s[i++];
      const r = term();
      v = op === "+" ? v + r : v - r;
    }
    return v;
  }

  // evaluate() runs inside CalcBar's render and the app has no ErrorBoundary:
  // an uncaught exception here (e.g. RangeError from pathologically nested
  // parens overflowing the recursion stack) would blank the whole viewer.
  // Any failure to evaluate is just "no result" — return null.
  let v;
  try {
    v = expr();
  } catch {
    return null;
  }
  if (i !== s.length || Number.isNaN(v) || !Number.isFinite(v)) return null;
  return v;
}
