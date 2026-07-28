/**
 * Lumio Popup 主入口
 *
 * 阶段 1：StatusHeader + CaptureButton + 占位
 * 阶段 2：加 HistoryList（缩略图 + 多选 + 重发）
 * 阶段 3：加 PreviewPanel + InboxSyncCard
 */
import { useEffect } from "react";
import { useConnectionStore } from "./store/connection";
import { StatusHeader } from "./components/StatusHeader";
import { CaptureButton } from "./components/CaptureButton";
import { SettingsGear } from "./components/SettingsGear";

export default function App() {
  const init = useConnectionStore((s) => s.init);

  useEffect(() => {
    init();
  }, [init]);

  return (
    <div className="relative flex min-h-[480px] flex-col p-4">
      {/* 顶部状态栏 + 设置齿轮 */}
      <div className="flex items-center justify-between">
        <StatusHeader />
        <SettingsGear />
      </div>

      {/* 主区域 */}
      <div className="mt-4 flex flex-1 flex-col gap-3">
        <div className="glass-card p-3">
          <CaptureButton />
        </div>

        {/* 阶段 2 占位：历史记录 */}
        <div className="glass-card flex-1 p-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wide text-text-muted">
              最近发送
            </span>
            <span className="rounded-full bg-text/5 px-2 py-0.5 text-[10px] text-text-dim">
              阶段 2 上线
            </span>
          </div>
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <div className="mb-2 h-10 w-10 rounded-full bg-text/5" />
            <p className="text-xs text-text-dim">历史记录与缩略图预览</p>
            <p className="mt-1 text-[10px] text-text-dim/60">
              阶段 2 实现：IndexedDB 存储 + 平台 badge + 多选重发
            </p>
          </div>
        </div>

        {/* 阶段 3 占位：Inbox 同步 */}
        <div className="glass-card p-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-text-muted">Inbox 状态</span>
            <span className="rounded-full bg-text/5 px-2 py-0.5 text-[10px] text-text-dim">
              阶段 3 上线
            </span>
          </div>
        </div>
      </div>

      {/* 底部版本 */}
      <div className="mt-3 text-center">
        <span className="text-[10px] text-text-dim/60">
          Lumio Extension v4.4.0 · 阶段 1/3
        </span>
      </div>
    </div>
  );
}
