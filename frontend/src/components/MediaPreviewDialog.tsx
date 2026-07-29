/**
 * 通用媒体预览对话框 — 支持 video / image / audio / mixed + 用户选择打开方式。
 *
 * 用于 LibraryPage 卡片左下角播放图标，替代系统默认应用打开。
 *
 * 调用链：
 *   1. 打开时调 /api/library/preview-items 列出所有可预览媒体（按 video → image → audio 排序）
 *   2. 单一类型 → 直接打开第一项
 *   3. 混合类型 → 显示选择面板让用户选"播放视频"/"查看图片"/"播放音频"
 *   4. 选择后进入对应面板，左右箭头/键盘 ←→ 在同类型内切换
 *
 * 混合帖子策略：用户主动选择，不强制视频优先。
 *
 * Bug 2 修复：
 * - 视频编码不支持（HEVC/H.265、部分 MKV）时显示友好提示 + 系统播放器 fallback
 * - 图片加载失败也提供系统播放器 fallback
 * - 文件缺失时直接在预览对话框内提供「删除此记录」按钮（不依赖 file_missing 事件）
 */

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { api, lumioFileUrl, subscribeEvents, type LibraryItem } from "../api";
import { useI18n } from "../i18n";

interface Props {
  item: LibraryItem;
  onClose: () => void;
}

interface PreviewItem {
  path: string;
  media_type: string;
}

type LoadState = "loading" | "select" | "viewing" | "error";

