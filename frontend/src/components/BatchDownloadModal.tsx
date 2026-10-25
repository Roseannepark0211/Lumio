/**
 * 批量下载弹窗 — 批量下载重构阶段 2。
 *
 * 入口形态（阶段 3 接线）：粘贴链接检测到个人主页 / 多帖链接后弹出。
 * 本文件只负责弹窗本身，不做链接检测、不调后端、不碰单帖粘贴流程。
 *
 * 样式：只用 tailwind 主题 token（bg / bg-surface / bg-elevated / accent /
 * text / text-muted / text-dim），跟随 <html> 的 dark class 走深浅主题。
 * 不要在这里引入 mockup 配色或任何自定义色板。
 *
 * —— 阶段 3 接线 props 契约（按此传入即可，阶段 3 不改组件签名）——
 *   works: Array<{
 *     url: string;                       // 作品链接（唯一标识，也是下载入参）
 *     title: string;                     // 作品标题（可为空串，组件内兜底显示“无标题”）
 *     thumbnail?: string;                // 缩略图 URL（可缺失，缺失时显示占位块）
 *     type: "video" | "image";            // 视频 / 图文
 *     duration_seconds?: number;         // 视频时长（秒，可缺失；缺失时不显示时长角标）
 *     image_count?: number;              // 图文张数（可缺失；缺失时不显示张数角标）
 *     post_time?: string;                // 发布时间（原样展示，可缺失）
 *   }>
 *   author: { name: string; platform: string }   // 博主名 + 平台名（用于标题和默认文件夹名）
 *   onClose: () => void                  // 关闭弹窗（点遮罩 / Esc / 取消按钮）
 *   onDownload: (payload: {
 *     selected_urls: string[];           // 已选作品 url，按 works 传入顺序排列
 *     folder_name: string;               // 清洗后的文件夹名（空时回落到默认名）
 *     global_quality: BatchVideoQuality; // 视频全局清晰度
 *     per_item_quality: Record<string, BatchVideoQuality>;
 *                                        // 仅含已选且单独改过清晰度的视频 url -> 清晰度
 *   }) => void
 *
 * 交互约定：
 *   - 默认全选；全选 / 取消全选作用于当前筛选结果（不是全部作品）。
 *   - 图片一律原图，不提供清晰度选择；视频全局清晰度 + 单个视频 override。
 *   - 全局清晰度档位按实际回落（后端负责回落逻辑，弹窗只传用户选择）。
 *   - 文件夹名非法字符（/ \ : * ? " < > | 及控制字符）自动清洗，
 *     输入框下方实时展示清洗后的结果；清洗后为空则下载时用默认名。
 */

import { useEffect, useMemo, useState } from "react";

export type BatchWorkType = "video" | "image";

export interface BatchWork {
  url: string;
  title: string;
  thumbnail?: string;
  type: BatchWorkType;
  duration_seconds?: number;
  image_count?: number;
  post_time?: string;
}

export interface BatchAuthor {
  name: string;
  platform: string;
}

export type BatchVideoQuality = "original" | "1080p" | "720p" | "480p";

export interface BatchDownloadPayload {
  selected_urls: string[];
  folder_name: string;
  global_quality: BatchVideoQuality;
  per_item_quality: Record<string, BatchVideoQuality>;
}

export interface BatchDownloadModalProps {
  works: BatchWork[];
  author: BatchAuthor;
  onClose: () => void;
  onDownload: (payload: BatchDownloadPayload) => void;
}

export const BATCH_VIDEO_QUALITIES: BatchVideoQuality[] = [
  "original",
  "1080p",
  "720p",
  "480p",
];

export const BATCH_VIDEO_QUALITY_LABELS: Record<BatchVideoQuality, string> = {
  original: "原画",
  "1080p": "1080p",
  "720p": "720p",
  "480p": "480p",
};

