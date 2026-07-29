/**
 * 设置齿轮 — 点击展开 API 地址 + 主题切换
 *
 * 不做独立 tab，浮层形式展开，符合"极简设置"取向
 */
import { useState } from "react";
import { useConnectionStore, applyTheme } from "../store/connection";
import type { LumioSettings } from "../../types";

export function SettingsGear() {
  const { settings, settingsOpen, setSettingsOpen, updateSettings } = useConnectionStore();
  const [apiInput, setApiInput] = useState(settings.apiBaseUrl);

  const handleSaveApi = async () => {
    const trimmed = apiInput.trim().replace(/\/$/, "");
    if (trimmed && trimmed !== settings.apiBaseUrl) {
      await updateSettings({ apiBaseUrl: trimmed });
    }
  };

  const handleThemeChange = async (theme: LumioSettings["theme"]) => {
    applyTheme(theme);
    await updateSettings({ theme });
  };

  return (
    <>
      {/* 触发按钮 */}
      <button
        className="btn-ghost flex items-center gap-1"
        onClick={() => setSettingsOpen(!settingsOpen)}
        aria-label="设置"
      >
        <svg
          className={`h-3.5 w-3.5 transition-transform duration-300 ${
            settingsOpen ? "rotate-90" : ""
          }`}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      </button>

      {/* 浮层 */}
      {settingsOpen && (
        <div
          className="fixed inset-0 z-40 flex items-end animate-fade-in"
          onClick={() => setSettingsOpen(false)}
        >
          <div
            className="glass-card mx-3 mb-3 w-[calc(100%-24px)] animate-slide-up p-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                设置
              </span>
              <button
                className="btn-ghost text-text-dim"
                onClick={() => setSettingsOpen(false)}
              >
                ✕
              </button>
            </div>

            {/* API 地址 */}
            <div className="mb-3">
              <label className="mb-1 block text-[11px] text-text-muted">
                Lumio 连接地址（Flask 固定端口）
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  className="input flex-1"
                  value={apiInput}
                  onChange={(e) => setApiInput(e.target.value)}
                  placeholder="http://127.0.0.1:38900"
                  spellCheck={false}
                />
                <button className="btn-primary !w-auto px-3 py-2" onClick={handleSaveApi}>
                  保存
                </button>
              </div>
              <p className="mt-1 text-[10px] text-text-dim">
                默认 38900。此端口为 Flask 服务端口（/health /capture /stats），
                与 LumioAPI 随机端口（38910-38999）无关，仅在端口冲突时才需修改。
              </p>
            </div>

            {/* 主题 */}
            <div className="mb-3">
              <label className="mb-1 block text-[11px] text-text-muted">主题</label>
              <div className="grid grid-cols-3 gap-2">
                {(["system", "light", "dark"] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => handleThemeChange(t)}
                    className={`rounded-lg px-2 py-1.5 text-xs transition-all ${
                      settings.theme === t
                        ? "bg-accent text-white shadow-md shadow-accent/30"
                        : "bg-text/5 text-text-muted hover:bg-text/10"
                    }`}
                  >
                    {t === "system" ? "跟随系统" : t === "light" ? "浅色" : "深色"}
                  </button>
                ))}
              </div>
            </div>

            {/* 快捷键配置 */}
            <div>
              <label className="mb-1 block text-[11px] text-text-muted">快捷键</label>
              <div className="space-y-1.5">
                <div className="flex items-center justify-between rounded-lg bg-text/5 px-2.5 py-1.5">
                  <div className="min-w-0 flex-1">
                    <div className="text-xs text-text">打开 Lumio</div>
                    <div className="truncate text-[10px] text-text-dim">Ctrl+Shift+L</div>
                  </div>
                  <kbd className="rounded bg-text/10 px-1.5 py-0.5 text-[10px] text-text-muted">
                    Ctrl+Shift+L
                  </kbd>
                </div>
                <div className="flex items-center justify-between rounded-lg bg-text/5 px-2.5 py-1.5">
                  <div className="min-w-0 flex-1">
                    <div className="text-xs text-text">静默发送当前页</div>
                    <div className="truncate text-[10px] text-text-dim">Ctrl+Shift+D</div>
                  </div>
                  <kbd className="rounded bg-text/10 px-1.5 py-0.5 text-[10px] text-text-muted">
                    Ctrl+Shift+D
                  </kbd>
                </div>
                <button
                  className="btn-ghost mt-1 w-full !justify-start text-[11px]"
                  onClick={() =>
                    chrome.tabs.create({ url: "chrome://extensions/shortcuts" })
                  }
                >
                  <span className="flex items-center justify-center gap-1.5">
                    <svg
                      className="h-3 w-3"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                      <polyline points="15 3 21 3 21 9" />
                      <line x1="10" y1="14" x2="21" y2="3" />
                    </svg>
                    自定义快捷键（打开 Chrome 配置页）
                  </span>
                </button>
                <p className="mt-1 text-[10px] text-text-dim">
                  Chrome 不允许扩展直接修改快捷键，需在系统页面配置
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
