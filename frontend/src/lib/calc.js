// Minimal arithmetic evaluator for the viewer calculator (triage I8).
// Grammar: expr := term (('+'|'-') term)* ; term := factor (('*'|'/') factor)* ;
// factor := number | '(' expr ')' | '-' factor. No eval(), ever.

export function evaluate(input) {
  const s = String(input).replace(/\s+/g, "");
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

  const v = expr();
  if (i !== s.length || Number.isNaN(v) || !Number.isFinite(v)) return null;
  return v;
}
