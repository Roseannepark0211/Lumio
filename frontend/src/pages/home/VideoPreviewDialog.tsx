/**
 * HomePage 子组件：视频预览对话框（X-Sou 视频缓存到本地后播放）。
 *
 * 与 QML 版 VideoPreviewDialog.qml 对齐：
 * - HTML5 <video> 标签 + 自带控制栏（controls）
 * - 用 lumio-file:// protocol 播放本地文件（Electron 主进程已注册）
 * - 模态对话框，点击遮罩关闭
 *
 * 与 QML 版差异：
 * - 不需要自己实现播放/暂停/进度条/音量控制（HTML5 controls 自带）
 * - 不需要 AudioOutput / MediaPlayer 复杂状态机
 */

import { useEffect, useRef, useState } from "react";
import { lumioFileUrl } from "../../api";

interface Props {
  /** 本地文件绝对路径（来自 WS preview_ready 事件 payload.path） */
  localPath: string | null;
  /** 错误信息（来自 WS preview_failed 事件） */
  error: string | null;
  onClose: () => void;
}

export function VideoPreviewDialog({ localPath, error, onClose }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [videoError, setVideoError] = useState<string | null>(null);

  // Esc 键关闭
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // localPath 变化时重置错误状态
  useEffect(() => {
    setVideoError(null);
  }, [localPath]);

  if (!localPath && !error) return null;

  const videoSrc = localPath ? lumioFileUrl(localPath) : "";
  console.log("[VideoPreviewDialog] videoSrc =", videoSrc, "localPath =", localPath);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm animate-fade-in"
      onClick={onClose}
    >
      <div
        className="relative flex items-center justify-center overflow-hidden rounded-2xl border border-white/10 bg-black shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        style={{ width: "80vw", height: "80vh" }}
      >
        {/* 关闭按钮 */}
        <button
          onClick={onClose}
          className="absolute right-3 top-3 z-10 flex h-8 w-8 items-center justify-center rounded-full bg-black/50 text-white/80 backdrop-blur-sm transition-colors hover:bg-black/70 hover:text-white"
          aria-label="关闭"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>

        {error ? (
          <div className="flex h-full w-full flex-col items-center justify-center gap-3 p-8 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-danger/15">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-6 w-6 text-danger">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            </div>
            <div className="text-sm font-medium text-danger">视频加载失败</div>
            <div className="text-xs text-text-muted">{error}</div>
          </div>
        ) : videoError ? (
          <div className="flex h-full w-full flex-col items-center justify-center gap-3 p-8 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-danger/15">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-6 w-6 text-danger">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            </div>
            <div className="text-sm font-medium text-danger">视频播放失败</div>
            <div className="max-w-md text-xs text-text-muted">{videoError}</div>
          </div>
        ) : (
          <video
            ref={videoRef}
            src={videoSrc}
            controls
            autoPlay
            className="h-full w-full object-contain"
            onError={(e) => {
              const v = e.currentTarget;
              const code = v.error?.code;
              const msg = v.error?.message;
              const codeMap: Record<number, string> = {
                1: "MEDIA_ERR_ABORTED",
                2: "MEDIA_ERR_NETWORK",
                3: "MEDIA_ERR_DECODE",
                4: "MEDIA_ERR_SRC_NOT_SUPPORTED",
              };
              const label = code ? codeMap[code] || `code ${code}` : "unknown";
              console.error("[VideoPreviewDialog] video error:", { code, message: msg, src: videoSrc });
              setVideoError(`${label}: ${msg || "无详细信息"} (src=${videoSrc})`);
            }}
            onLoadedData={() => console.log("[VideoPreviewDialog] video loaded OK")}
          />
        )}
      </div>
    </div>
  );
}
