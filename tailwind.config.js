/**
 * Design tokens. Tailwind scans the templates and scripts for class names; component classes live in app/static/src/input.css.
 * Every colour pair used for text was checked against WCAG 2.2 AA (4.5:1 text, 3:1 UI boundaries and states).
 */
module.exports = {
  content: ["./app/templates/**/*.html", "./app/static/*.js"],
  theme: {
    extend: {
      colors: {
        canvas: "#f2f2f7",                                   // grouped-list background, as on iOS / React Native
        accent: { DEFAULT: "#1d4ed8", pressed: "#1e40af" },  // blue-700: 6.7:1 on white (iOS #007aff is only ~4:1)
      },
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", '"SF Pro Text"', '"Segoe UI"', "Roboto", '"Helvetica Neue"', "Arial", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 2px rgb(15 23 42 / 0.06), 0 1px 3px rgb(15 23 42 / 0.08)",
        sheet: "0 -10px 40px rgb(15 23 42 / 0.20)",
      },
      transitionTimingFunction: { native: "cubic-bezier(0.2, 0.8, 0.2, 1)" },  // the "spring-ish" ease mobile apps use
    },
  },
  plugins: [],
};