/** 文件夹名清洗：去掉 Windows / macOS / Linux 都不允许的字符及首尾空白与尾点。 */
export function sanitizeFolderName(raw: string): string {
  return raw
    .replace(/[\\/:*?"<>|\x00-\x1f]/g, "")
    .trim()
    .replace(/[. ]+$/g, "");
}

function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  return `${m}:${String(sec).padStart(2, "0")}`;
}

function formatToday(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}${m}${day}`;
}

type Filter = "all" | "video" | "image";

export function BatchDownloadModal({
  works,
  author,
  onClose,
  onDownload,
}: BatchDownloadModalProps) {
  const defaultFolderName = useMemo(() => {
    const base = author.name.trim() || "批量下载";
    return sanitizeFolderName(`${base}-${formatToday()}`) || `批量下载-${formatToday()}`;
  }, [author.name]);

  // 默认全选；全选 / 取消全选作用于当前筛选结果
  const [selected, setSelected] = useState<ReadonlySet<string>>(
    () => new Set(works.map((w) => w.url)),
  );
  const [filter, setFilter] = useState<Filter>("all");
  const [folderInput, setFolderInput] = useState(defaultFolderName);
  const [globalQuality, setGlobalQuality] = useState<BatchVideoQuality>("original");
  const [perItemQuality, setPerItemQuality] = useState<Record<string, BatchVideoQuality>>({});
  // 当前展开清晰度行的视频 url（同一时间只展开一个）
  const [qualityExpandedUrl, setQualityExpandedUrl] = useState<string | null>(null);

  // Esc 关闭（与 MediaPreviewDialog 同款写法）
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const filteredWorks = useMemo(
    () => (filter === "all" ? works : works.filter((w) => w.type === filter)),
    [works, filter],
  );
  const videoCount = useMemo(() => works.filter((w) => w.type === "video").length, [works]);
  const imageCount = useMemo(() => works.filter((w) => w.type === "image").length, [works]);

  const sanitizedFolderName = sanitizeFolderName(folderInput);
  const effectiveFolderName = sanitizedFolderName || defaultFolderName;

  const toggleSelect = (url: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(url)) next.delete(url);
      else next.add(url);
      return next;
    });
  };

  const selectFiltered = () => {
    setSelected((prev) => new Set([...prev, ...filteredWorks.map((w) => w.url)]));
  };

  const deselectFiltered = () => {
    setSelected((prev) => {
      const next = new Set(prev);
      filteredWorks.forEach((w) => next.delete(w.url));
      return next;
    });
  };

  const handleDownload = () => {
    const selectedWorks = works.filter((w) => selected.has(w.url));
    const overrides: Record<string, BatchVideoQuality> = {};
    selectedWorks.forEach((w) => {
      if (w.type === "video" && perItemQuality[w.url]) {
        overrides[w.url] = perItemQuality[w.url];
      }
    });
    onDownload({
      selected_urls: selectedWorks.map((w) => w.url),
      folder_name: effectiveFolderName,
      global_quality: globalQuality,
      per_item_quality: overrides,
    });
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="glass-card flex h-[80vh] w-[min(720px,92vw)] flex-col overflow-hidden bg-bg-surface/95"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="批量下载"
      >
        {/* 头：固定 */}
        <div className="flex shrink-0 items-start justify-between gap-3 px-5 pb-3 pt-4">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-text">
              批量下载 · {author.name}
            </h2>
            <p className="mt-0.5 text-xs text-text-muted">
              {author.platform} · 共 {works.length} 个作品
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭"
            className="shrink-0 rounded-lg px-2 py-1 text-lg leading-none text-text-muted hover:bg-bg-elevated hover:text-text"
          >
            ×
          </button>
        </div>

        {/* 工具栏：固定 */}
        <div className="flex shrink-0 flex-wrap items-center gap-2 border-t px-5 py-3">
          <button
            type="button"
            data-testid="batch-select-all"
            onClick={selectFiltered}
            className="rounded-lg border px-3 py-1.5 text-xs font-medium text-text hover:bg-bg-elevated"
          >
            全选
          </button>
          <button
            type="button"
            data-testid="batch-deselect-all"
            onClick={deselectFiltered}
            className="rounded-lg border px-3 py-1.5 text-xs font-medium text-text hover:bg-bg-elevated"
          >
            取消全选
          </button>
          <div className="mx-1 h-5 w-px bg-bg-elevated" />
          <div className="flex rounded-lg bg-bg-elevated p-0.5">
            <button
              type="button"
              data-testid="batch-filter-all"
              onClick={() => setFilter("all")}
              className={`rounded-md px-3 py-1.5 text-xs font-medium ${
                filter === "all" ? "bg-accent text-white" : "text-text-muted"
              }`}
            >
              全部 {works.length}
            </button>
            <button
              type="button"
              data-testid="batch-filter-video"
              onClick={() => setFilter("video")}
              className={`rounded-md px-3 py-1.5 text-xs font-medium ${
                filter === "video" ? "bg-accent text-white" : "text-text-muted"
              }`}
            >
              仅视频 {videoCount}
            </button>
            <button
              type="button"
              data-testid="batch-filter-image"
              onClick={() => setFilter("image")}
              className={`rounded-md px-3 py-1.5 text-xs font-medium ${
                filter === "image" ? "bg-accent text-white" : "text-text-muted"
              }`}
            >
              仅图片 {imageCount}
            </button>
          </div>
          <span className="ml-auto text-xs text-text-muted">
            已选 {selected.size} / {works.length}
          </span>
        </div>

        {/* 文件夹命名 + 清晰度：固定 */}
        <div className="shrink-0 space-y-3 border-t px-5 py-3">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-text-muted">
              保存文件夹
            </label>
            <input
              type="text"
              data-testid="batch-folder-input"
              value={folderInput}
              onChange={(e) => setFolderInput(e.target.value)}
              placeholder={defaultFolderName}
              className="w-full rounded-lg border bg-bg-surface px-3 py-2 text-sm text-text outline-none focus:border-accent"
            />
            {sanitizedFolderName !== folderInput && (
              <p className="mt-1 text-xs text-text-muted">
                {sanitizedFolderName
                  ? `清洗后：${sanitizedFolderName}`
                  : "清洗后为空，下载时将使用默认名称"}
              </p>
            )}
          </div>
          <div>
            <div className="mb-1.5 flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium text-text-muted">视频清晰度</span>
              <div className="flex rounded-lg bg-bg-elevated p-0.5">
                {BATCH_VIDEO_QUALITIES.map((q) => (
                  <button
                    key={q}
                    type="button"
                    data-testid={`batch-global-quality-${q}`}
                    onClick={() => setGlobalQuality(q)}
                    className={`rounded-md px-3 py-1.5 text-xs font-medium ${
                      globalQuality === q ? "bg-accent text-white" : "text-text-muted"
                    }`}
                  >
                    {BATCH_VIDEO_QUALITY_LABELS[q]}
                  </button>
                ))}
              </div>
            </div>
            <p className="text-xs text-text-dim">
              图片一律原图；视频无此档位时自动回落到最接近的档位；单个视频可在卡片里单独改清晰度。
            </p>
          </div>
        </div>

        {/* 网格：内部滚动 */}
        <div className="min-h-0 flex-1 overflow-y-auto border-t px-5 py-4">
          {filteredWorks.length === 0 ? (
            <p className="py-10 text-center text-sm text-text-muted">
              {works.length === 0 ? "暂无作品" : "该筛选下暂无作品"}
            </p>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {filteredWorks.map((work) => {
                const isSelected = selected.has(work.url);
                const title = work.title.trim() || "无标题";
                const override = perItemQuality[work.url];
                const qualityExpanded = qualityExpandedUrl === work.url;
                return (
                  <div
                    key={work.url}
                    onClick={() => toggleSelect(work.url)}
                    className={`cursor-pointer overflow-hidden rounded-xl border bg-bg-surface ${
                      isSelected ? "ring-2 ring-accent" : ""
                    }`}
                  >
                    {/* 缩略图 */}
                    <div className="relative aspect-video w-full overflow-hidden bg-bg-elevated">
                      {work.thumbnail ? (
                        <img
                          src={work.thumbnail}
                          alt={title}
                          className="h-full w-full object-cover"
                          loading="lazy"
                        />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center text-xs text-text-dim">
                          无缩略图
                        </div>
                      )}
                      {/* 复选框：24px 触点 */}
                      <button
                        type="button"
                        data-testid="batch-card-checkbox"
                        aria-label={isSelected ? "取消选择" : "选择"}
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleSelect(work.url);
                        }}
                        className={`absolute left-2 top-2 flex h-6 w-6 items-center justify-center rounded-md border text-sm leading-none ${
                          isSelected
                            ? "border-accent bg-accent text-white"
                            : "border-text/30 bg-bg-surface/80 text-transparent"
                        }`}
                      >
                        ✓
                      </button>
                      {/* 角标：视频时长 / 图文张数 */}
                      {work.type === "video" && work.duration_seconds != null && (
                        <span className="absolute bottom-2 right-2 rounded bg-black/60 px-1.5 py-0.5 text-[11px] text-white">
                          {formatDuration(work.duration_seconds)}
                        </span>
                      )}
                      {work.type === "image" && work.image_count != null && (
                        <span className="absolute bottom-2 right-2 rounded bg-black/60 px-1.5 py-0.5 text-[11px] text-white">
                          {work.image_count}张
                        </span>
                      )}
                    </div>
                    {/* 标题 + 元信息 */}
                    <div className="p-2">
                      <p className="truncate text-sm text-text" title={title}>
                        {title}
                      </p>
                      <div className="mt-1 flex items-center justify-between gap-2">
                        <span className="min-w-0 truncate text-xs text-text-muted">
                          {work.post_time || (work.type === "video" ? "视频" : "图文")}
                        </span>
                        {work.type === "video" && (
                          <button
                            type="button"
                            data-testid="batch-quality-toggle"
                            onClick={(e) => {
                              e.stopPropagation();
                              setQualityExpandedUrl(qualityExpanded ? null : work.url);
                            }}
                            className="shrink-0 rounded-md border px-2 py-1 text-xs text-text-muted hover:bg-bg-elevated hover:text-text"
                          >
                            {override
                              ? BATCH_VIDEO_QUALITY_LABELS[override]
                              : "跟随全局"}
                            {qualityExpanded ? " ▴" : " ▾"}
                          </button>
                        )}
                      </div>
                      {/* 单项清晰度 override：行内展开，不会被滚动容器裁剪 */}
                      {work.type === "video" && qualityExpanded && (
                        <div
                          className="mt-2 flex flex-wrap gap-1.5"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button
                            type="button"
                            data-testid="batch-quality-opt-follow"
                            onClick={() => {
                              setPerItemQuality((prev) => {
                                const next = { ...prev };
                                delete next[work.url];
                                return next;
                              });
                            }}
                            className={`rounded-md px-2 py-1 text-xs ${
                              !override
                                ? "bg-accent text-white"
                                : "border text-text-muted hover:text-text"
                            }`}
                          >
                            跟随全局
                          </button>
                          {BATCH_VIDEO_QUALITIES.map((q) => (
                            <button
                              key={q}
                              type="button"
                              data-testid={`batch-quality-opt-${q}`}
                              onClick={() =>
                                setPerItemQuality((prev) => ({ ...prev, [work.url]: q }))
                              }
                              className={`rounded-md px-2 py-1 text-xs ${
                                override === q
                                  ? "bg-accent text-white"
                                  : "border text-text-muted hover:text-text"
                              }`}
                            >
                              {BATCH_VIDEO_QUALITY_LABELS[q]}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* 尾：固定 */}
        <div className="flex shrink-0 items-center justify-between gap-3 border-t px-5 py-3">
          <span className="text-xs text-text-muted">已选 {selected.size} 项</span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border px-4 py-2 text-sm text-text hover:bg-bg-elevated"
            >
              取消
            </button>
            <button
              type="button"
              data-testid="batch-download"
              onClick={handleDownload}
              disabled={selected.size === 0}
              className="rounded-lg bg-accent px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-glow disabled:cursor-not-allowed disabled:opacity-40"
            >
              下载选中（{selected.size}）
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