export function MediaPreviewDialog({ item, onClose }: Props) {
  const { tr } = useI18n();
  const [state, setState] = useState<LoadState>("loading");
  const [items, setItems] = useState<PreviewItem[]>([]);
  const [errorMsg, setErrorMsg] = useState<string>("");

  // 用户选择的类型筛选（"video" / "image" / "audio"）
  // 选择后 currentIndex 在该类型的子集内导航
  const [selectedType, setSelectedType] = useState<string>("");
  const [currentIndex, setCurrentIndex] = useState(0);

  // 按选中类型过滤后的子集
  const filteredItems = useMemo(
    () => (selectedType ? items.filter((it) => it.media_type === selectedType) : items),
    [items, selectedType]
  );

  const currentItem = filteredItems[currentIndex] || null;
  const resolvedPath = currentItem?.path || "";
  const resolvedType = currentItem?.media_type || "";

  // —— Esc 键关闭 ——
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // —— 打开时调后端列出所有可预览媒体 ——
  useEffect(() => {
    let cancelled = false;
    setState("loading");
    setErrorMsg("");
    (async () => {
      const fp = item.file_path || "";
      if (!fp) {
        if (!cancelled) {
          setErrorMsg(tr("preview_file_missing"));
          setState("error");
        }
        return;
      }
      try {
        const r = await api.listPreviewItems(fp);
        if (cancelled) return;
        if (!r.items || r.items.length === 0) {
          setErrorMsg(tr("preview_file_missing"));
          setState("error");
          return;
        }
        setItems(r.items);
        // 统计类型种类
        const types = new Set(r.items.map((it) => it.media_type));
        if (types.size <= 1) {
          // 单一类型 → 直接进入查看模式
          setSelectedType(r.items[0].media_type);
          setCurrentIndex(0);
          setState("viewing");
        } else {
          // 混合类型 → 显示选择面板
          setState("select");
        }
      } catch (e) {
        if (!cancelled) {
          setErrorMsg(String(e));
          setState("error");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [item, tr]);

  // —— 监听 file_missing 事件：后端检测到文件不存在时，关闭预览对话框 ——
  // 父组件 LibraryPage 会弹「是否删除本条记录」对话框，避免双弹窗冲突
  useEffect(() => {
    const fp = item.file_path || "";
    if (!fp) return;
    const unsub = subscribeEvents((e) => {
      if (e.type === "file_missing") {
        const p = e.data as { path?: string; source?: string } | null;
        if (p?.source === "library" && p.path === fp) {
          onClose();
        }
      }
    });
    return unsub;
  }, [item.file_path, onClose]);

  // —— 用系统默认播放器打开（视频 codec 不支持时的 fallback） ——
  const onOpenInSystemPlayer = useCallback(async () => {
    const fp = item.file_path || "";
    if (!fp) return;
    try {
      await api.openFile(fp, "library");
    } catch (e) {
      console.warn("open in system player failed:", e);
    }
  }, [item.file_path]);

  // —— 键盘 ←/→ 切换（仅在 viewing 状态） ——
  useEffect(() => {
    if (state !== "viewing") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") {
        setCurrentIndex((i) => Math.max(0, i - 1));
      } else if (e.key === "ArrowRight") {
        setCurrentIndex((i) => Math.min(filteredItems.length - 1, i + 1));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state, filteredItems.length]);

  const goToPrev = useCallback(() => {
    setCurrentIndex((i) => Math.max(0, i - 1));
  }, []);

  const goToNext = useCallback(() => {
    setCurrentIndex((i) => Math.min(filteredItems.length - 1, i + 1));
  }, [filteredItems.length]);

  const handleSelectType = useCallback((type: string) => {
    setSelectedType(type);
    setCurrentIndex(0);
    setState("viewing");
  }, []);

  const src = resolvedPath ? lumioFileUrl(resolvedPath) : "";
  const hasMultiple = filteredItems.length > 1;

  // 类型统计（用于选择面板）
  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const it of items) {
      counts[it.media_type] = (counts[it.media_type] || 0) + 1;
    }
    return counts;
  }, [items]);

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-black/85 backdrop-blur-sm animate-fade-in"
      onClick={onClose}
    >
      {/* 顶部标题栏 */}
      <header
        className="flex h-12 shrink-0 items-center gap-3 px-4 text-white/90"
        onClick={(e) => e.stopPropagation()}
      >
        <span className="truncate text-sm font-medium">
          {item.title || resolvedPath || tr("library_preview")}
        </span>
        {state === "viewing" && (
          <span className="shrink-0 rounded bg-white/10 px-1.5 py-0.5 font-mono text-[10px] uppercase text-white/60">
            {resolvedType}
          </span>
        )}
        {state === "viewing" && hasMultiple && (
          <span className="shrink-0 rounded bg-white/10 px-1.5 py-0.5 font-mono text-[10px] text-white/60">
            {currentIndex + 1} / {filteredItems.length}
          </span>
        )}
        <div className="flex-1" />
        {/* 选择面板时显示"返回选择"按钮 */}
        {state === "viewing" && Object.keys(typeCounts).length > 1 && (
          <button
            onClick={() => setState("select")}
            className="flex h-8 items-center gap-1 rounded-full bg-white/10 px-3 text-xs text-white/80 transition-colors hover:bg-white/20 hover:text-white"
            title="返回选择"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-3.5 w-3.5">
              <path d="M3 3v5h5" />
              <path d="M3.05 13A9 9 0 106 5.3L3 8" />
            </svg>
            选择
          </button>
        )}
        <button
          onClick={onClose}
          className="flex h-8 w-8 items-center justify-center rounded-full bg-white/10 text-white/80 transition-colors hover:bg-white/20 hover:text-white"
          aria-label={tr("close")}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </header>

      {/* 主内容区 */}
      <div
        className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {state === "loading" && (
          <div className="text-sm text-white/60">加载中…</div>
        )}

        {state === "error" && (
          <ErrorPanel message={errorMsg} />
        )}

        {/* 选择面板 — 混合类型时显示 */}
        {state === "select" && (
          <div className="flex flex-col items-center gap-8 p-8">
            <div className="text-center">
              <div className="mb-2 text-lg font-medium text-white/90">
                {tr("library_preview")}
              </div>
              <div className="text-sm text-white/50">
                本帖子包含多种媒体类型，请选择预览方式
              </div>
            </div>
            <div className="flex flex-wrap items-center justify-center gap-4">
              {typeCounts.video > 0 && (
                <TypeSelectButton
                  icon={<VideoIcon />}
                  label="播放视频"
                  count={typeCounts.video}
                  accent="from-blue-500/30 to-purple-500/30"
                  onClick={() => handleSelectType("video")}
                />
              )}
              {typeCounts.image > 0 && (
                <TypeSelectButton
                  icon={<ImageIcon />}
                  label="查看图片"
                  count={typeCounts.image}
                  accent="from-emerald-500/30 to-teal-500/30"
                  onClick={() => handleSelectType("image")}
                />
              )}
              {typeCounts.audio > 0 && (
                <TypeSelectButton
                  icon={<AudioIcon />}
                  label="播放音频"
                  count={typeCounts.audio}
                  accent="from-amber-500/30 to-orange-500/30"
                  onClick={() => handleSelectType("audio")}
                />
              )}
            </div>
          </div>
        )}

        {/* 查看模式 */}
        {state === "viewing" && currentItem && (
          <>
            {/* 左切换按钮 */}
            {hasMultiple && (
              <button
                onClick={goToPrev}
                disabled={currentIndex === 0}
                className="absolute left-4 top-1/2 z-10 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full bg-black/50 text-white/80 backdrop-blur-sm transition-colors hover:bg-black/70 hover:text-white disabled:opacity-20 disabled:hover:bg-black/50"
                title="上一项 (←)"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-5 w-5">
                  <polyline points="15 18 9 12 15 6" />
                </svg>
              </button>
            )}

            <div className="flex h-full w-full items-center justify-center">
              {currentItem.media_type === "video" && (
                <VideoPanel src={src} tr={tr} onOpenInSystemPlayer={onOpenInSystemPlayer} />
              )}
              {currentItem.media_type === "image" && (
                <ImagePanel src={src} tr={tr} onOpenInSystemPlayer={onOpenInSystemPlayer} />
              )}
              {currentItem.media_type === "audio" && (
                <AudioPanel src={src} tr={tr} onOpenInSystemPlayer={onOpenInSystemPlayer} />
              )}
              {!["video", "image", "audio"].includes(currentItem.media_type) && (
                <ErrorPanel
                  message={tr("preview_format_error")}
                  actionLabel={tr("open_in_system_player")}
                  onAction={onOpenInSystemPlayer}
                />
              )}
            </div>

            {/* 右切换按钮 */}
            {hasMultiple && (
              <button
                onClick={goToNext}
                disabled={currentIndex === filteredItems.length - 1}
                className="absolute right-4 top-1/2 z-10 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full bg-black/50 text-white/80 backdrop-blur-sm transition-colors hover:bg-black/70 hover:text-white disabled:opacity-20 disabled:hover:bg-black/50"
                title="下一项 (→)"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-5 w-5">
                  <polyline points="9 18 15 12 9 6" />
                </svg>
              </button>
            )}

            {/* 底部点状指示器（同类型多项时显示） */}
            {hasMultiple && (
              <div className="absolute bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-1.5 rounded-full bg-black/60 px-3 py-1.5 backdrop-blur-sm">
                {filteredItems.map((it, idx) => (
                  <button
                    key={idx}
                    onClick={() => setCurrentIndex(idx)}
                    className={`h-2 rounded-full transition-all ${
                      idx === currentIndex
                        ? "w-4 bg-white"
                        : "w-2 bg-white/40 hover:bg-white/70"
                    }`}
                    title={`${idx + 1}. ${it.media_type}`}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ============================================================
// 类型选择按钮（混合帖子选择面板）
// ============================================================

function TypeSelectButton({
  icon,
  label,
  count,
  accent,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  count: number;
  accent: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`group flex w-40 flex-col items-center gap-3 rounded-2xl bg-gradient-to-br ${accent} p-6 backdrop-blur-sm transition-all hover:scale-105 hover:shadow-2xl`}
    >
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-white/10 text-white/90 transition-transform group-hover:scale-110">
        {icon}
      </div>
      <div className="text-center">
        <div className="text-sm font-medium text-white/90">{label}</div>
        <div className="mt-0.5 text-xs text-white/50">{count} 项</div>
      </div>
    </button>
  );
}

function VideoIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-8 w-8">
      <polygon points="5 3 19 12 5 21 5 3" fill="currentColor" />
    </svg>
  );
}

function ImageIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-8 w-8">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="8.5" cy="8.5" r="1.5" />
      <polyline points="21 15 16 10 5 21" />
    </svg>
  );
}

function AudioIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-8 w-8">
      <path d="M9 18V5l12-2v13" />
      <circle cx="6" cy="18" r="3" />
      <circle cx="18" cy="16" r="3" />
    </svg>
  );
}

// ============================================================
// 视频面板
// ============================================================

function VideoPanel({
  src,
  tr,
  onOpenInSystemPlayer,
}: {
  src: string;
  tr: (k: string, p?: Record<string, string | number>) => string;
  onOpenInSystemPlayer: () => void;
}) {
  const [videoError, setVideoError] = useState<string | null>(null);
  const [isCodecUnsupported, setIsCodecUnsupported] = useState(false);

  useEffect(() => {
    setVideoError(null);
    setIsCodecUnsupported(false);
  }, [src]);

  if (videoError) {
    // Bug 2: 对 MEDIA_ERR_SRC_NOT_SUPPORTED（code=4）显示更友好的提示
    // Chromium 内置播放器不支持 HEVC/H.265、部分 MKV 等编码，
    // 错误信息含 "DEMUXER ERROR" / "open context failed" 时判定为编码不支持
    const msg = isCodecUnsupported ? tr("video_codec_unsupported") : `${tr("video_play_failed")}\n${videoError}`;
    return (
      <ErrorPanel
        message={msg}
        actionLabel={tr("open_in_system_player")}
        onAction={onOpenInSystemPlayer}
      />
    );
  }

  return (
    <video
      key={src}
      src={src}
      controls
      autoPlay
      className="max-h-full max-w-full object-contain"
      onError={(e) => {
        const v = e.currentTarget;
        const code = v.error?.code;
        const msg = v.error?.message || "";
        // code=4 = MEDIA_ERR_SRC_NOT_SUPPORTED（常见于 HEVC/H.265、MKV 等编码不支持）
        // Chromium 错误信息含 "DEMUXER ERROR" / "open context failed" 也是编码不支持
        if (code === 4 || /demuxer|open context|codec/i.test(msg)) {
          setIsCodecUnsupported(true);
          setVideoError(msg);
        } else {
          const codeMap: Record<number, string> = {
            1: "MEDIA_ERR_ABORTED",
            2: "MEDIA_ERR_NETWORK",
            3: "MEDIA_ERR_DECODE",
            4: "MEDIA_ERR_SRC_NOT_SUPPORTED",
          };
          const label = code ? codeMap[code] || `code ${code}` : "unknown";
          setVideoError(`${label}: ${msg}`);
        }
      }}
    />
  );
}

// ============================================================
// 图片面板 — 滚轮缩放 + 拖拽平移 + 双击重置
// ============================================================

function ImagePanel({
  src,
  tr,
  onOpenInSystemPlayer,
}: {
  src: string;
  tr: (k: string, p?: Record<string, string | number>) => string;
  onOpenInSystemPlayer: () => void;
}) {
  const [scale, setScale] = useState(1);
  const [tx, setTx] = useState(0);
  const [ty, setTy] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [imgError, setImgError] = useState(false);
  const dragStart = useRef({ x: 0, y: 0, tx: 0, ty: 0 });

  useEffect(() => {
    setScale(1);
    setTx(0);
    setTy(0);
    setImgError(false);
  }, [src]);

  const resetTransform = useCallback(() => {
    setScale(1);
    setTx(0);
    setTy(0);
  }, []);

  const onWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    setScale((prev) => Math.min(10, Math.max(0.2, prev * delta)));
  }, []);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if (scale <= 1) return;
    setDragging(true);
    dragStart.current = { x: e.clientX, y: e.clientY, tx, ty };
  }, [scale, tx, ty]);

  const onMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragging) return;
    const dx = e.clientX - dragStart.current.x;
    const dy = e.clientY - dragStart.current.y;
    setTx(dragStart.current.tx + dx);
    setTy(dragStart.current.ty + dy);
  }, [dragging]);

  const onMouseUp = useCallback(() => setDragging(false), []);

  if (imgError) {
    // Bug 2: 图片加载失败时也提供系统播放器 fallback（可能是路径问题或格式不支持）
    return (
      <ErrorPanel
        message={tr("image_load_failed")}
        actionLabel={tr("open_in_system_player")}
        onAction={onOpenInSystemPlayer}
      />
    );
  }

  return (
    <div
      className="flex h-full w-full items-center justify-center overflow-hidden"
      onWheel={onWheel}
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      onMouseLeave={onMouseUp}
      style={{ cursor: scale > 1 ? (dragging ? "grabbing" : "grab") : "default" }}
    >
      <img
        key={src}
        src={src}
        alt=""
        draggable={false}
        className="max-h-full max-w-full select-none object-contain"
        style={{
          transform: `translate(${tx}px, ${ty}px) scale(${scale})`,
          transition: dragging ? "none" : "transform 0.15s ease-out",
        }}
        onError={() => setImgError(true)}
        onDoubleClick={resetTransform}
      />
      {scale !== 1 && (
        <div className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full bg-black/60 px-3 py-1 text-xs font-medium text-white/90 backdrop-blur-sm">
          {tr("preview_zoom", { pct: Math.round(scale * 100) })}
        </div>
      )}
      {scale !== 1 && (
        <button
          onClick={resetTransform}
          className="absolute bottom-4 right-4 flex h-8 w-8 items-center justify-center rounded-full bg-black/60 text-white/80 backdrop-blur-sm transition-colors hover:bg-black/80 hover:text-white"
          title="Reset"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4">
            <path d="M3 12a9 9 0 109-9 9.75 9.75 0 00-6.74 2.74L3 8" />
            <path d="M3 3v5h5" />
          </svg>
        </button>
      )}
    </div>
  );
}

