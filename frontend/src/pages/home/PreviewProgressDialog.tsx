/**
 * HomePage 子组件：X-Sou 视频预览下载进度对话框。
 *
 * 与 QML 版 _previewProgressDialog（HomePage.qml line 1467-1519）对齐：
 * - 显示已下载字节 / 总字节
 * - 进度条（百分比）
 * - 取消按钮（调 /api/preview-cancel）
 *
 * 触发时机：用户点击 X-Sou 搜索结果"预览"按钮
 * 关闭时机：preview_ready（成功）/ preview_failed（失败/取消）
 */

import { type PreviewProgressPayload } from "../../api";

interface Props {
  open: boolean;
  progress: PreviewProgressPayload | null;
  onCancel: () => void;
}

export function PreviewProgressDialog({ open, progress, onCancel }: Props) {
  if (!open) return null;

  const downloaded = progress?.downloaded ?? 0;
  const total = progress?.total ?? 0;
  const percent = total > 0 ? Math.min(100, (downloaded / total) * 100) : 0;

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 backdrop-blur-sm animate-fade-in">
      <div className="w-80 rounded-2xl border border-white/10 bg-bg-surface p-5 shadow-2xl">
        <div className="mb-3 text-sm font-medium text-text">缓存视频到本地...</div>

        {/* 进度条 */}
        <div className="h-1.5 overflow-hidden rounded-full bg-white/5">
          <div
            className="h-full bg-accent transition-all duration-200"
            style={{ width: `${percent}%` }}
          />
        </div>

        {/* 字节数 */}
        <div className="mt-2 flex justify-between font-mono text-xs text-text-muted">
          <span>{formatBytes(downloaded)}</span>
          <span>{total > 0 ? formatBytes(total) : '?'}</span>
        </div>

        {/* 取消按钮 */}
        <button
          onClick={onCancel}
          className="mt-4 w-full rounded-lg bg-white/5 py-2 text-sm text-text-muted transition-colors hover:bg-white/10 hover:text-text"
        >
          取消
        </button>
      </div>
    </div>
  );
}

function formatBytes(b: number): string {
  if (!b) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(b) / Math.log(1024));
  return `${(b / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}
