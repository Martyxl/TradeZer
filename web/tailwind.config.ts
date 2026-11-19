import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        up: {
          DEFAULT: "#22c55e",
          dim: "#14532d",
          glow: "rgba(34,197,94,0.4)",
        },
        neutral: {
          500: "#eab308",
          dim: "#713f12",
          glow: "rgba(234,179,8,0.4)",
        },
        down: {
          DEFAULT: "#ef4444",
          dim: "#7f1d1d",
          glow: "rgba(239,68,68,0.4)",
        },
        // Povrchy přes CSS proměnné: výchozí hodnoty = původní tmavý vzhled (landing, auth),
        // uvnitř aplikace (.tz-glass) je přepíše skleněný motiv. Viz globals.css.
        surface: "var(--tz-sunken)",
        card: "var(--tz-panel)",
        border: "var(--tz-line)",
        panel: { DEFAULT: "var(--tz-panel)", 2: "var(--tz-panel-2)" },
        sunken: "var(--tz-sunken)",
        raised: "var(--tz-raised)",
        line: { DEFAULT: "var(--tz-line)", 2: "var(--tz-line-2)" },
        mint: "var(--tz-mint)",
        gray: {
          50: "#f9fafb", 100: "#f3f4f6",
          200: "var(--tz-gray-200)", 300: "var(--tz-gray-300)", 400: "var(--tz-gray-400)",
          500: "var(--tz-gray-500)", 600: "var(--tz-gray-600)", 700: "var(--tz-gray-700)",
          800: "#1f2937", 900: "#111827", 950: "#030712",
        },
      },
      borderRadius: {
        xl: "var(--tz-r-xl)",
        "2xl": "var(--tz-r-2xl)",
      },
      animation: {
        glow: "glow 2s ease-in-out infinite alternate",
        "fade-in": "fadeIn 0.3s ease-in-out",
      },
      keyframes: {
        glow: {
          from: { boxShadow: "0 0 8px var(--glow-color)" },
          to: { boxShadow: "0 0 20px var(--glow-color), 0 0 40px var(--glow-color)" },
        },
        fadeIn: {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
