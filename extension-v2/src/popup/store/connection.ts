/**
 * 连接 + 设置状态管理（Zustand）
 */
import { create } from "zustand";
import type { LumioSettings } from "../../types";
import { DEFAULT_SETTINGS, onSettingsChanged } from "../../background/settings";

interface ConnectionState {
  connected: boolean;
  settings: LumioSettings;
  settingsOpen: boolean;

  setSettingsOpen: (open: boolean) => void;
  updateSettings: (patch: Partial<LumioSettings>) => Promise<void>;
  init: () => Promise<void>;
}

export const useConnectionStore = create<ConnectionState>((set) => ({
  connected: false,
  settings: DEFAULT_SETTINGS,
  settingsOpen: false,

  setSettingsOpen: (settingsOpen) => set({ settingsOpen }),

  updateSettings: async (patch) => {
    const next = (await chrome.runtime.sendMessage({
      type: "setSettings",
      settings: patch,
    })) as LumioSettings;
    set({ settings: next });
  },

  init: async () => {
    // 拉取连接状态
    const status = (await chrome.runtime.sendMessage({ type: "getStatus" })) as {
      connected: boolean;
    };
    if (status) set({ connected: status.connected });

    // 拉取设置
    const settings = (await chrome.runtime.sendMessage({
      type: "getSettings",
    })) as LumioSettings;
    if (settings) set({ settings });

    // 监听连接状态广播
    chrome.runtime.onMessage.addListener((msg) => {
      if (
        typeof msg === "object" &&
        msg !== null &&
        (msg as { type?: string }).type === "status"
      ) {
        set({ connected: (msg as { connected: boolean }).connected });
      }
    });

    // 监听设置变更
    onSettingsChanged((settings) => set({ settings }));

    // 应用主题
    applyTheme(settings?.theme ?? DEFAULT_SETTINGS.theme);
  },
}));

/** 应用主题到 <html> */
export function applyTheme(theme: LumioSettings["theme"]) {
  const root = document.documentElement;
  root.classList.remove("dark", "light");

  if (theme === "dark") {
    root.classList.add("dark");
  } else if (theme === "light") {
    root.classList.add("light");
  } else {
    // system：跟随 prefers-color-scheme
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    if (prefersDark) root.classList.add("dark");
  }
}
