/**
 * 顶部状态栏 — Logo + 连接状态点
 */
import { useConnectionStore } from "../store/connection";

export function StatusHeader() {
  const connected = useConnectionStore((s) => s.connected);

  return (
    <div className="flex items-center justify-between px-1 py-2 animate-fade-in">
      <div className="flex items-center gap-2">
        <img
          src={chrome.runtime.getURL("src/assets/icons/logo-48.png")}
          alt="Lumio"
          className="h-7 w-7 rounded-lg"
          draggable={false}
        />
        <div className="flex flex-col">
          <span className="text-sm font-semibold leading-tight">Lumio</span>
          <span className="text-[10px] text-text-dim leading-tight">
            {connected ? "已连接到桌面端" : "未连接"}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-1.5">
        <span
          className={`relative h-2.5 w-2.5 rounded-full transition-colors duration-300 ${
            connected ? "bg-success" : "bg-danger"
          }`}
        >
          {connected && (
            <span className="absolute inset-0 rounded-full bg-success animate-ping opacity-60" />
          )}
        </span>
        <span className="text-xs text-text-muted">
          {connected ? "在线" : "离线"}
        </span>
      </div>
    </div>
  );
}
