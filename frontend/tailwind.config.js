/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Lumio 主题色 — 用 CSS 变量驱动，深色/浅色各一套值（见 index.css）
        // 透明度通道用 rgb 通道引用：rgb(var(--color-bg) / <alpha-value>)
        bg: {
          DEFAULT: "rgb(var(--color-bg) / <alpha-value>)",
          surface: "rgb(var(--color-bg-surface) / <alpha-value>)",
          elevated: "rgb(var(--color-bg-elevated) / <alpha-value>)",
        },
        accent: {
          DEFAULT: "rgb(var(--color-accent) / <alpha-value>)",
          glow: "rgb(var(--color-accent-glow) / <alpha-value>)",
        },
        danger: "rgb(var(--color-danger) / <alpha-value>)",
        success: "rgb(var(--color-success) / <alpha-value>)",
        warning: "rgb(var(--color-warning) / <alpha-value>)",
        text: {
          DEFAULT: "rgb(var(--color-text) / <alpha-value>)",
          muted: "rgb(var(--color-text-muted) / <alpha-value>)",
          dim: "rgb(var(--color-text-dim) / <alpha-value>)",
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
