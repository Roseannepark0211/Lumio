/**
 * PreviewPanel — 媒体预览面板
 *
 * 阶段 3：发送前确认面板
 * - 显示 thumbnail + title + author + platform badge
 * - 列出所有 media_items（视频/图片缩略图）
 * - 两个按钮：「确认发送」「取消」
 *
 * ★ 触发流程：
 * 1. popup 点「解析并发送」按钮
 * 2. extractPageMeta 拿到 PageMeta
 * 3. 弹出 PreviewPanel 等用户确认
 * 4. 用户点「确认发送」→ 调 /capture
 *
 * ★ 渲染：通过 React Portal 渲染到 document.body，
 *   彻底脱离 CaptureButton 的 flex 父级，避免布局被压缩
 */
import { useState } from "react";
import { createPortal } from "react-dom";
import type { PageMeta } from "../../types";
import { PLATFORM_LABELS_FULL as PLATFORM_LABELS } from "./platform-badge";

interface Props {
  meta: PageMeta;
  onConfirm: () => void;
  onCancel: () => void;
}

export function PreviewPanel({ meta, onConfirm, onCancel }: Props) {
  const [confirmed, setConfirmed] = useState(false);
  const mediaCount = meta.media_items?.length || 0;
  const videoCount = meta.media_items?.filter((m) => m.is_video).length || 0;
  const imageCount = mediaCount - videoCount;

  const handleConfirm = () => {
    setConfirmed(true);
    onConfirm();
  };

  // Portal 到 body，脱离 CaptureButton 的 flex 父级
  return createPortal(
    <>
      {/* 遮罩层 */}
      <div
        className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm animate-fade-in"
        onClick={onCancel}
      />
      {/* 面板层：占满整个 popup 视口 */}
      <div className="fixed inset-0 z-50 flex flex-col animate-slide-up">
        {/* 标题栏（固定） */}
        <div className="flex flex-shrink-0 items-center justify-between border-b border-text/10 bg-text/5 px-4 py-3">
          <span className="text-sm font-medium text-text">发送预览</span>
          <button
            className="rounded-full p-1 text-text-muted hover:bg-text/10 hover:text-text"
            onClick={onCancel}
            disabled={confirmed}
            aria-label="取消"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <path
                d="M6 6L18 18M6 18L18 6"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </div>

        {/* 中间内容区（滚动） */}
        <div className="min-h-0 flex-1 overflow-y-auto bg-surface px-4 py-3">
          {/* 主缩略图 + 信息 */}
          <div className="mb-3 flex gap-3">
            {meta.thumbnail && (
              <img
                src={meta.thumbnail}
                alt=""
                className="h-20 w-20 flex-shrink-0 rounded-lg object-cover"
                draggable={false}
              />
            )}
            <div className="min-w-0 flex-1">
              <div
                className="line-clamp-2 text-sm font-medium text-text"
                title={meta.title}
              >
                {meta.title || "(无标题)"}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-text-muted">
                {meta.author && <span>@{meta.author}</span>}
                {meta.platform && (
                  <span className="rounded-full bg-accent/15 px-2 py-0.5 text-accent">
                    {PLATFORM_LABELS[meta.platform] || meta.platform}
                  </span>
                )}
                {mediaCount > 0 && (
                  <span className="rounded-full bg-text/10 px-2 py-0.5">
                    {mediaCount} 项媒体
                    {videoCount > 0 && ` · ${videoCount} 视频`}
                    {imageCount > 0 && ` · ${imageCount} 图片`}
                  </span>
                )}
                {meta.duration && (
                  <span className="rounded-full bg-text/10 px-2 py-0.5">
                    {Math.floor(meta.duration / 60)}:
                    {(meta.duration % 60).toString().padStart(2, "0")}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* media_items 缩略图列表（最多 6 个） */}
          {mediaCount > 1 && (
            <div className="mb-3 flex flex-wrap gap-1.5">
              {meta.media_items!.slice(0, 6).map((item, idx) => (
                <div
                  key={idx}
                  className="relative h-14 w-14 overflow-hidden rounded-md bg-text/5"
                >
                  {item.is_video ? (
                    <div className="flex h-full w-full items-center justify-center bg-text/10">
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                        <path
                          d="M8 5v14l11-7z"
                          fill="currentColor"
                          className="text-accent"
                        />
                      </svg>
                    </div>
                  ) : (
                    <img
                      src={item.url}
                      alt=""
                      className="h-full w-full object-cover"
                      draggable={false}
                    />
                  )}
                </div>
              ))}
              {mediaCount > 6 && (
                <div className="flex h-14 w-14 items-center justify-center rounded-md bg-text/10 text-xs text-text-muted">
                  +{mediaCount - 6}
                </div>
              )}
            </div>
          )}

          {/* URL 来源 */}
          <div
            className="truncate rounded bg-text/5 px-2 py-1 text-[10px] text-text-dim"
            title={meta.url}
          >
            {meta.url}
          </div>
        </div>

        {/* 操作按钮（固定底部） */}
        <div className="flex flex-shrink-0 gap-2 border-t border-text/10 bg-surface p-4 pt-3">
          <button
            className="btn-secondary flex-1"
            onClick={onCancel}
            disabled={confirmed}
          >
            取消
          </button>
          <button
            className="btn-primary flex-1"
            onClick={handleConfirm}
            disabled={confirmed}
          >
            {confirmed ? "发送中..." : "确认发送"}
          </button>
        </div>
      </div>
    </>,
    document.body,
  );
}
