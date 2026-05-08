/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: {
          950: "#050b14",
          900: "#0a1628",
          800: "#0f2744",
          700: "#153a5c",
          600: "#1c4d75",
        },
        steel: {
          950: "#111827",
          900: "#1f2937",
          800: "#374151",
          700: "#4b5563",
          600: "#6b7280",
          500: "#9ca3af",
          400: "#d1d5db",
          300: "#e5e7eb",
          200: "#f3f4f6",
          100: "#f9fafb",
        },
        alert: {
          red: "#dc2626",
          orange: "#ea580c",
          amber: "#f59e0b",
        },
        plant: {
          accent: "#0e7490",
          glow: "#22d3ee",
        },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
      boxShadow: {
        panel: "0 4px 24px rgba(5, 11, 20, 0.45)",
        inset: "inset 0 1px 0 rgba(255,255,255,0.06)",
      },
      backgroundImage: {
        "grid-industrial":
          "linear-gradient(rgba(14,116,144,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(14,116,144,0.08) 1px, transparent 1px)",
      },
      backgroundSize: {
        grid: "32px 32px",
      },
      animation: {
        "scan-slow": "scan 14s linear infinite",
        "pulse-border": "pulseBorder 3s ease-in-out infinite",
      },
      keyframes: {
        scan: {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100%)" },
        },
        pulseBorder: {
          "0%, 100%": { opacity: "0.5" },
          "50%": { opacity: "1" },
        },
      },
    },
  },
  plugins: [],
};
