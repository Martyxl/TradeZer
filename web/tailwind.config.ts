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
        surface: "#0f1117",
        card: "#1a1d27",
        border: "#2a2d3a",
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
