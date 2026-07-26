/**
 * 页面级开关 — 单页迁移的 L3 回滚防线（AGENTS.md L3）。
 *
 * 每迁移一个页面在此维护开关。Electron 启动时按开关决定加载 React 页面
 * 还是 fallback 到 QML 版本。单页出问题不影响其他页面。
 *
 * 开关值从两处读取（按优先级）：
 *   1. localStorage（用户可手动覆盖，用于调试）
 *   2. 默认值（DEFAULTS）— 仅在迁移完成且验证通过后才改为 true
 *
 * 迁移流程：
 *   - 开发中：USE_REACT_HOME = false（默认）→ 启用开关后改为 true 测试
 *   - 验证通过：DEFAULTS.USE_REACT_HOME = true → 合并到 main
 *   - 出问题：localStorage 设为 false，或 DEFAULTS 改回 false 回滚
 */

export interface PageSwitches {
  /** Home 页面是否用 React（false = 用 QML HomePage.qml） */
  USE_REACT_HOME: boolean;
  // 后续迁移时新增：
  // USE_REACT_DOWNLOADS: boolean;
  // USE_REACT_HISTORY: boolean;
  // USE_REACT_LIBRARY: boolean;
  // USE_REACT_INBOX: boolean;
  // USE_REACT_STATS: boolean;
  // USE_REACT_NOTIFICATIONS: boolean;
  // USE_REACT_SETTINGS: boolean;
}

/** 默认开关值 — 仅在迁移完成且验证通过后才改为 true */
export const DEFAULTS: PageSwitches = {
  USE_REACT_HOME: false,  // Home 页面正在迁移中，默认 false
};

const STORAGE_KEY = "lumio_page_switches";

/** 读取单个开关值（localStorage 优先，否则用 DEFAULTS） */
export function getPageSwitch<K extends keyof PageSwitches>(key: K): boolean {
  try {
    const raw = typeof localStorage !== "undefined" ? localStorage.getItem(STORAGE_KEY) : null;
    if (raw) {
      const obj = JSON.parse(raw) as Partial<PageSwitches>;
      if (typeof obj[key] === "boolean") return obj[key] as boolean;
    }
  } catch {
    // ignore parse error
  }
  return DEFAULTS[key];
}

/** 读取所有开关值 */
export function getAllPageSwitches(): PageSwitches {
  const result = { ...DEFAULTS };
  try {
    const raw = typeof localStorage !== "undefined" ? localStorage.getItem(STORAGE_KEY) : null;
    if (raw) {
      const obj = JSON.parse(raw) as Partial<PageSwitches>;
      Object.assign(result, obj);
    }
  } catch {
    // ignore
  }
  return result;
}

/** 设置单个开关值（持久化到 localStorage） */
export function setPageSwitch<K extends keyof PageSwitches>(key: K, value: boolean): void {
  const all = getAllPageSwitches();
  all[key] = value;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
  } catch {
    // ignore
  }
}
