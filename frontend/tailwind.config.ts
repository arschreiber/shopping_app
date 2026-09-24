import type { Config } from "tailwindcss";

/**
 * Zurückhaltendes Werkzeug, kein Baukasten-Look: warme Neutraltöne, *eine* Akzentfarbe,
 * Haarlinien statt Schatten, engere Typo-Skala. Alles, was hier nicht steht, soll auch
 * nicht benutzt werden - so bleibt die Oberfläche über Monate ruhig.
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ground: "#faf9f7", // Seitenhintergrund
        surface: "#ffffff",
        sunken: "#f3f1ed", // leere Slots, Tabellenzebra
        ink: {
          DEFAULT: "#1c1a17",
          muted: "#6b6660",
          faint: "#9a948c",
        },
        line: {
          DEFAULT: "#e5e1db",
          strong: "#d3cec6",
        },
        accent: {
          DEFAULT: "#2f5d50", // tiefes Grün - Pins, Primäraktionen, Aktivzustand
          hover: "#264c42",
          soft: "#eaf1ee",
          line: "#bcd2ca",
        },
        warn: { DEFAULT: "#8a5a12", soft: "#fbf2e3", line: "#e8d5ae" },
        danger: { DEFAULT: "#9b3b2c", soft: "#fceeeb", line: "#eec7bf" },
        info: { DEFAULT: "#4a5568", soft: "#f1f3f6", line: "#d9dee7" },
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Inter",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.04em" }],
        xs: ["0.75rem", { lineHeight: "1.1rem" }],
        sm: ["0.8125rem", { lineHeight: "1.25rem" }],
        base: ["0.9375rem", { lineHeight: "1.5rem" }],
        lg: ["1.0625rem", { lineHeight: "1.6rem" }],
        xl: ["1.375rem", { lineHeight: "1.8rem", letterSpacing: "-0.01em" }],
        "2xl": ["1.75rem", { lineHeight: "2.1rem", letterSpacing: "-0.02em" }],
      },
      borderRadius: { DEFAULT: "6px", md: "8px", lg: "10px", xl: "14px" },
      boxShadow: {
        // Genau zwei Schatten: für Sheet und Popover. Karten bleiben flach.
        sheet: "0 -8px 32px -12px rgb(28 26 23 / 0.18)",
        pop: "0 8px 24px -12px rgb(28 26 23 / 0.22)",
      },
      transitionDuration: { fast: "120ms" },
    },
  },
  plugins: [],
} satisfies Config;
