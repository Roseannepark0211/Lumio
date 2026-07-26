/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Lumio 主题色（与 Theme.qml 对齐）
        bg: {
          DEFAULT: "#0a0a0f",
          surface: "#13131a",
          elevated: "#1c1c26",
        },
        accent: {
          DEFAULT: "#a78bfa",
          glow: "#c4b5fd",
        },
        danger: "#ef4444",
        success: "#10b981",
        warning: "#f59e0b",
        text: {
          DEFAULT: "#e5e7eb",
          muted: "#9ca3af",
        },
      },
      fontFamily: {
        sans: ["Manrope", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      backdropBlur: {
        xs: "2px",
        lg: "40px",
        xl: "60px",
      },
      animation: {
        "fade-in": "fadeIn 200ms ease-out",
        "slide-up": "slideUp 250ms cubic-bezier(0.16, 1, 0.3, 1)",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(8px) scale(0.98)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
        },
      },
    },
  },
  plugins: [],
};
