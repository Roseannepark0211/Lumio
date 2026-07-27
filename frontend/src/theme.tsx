/**
 * 前端主题 Provider — 与后端 /api/theme 对齐。
 *
 * 设计：
 *   - 启动时拉 /api/config 取当前 theme 字段
 *   - 监听 WS `theme_changed` 事件，自动切换主题
 *   - setTheme(theme) 调 api.setTheme → 后端发 theme_changed → 自动刷新
 *   - 通过在 <html> 上切换 `dark` class 驱动 Tailwind dark: 变体
 *   - 乐观更新：立即切换 class，不依赖 WS 事件延迟
 *
 * 用法：
 *   <ThemeProvider><App /></ThemeProvider>
 *   const { theme, setTheme, toggleTheme } = useTheme();
 *
 * 配色方案：
 *   - 深色（默认）：bg=#0a0a0f, surface=#13131a, text=#e5e7eb
 *   - 浅色：bg=#f5f5f7, surface=#ffffff, text=#1c1c26
 *   - accent / danger / success / warning 跨主题保持一致
 */
import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, subscribeEvents, type AppEvent } from "./api";

export type Theme = "light" | "dark";

interface ThemeContextValue {
  theme: Theme;
  ready: boolean;
  setTheme: (theme: Theme) => Promise<void>;
  toggleTheme: () => Promise<void>;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: "dark",
  ready: false,
  setTheme: async () => {},
  toggleTheme: async () => {},
});

export const useTheme = () => useContext(ThemeContext);

/** 在 <html> 上切换 dark class（Tailwind darkMode: 'class' 模式） */
function applyThemeClass(theme: Theme) {
  const root = document.documentElement;
  if (theme === "dark") {
    root.classList.add("dark");
    root.style.colorScheme = "dark";
  } else {
    root.classList.remove("dark");
    root.style.colorScheme = "light";
  }
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("dark");

  // 启动时拉当前主题
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const cfg = await api.getConfig();
        if (cancelled) return;
        const t = (cfg as { theme?: string }).theme;
        if (t === "light" || t === "dark") {
          setThemeState(t);
          applyThemeClass(t);
        } else {
          // 默认深色
          applyThemeClass("dark");
        }
      } catch {
        applyThemeClass("dark");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // 监听 theme_changed 事件
  useEffect(() => {
    const unsub = subscribeEvents((e: AppEvent) => {
      if (e.type === "theme_changed") {
        const t = (e.data as { theme?: string })?.theme;
        if (t === "light" || t === "dark") {
          setThemeState(t);
          applyThemeClass(t);
        }
      }
    });
    return unsub;
  }, []);

  const setTheme = useCallback(async (next: Theme) => {
    // 乐观更新：立即切换 class
    setThemeState(next);
    applyThemeClass(next);
    try {
      await api.setTheme(next);
      // 后端会发 theme_changed 事件，但 class 已经切换
    } catch {
      // 失败时静默 — 由调用方 toast
    }
  }, []);

  const toggleTheme = useCallback(async () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    await setTheme(next);
  }, [theme, setTheme]);

  const value: ThemeContextValue = {
    theme,
    ready: true, // 主题切换不需要等加载完成（有默认值）
    setTheme,
    toggleTheme,
  };

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
