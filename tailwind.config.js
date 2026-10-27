/**
 * Design tokens: a dark trading-terminal theme (slate darks, sky accent, emerald / amber / rose status colours).
 * Gradients stay simple: one hue, two stops. Tailwind scans the templates and scripts for class names; component
 * classes live in app/static/src/input.css.
 *
 * How the dark theme works without touching ~600 class names in the templates: every scale below runs from
 * "closest to the surface" (50) to "strongest contrast against it" (900-950), which is exactly what the numbers
 * meant in the old light theme. So `text-slate-700` is still "secondary text", `bg-green-50` is still "a faint
 * green tint", `border-red-700` is still "a strong red boundary", and `bg-white` is the card surface.
 * Every text pair was checked against WCAG 2.2 AA on the slate-900 surface (4.5:1 text, 3:1 UI boundaries).
 */
const scale = (values) => Object.fromEntries([50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950].map((k, i) => [k, values[i]]));

module.exports = {
  content: ["./app/templates/**/*.html", "./app/static/*.js"],
  theme: {
    extend: {
      colors: {
        white: "#0f172a",                                    // the card surface (slate-900)
        canvas: "#020617",                                   // page background (slate-950)
        accent: { DEFAULT: "#38bdf8", pressed: "#7dd3fc" },  // sky-400: 8.6:1 on the surface; text on it is dark
        //            50         100        200        300        400        500        600        700        800        900        950
        slate: scale(["#131d33", "#1a2540", "#243049", "#334155", "#64748b", "#8b9ab0", "#a3b1c6", "#cbd5e1", "#e2e8f0", "#f1f5f9", "#f8fafc"]),
        green: scale(["#0b2a24", "#0f3b30", "#065f46", "#047857", "#059669", "#10b981", "#22c58f", "#34d399", "#6ee7b7", "#a7f3d0", "#d1fae5"]),
        red: scale(["#2a1019", "#3b1424", "#881337", "#9f1239", "#be123c", "#e11d48", "#f43f5e", "#fb7185", "#fda4af", "#fecdd3", "#ffe4e6"]),
        amber: scale(["#2a1f0a", "#3a2a0b", "#78350f", "#92400e", "#b45309", "#d97706", "#f59e0b", "#fbbf24", "#fcd34d", "#fde68a", "#fef3c7"]),
        blue: scale(["#0c1e36", "#0f2a4a", "#0c4a6e", "#075985", "#0369a1", "#0284c7", "#0ea5e9", "#38bdf8", "#7dd3fc", "#bae6fd", "#e0f2fe"]),
      },
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", '"SF Pro Text"', '"Segoe UI"', "Roboto", '"Helvetica Neue"', "Arial", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 3px rgb(0 0 0 / 0.45), 0 0 0 1px rgb(30 41 59 / 0.9)",
        sheet: "0 -10px 40px rgb(0 0 0 / 0.6)",
      },
      transitionTimingFunction: { native: "cubic-bezier(0.2, 0.8, 0.2, 1)" },  // the "spring-ish" ease mobile apps use
    },
  },
  plugins: [],
};
