/**
 * Lumio Popup 主入口
 *
 * 阶段 2：StatusHeader + CaptureButton（带元数据预览）+ HistoryList
 * 阶段 3：加 PreviewPanel（发送前确认）+ InboxSyncCard + 快捷键/Omnibox
 */
import { useEffect } from "react";
import { useConnectionStore } from "./store/connection";
import { StatusHeader } from "./components/StatusHeader";
import { CaptureButton } from "./components/CaptureButton";
import { SettingsGear } from "./components/SettingsGear";
import { HistoryList } from "./components/HistoryList";
import { InboxSyncCard } from "./components/InboxSyncCard";

export default function App() {
  const init = useConnectionStore((s) => s.init);

  useEffect(() => {
    init();
  }, [init]);

  return (
    <div className="relative flex h-[600px] flex-col p-4">
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

        {/* 阶段 3：Lumio 状态卡片（Inbox + 队列） */}
        <InboxSyncCard />

        {/* 历史记录 */}
        <HistoryList />
      </div>

      {/* 底部版本 */}
      <div className="mt-3 text-center">
        <span className="text-[10px] text-text-dim/60">
          Lumio Extension v4.4.0 · 阶段 3 · Ctrl+Shift+D 静默发送
        </span>
      </div>
    </div>
  );
}