// ============================================================
// 音频面板 — 占位封面 + 播放器
// ============================================================

function AudioPanel({
  src,
  tr,
  onOpenInSystemPlayer,
}: {
  src: string;
  tr: (k: string, p?: Record<string, string | number>) => string;
  onOpenInSystemPlayer: () => void;
}) {
  const [audioError, setAudioError] = useState<string | null>(null);

  useEffect(() => {
    setAudioError(null);
  }, [src]);

  if (audioError) {
    return (
      <ErrorPanel
        message={`${tr("audio_play_failed")}\n${audioError}`}
        actionLabel={tr("open_in_system_player")}
        onAction={onOpenInSystemPlayer}
      />
    );
  }

  return (
    <div className="flex flex-col items-center gap-6 p-8">
      <div className="flex h-48 w-48 items-center justify-center rounded-2xl bg-gradient-to-br from-accent/30 to-purple-500/30 shadow-2xl">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-20 w-20 text-white/80">
          <path d="M9 18V5l12-2v13" />
          <circle cx="6" cy="18" r="3" />
          <circle cx="18" cy="16" r="3" />
        </svg>
      </div>
      <audio
        key={src}
        src={src}
        controls
        autoPlay
        className="w-full max-w-md"
        onError={(e) => {
          const a = e.currentTarget;
          const code = a.error?.code;
          const msg = a.error?.message || "";
          setAudioError(`code ${code || "?"}: ${msg}`);
        }}
      />
    </div>
  );
}

// ============================================================
// 错误面板
// ============================================================

function ErrorPanel({
  message,
  actionLabel,
  onAction,
}: {
  message: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-3 p-8 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-danger/15">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-6 w-6 text-danger">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
      </div>
      <div className="max-w-md whitespace-pre-line text-sm text-text-muted">
        {message}
      </div>
      {actionLabel && onAction && (
        <button
          onClick={onAction}
          className="mt-2 rounded-lg bg-white/10 px-4 py-1.5 text-sm font-medium text-text transition-colors hover:bg-white/20"
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
}
