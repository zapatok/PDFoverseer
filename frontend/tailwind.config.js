/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Canvas
        "po-bg":            "var(--slate-1)",
        "po-panel":         "var(--slate-2)",
        "po-panel-hover":   "var(--slate-3)",
        "po-border":        "var(--slate-6)",
        "po-border-strong": "var(--slate-7)",

        // Text
        "po-text":         "var(--slate-12)",
        "po-text-muted":   "var(--slate-11)",
        "po-text-subtle":  "var(--slate-10)",

        // Semantic state foregrounds (text in pills)
        "po-confidence-high":   "var(--jade-11)",
        "po-confidence-low":    "var(--amber-11)",
        "po-suspect":           "var(--amber-11)",
        "po-error":             "var(--ruby-11)",
        "po-scanning":          "var(--indigo-11)",
        "po-override":          "var(--iris-11)",
        "po-success":           "var(--jade-11)",

        // Semantic state backgrounds (subtle fills for pills) — use the
        // ALPHA scales (step 3) so they composite correctly over any
        // panel/canvas background. NEVER use Tailwind's /opacity modifier
        // on the `po-*` tokens — those resolve to hex via CSS var and
        // Tailwind can't inject an alpha channel.
        "po-confidence-high-bg":  "var(--jade-a3)",
        "po-confidence-low-bg":   "var(--amber-a3)",
        "po-suspect-bg":          "var(--amber-a3)",
        "po-error-bg":            "var(--ruby-a3)",
        "po-scanning-bg":         "var(--indigo-a3)",
        "po-override-bg":         "var(--iris-a3)",

        // Semantic state borders (step 7 alpha for the pill outlines)
        "po-confidence-high-border": "var(--jade-a7)",
        "po-confidence-low-border":  "var(--amber-a7)",
        "po-suspect-border":         "var(--amber-a7)",
        "po-error-border":           "var(--ruby-a7)",
        "po-scanning-border":        "var(--indigo-a7)",
        "po-override-border":        "var(--iris-a7)",

        // Dot solids (step 9 of base scale — the canonical solid)
        "po-dot-high":     "var(--jade-9)",
        "po-dot-low":      "var(--amber-9)",
        "po-dot-suspect":  "var(--amber-9)",
        "po-dot-error":    "var(--ruby-9)",
        "po-dot-scanning": "var(--indigo-9)",
        "po-dot-override": "var(--iris-9)",

        // Accent (primary CTA)
        "po-accent":       "var(--indigo-9)",
        "po-accent-hover": "var(--indigo-10)",
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', '"Segoe UI"', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', '"Cascadia Code"', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
};
