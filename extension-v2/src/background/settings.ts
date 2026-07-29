/**
 * 默认设置 & 存储 key
 */
import type { LumioSettings } from "../types";

export const DEFAULT_SETTINGS: LumioSettings = {
  apiBaseUrl: "http://127.0.0.1:38900",
  theme: "system",
};

const SETTINGS_KEY = "lumio_settings";

export async function getSettings(): Promise<LumioSettings> {
  const { [SETTINGS_KEY]: settings } = await chrome.storage.local.get(SETTINGS_KEY);
  return { ...DEFAULT_SETTINGS, ...settings };
}

export async function saveSettings(patch: Partial<LumioSettings>): Promise<LumioSettings> {
  const current = await getSettings();
  const next = { ...current, ...patch };
  await chrome.storage.local.set({ [SETTINGS_KEY]: next });
  // 广播给 popup（如果打开）
  chrome.runtime.sendMessage({ type: "settingsUpdated", settings: next }).catch(() => {});
  return next;
}

/** 监听设置变化（popup 用） */
export function onSettingsChanged(cb: (settings: LumioSettings) => void): () => void {
  const listener = (msg: unknown) => {
    if (
      typeof msg === "object" &&
      msg !== null &&
      (msg as { type?: string }).type === "settingsUpdated"
    ) {
      cb((msg as { settings: LumioSettings }).settings);
    }
  };
  chrome.runtime.onMessage.addListener(listener);
  return () => chrome.runtime.onMessage.removeListener(listener);
}
