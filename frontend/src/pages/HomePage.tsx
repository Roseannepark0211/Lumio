/**
 * React HomePage — 复刻 QML HomePage.qml 完整功能。
 *
 * 功能清单（与 QML 版本对齐）：
 *   1. URL 输入框（粘贴/清空）
 *   2. URL 解析 → 预览区（图片/视频自适应宽高比）
 *   3. Media Items 横向列表（多图/多视频切换 + 单项直链入队）
 *   4. 格式选择下拉（formats.length > 1 时显示）
 *   5. 文件名输入框（默认作者+发布时间）
 *   6. 加入队列按钮（含非阻断去重检查）
 *   7. X-Sou 搜索面板（开关由 config.enable_xsou 控制）
 *   8. X-Sou 视频预览（下载进度对话框 + VideoPreviewDialog）
 *
 * 不实现的功能（QML 版本本身就没有，AGENTS.md 文档与代码不一致）：
 *   - IG/YouTube/X 批量对话框
 *   - 多行 URL 批量导入
 */

import { useEffect, useState, useCallback, useRef } from "react";
import {
  api,
  subscribeEvents,
  type AppEvent,
  type VideoInfo,
  type XSouResult,
  type XSouSearchPayload,
  type ParseCompletedPayload,
  type PreviewProgressPayload,
} from "../api";
import { useI18n } from "../i18n";
import { MediaItemsList, type SortedMediaItem } from "./home/MediaItemsList";
import { PreviewArea } from "./home/PreviewArea";
import { XSouSearchPanel } from "./home/XSouSearchPanel";
import { VideoPreviewDialog } from "./home/VideoPreviewDialog";
import { PreviewProgressDialog } from "./home/PreviewProgressDialog";

// 8 个平台徽章配置（与老版本 QML HomePage.qml 对齐）
const PLATFORM_PILLS: { plat: string; labelKey: string; defaultLabel: string; color: string }[] = [
  { plat: "youtube", labelKey: "", defaultLabel: "YouTube", color: "#ff3b5c" },
  { plat: "instagram", labelKey: "", defaultLabel: "Instagram", color: "#e1306c" },
  { plat: "x", labelKey: "", defaultLabel: "X", color: "#1d9bf0" },
  { plat: "bilibili", labelKey: "platform_bilibili", defaultLabel: "B站", color: "#fb7299" },
  { plat: "douyin", labelKey: "platform_douyin", defaultLabel: "抖音", color: "#25f4ee" },
  { plat: "kuaishou", labelKey: "platform_kuaishou", defaultLabel: "快手", color: "#ff6a00" },
  { plat: "weibo", labelKey: "platform_weibo", defaultLabel: "微博", color: "#e6162d" },
  { plat: "xiaohongshu", labelKey: "platform_xiaohongshu", defaultLabel: "小红书", color: "#ff2442" },
];

export function HomePage() {
  // —— i18n ——
  const { tr } = useI18n();

  // —— URL 输入状态 ——
  const [urlText, setUrlText] = useState("");
  const [isParsing, setIsParsing] = useState(false);

  // —— 解析结果状态 ——
  const [previewInfo, setPreviewInfo] = useState<VideoInfo | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [selectedItemIndex, setSelectedItemIndex] = useState(-1);
  const [addedItemIndices, setAddedItemIndices] = useState<Record<number, boolean>>({});
  const [sortedItems, setSortedItems] = useState<SortedMediaItem[]>([]);

  // —— 格式选择 + 文件名 ——
  const [customName, setCustomName] = useState("");
  const [selectedFormatId, setSelectedFormatId] = useState("");
  const [selectedFormatType, setSelectedFormatType] = useState("");

  // —— X-Sou 搜索状态 ——
  const [xsouEnabled, setXsouEnabled] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<XSouResult[]>([]);
  const [searchTotal, setSearchTotal] = useState(0);
  const [searchPage, setSearchPage] = useState(0);
  const [searchLimit] = useState(20);
  const [selectedSearchItems, setSelectedSearchItems] = useState<Record<number, boolean>>({});

  // —— X-Sou 视频预览状态 ——
  const [, setPreviewDialogOpen] = useState(false);
  const [previewProgressDialogOpen, setPreviewProgressDialogOpen] = useState(false);
  const [previewProgress, setPreviewProgress] = useState<PreviewProgressPayload | null>(null);
  const [previewLocalPath, setPreviewLocalPath] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // —— Toast ——
  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<number | null>(null);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 2500);
  }, []);

  // —— 初始化：加载 config（xsou 开关）——
  useEffect(() => {
    (async () => {
      try {
        const cfg = await api.getConfig();
        setXsouEnabled(!!(cfg as Record<string, unknown>).enable_xsou);
      } catch (e) {
        console.warn("load config failed:", e);
      }
    })();
  }, []);

  // —— WebSocket 事件订阅 ——
  useEffect(() => {
    const unsub = subscribeEvents((e: AppEvent) => {
      handleEvent(e);
    });
    return unsub;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleEvent = useCallback((e: AppEvent) => {
    switch (e.type) {
      case "config_changed": {
        // X-Sou 开关等配置变更时实时刷新（设置页切换开关后立即生效）
        // 后端事件只通知 key，不带值，需重新拉 config
        (async () => {
          try {
            const cfg = await api.getConfig();
            setXsouEnabled(!!(cfg as Record<string, unknown>).enable_xsou);
          } catch {}
        })();
        break;
      }
      case "parse_completed": {
        const p = e.data as ParseCompletedPayload;
        setIsParsing(false);
        if (p?.info) {
          setPreviewInfo(p.info);
          setParseError(null);
          setSelectedItemIndex(-1);
          setAddedItemIndices({});
          // 默认 customName = author + post_time
          const parts: string[] = [];
          if (p.info.author) parts.push(p.info.author);
          if (p.info.post_time) parts.push(p.info.post_time);
          setCustomName(parts.join("_"));
          // 默认选 formats[0]
          if (p.info.formats.length > 0) {
            setSelectedFormatId(p.info.formats[0].format_id);
            setSelectedFormatType(p.info.formats[0].type);
          } else {
            setSelectedFormatId("");
            setSelectedFormatType("");
          }
          // 构建 sorted items（视频在前，图片在后）
          const sorted = buildSortedItems(p.info);
          setSortedItems(sorted);
          // 多项帖默认选中第一项
          if (sorted.length > 1) {
            setSelectedItemIndex(sorted[0].orig_idx);
          }
        } else {
          setParseError("解析结果无效");
        }
        break;
      }
      case "parse_failed": {
        setIsParsing(false);
        setPreviewInfo(null);
        setParseError((e.data as { error?: string })?.error || "解析失败");
        break;
      }
      case "search_completed": {
        setIsSearching(false);
        // 后端 publish 的 payload 结构：{request_id, results: {data:[], total, page, ...}}
        // 其中 results 是 x_sou_search() 返回的 x-sou.com API 原始响应
        const payload = e.data as { request_id?: string; results?: unknown } | null;
        const rawResults = payload?.results;
        let results: XSouResult[] = [];
        let total = 0;
        // rawResults 可能是 {data:[], total, page} 对象，也可能是 [] 数组
        if (Array.isArray(rawResults)) {
          results = rawResults;
          total = rawResults.length;
        } else if (rawResults && typeof rawResults === "object") {
          const obj = rawResults as XSouSearchPayload;
          if (Array.isArray(obj.data)) {
            results = obj.data;
            total = obj.total || results.length;
          }
        }
        setSearchResults(results);
        setSearchTotal(total);
        setSelectedSearchItems({});
        break;
      }
      case "search_failed": {
        setIsSearching(false);
        setSearchResults([]);
        setSearchTotal(0);
        showToast((e.data as { error?: string })?.error || "搜索失败");
        break;
      }
      case "preview_progress": {
        setPreviewProgress(e.data as PreviewProgressPayload);
        break;
      }
      case "preview_ready": {
        setPreviewProgressDialogOpen(false);
        setPreviewProgress(null);
        setPreviewLocalPath((e.data as { path?: string })?.path ?? null);
        setPreviewError(null);
        setPreviewDialogOpen(true);
        break;
      }
      case "preview_failed": {
        setPreviewProgressDialogOpen(false);
        setPreviewProgress(null);
        const err = (e.data as { error?: string })?.error || tr("x_sou_preview_failed", { err: "" });
        if (err === "cancelled") {
          showToast(tr("x_sou_preview_cancelled"));
        } else {
          setPreviewError(err);
          setPreviewDialogOpen(true);
        }
        break;
      }
      case "toast": {
        const msg = (e.data as { message?: string })?.message;
        if (msg) showToast(msg);
        break;
      }
      default:
        // 其他事件（task_added/queue_changed 等）由 DownloadsPage 处理
        break;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tr]);

  // —— URL 解析 ——
  const parseUrl = useCallback(async () => {
    const url = urlText.trim();
    if (!url || isParsing) return;
    setIsParsing(true);
    setPreviewInfo(null);
    setParseError(null);
    setSelectedItemIndex(-1);
    setAddedItemIndices({});
    setSortedItems([]);
    setCustomName("");
    setSelectedFormatId("");
    setSelectedFormatType("");
    try {
      await api.parseUrl(url);
    } catch (e) {
      setIsParsing(false);
      setParseError(tr("parse_failed") + `: ${e}`);
    }
  }, [urlText, isParsing, tr]);

  // —— 粘贴 ——
  const pasteFromClipboard = useCallback(async () => {
    try {
      const { text } = await api.getClipboardText();
      if (text) setUrlText(text);
    } catch (e) {
      showToast(tr("paste_failed", { err: String(e) }));
    }
  }, [showToast, tr]);

  // —— 清空 ——
  const clearInput = useCallback(() => {
    setUrlText("");
    setPreviewInfo(null);
    setParseError(null);
    setSortedItems([]);
  }, []);

  // —— 单项直链入队（多图帖子项）——
  const enqueueSingleItem = useCallback(async (origIdx: number) => {
    if (!previewInfo) return;
    const item = previewInfo.items[origIdx];
    if (!item || !item.url) {
      showToast(tr("video_url_invalid"));
      return;
    }
    if (addedItemIndices[origIdx]) return;
    try {
      // 视频用帖子缩略图，图片用 item.url
      const thumb = item.is_video ? previewInfo.thumbnail : item.url;
      const title = customName || `${origIdx + 1}`;
      await api.addDirectDownloadTask({
        url: item.url,
        title,
        platform: previewInfo.platform,
        thumbnail: thumb,
        is_video: item.is_video,
        author: previewInfo.author,
      });
      setAddedItemIndices((prev) => ({ ...prev, [origIdx]: true }));
      showToast(tr("item_added"));
    } catch (e) {
      showToast(tr("enqueue_failed", { err: String(e) }));
    }
  }, [previewInfo, customName, addedItemIndices, showToast, tr]);

  // —— 整帖入队（带格式选择 + 非阻断去重）——
  const enqueue = useCallback(async () => {
    if (!previewInfo) return;
    try {
      // 去重检查（非阻断）
      const dup = await api.checkUrlDuplicate(previewInfo.url);
      if (dup.duplicate) {
        showToast(tr("dup_continue"));
      }
      await api.addDownloadTask({
        info: previewInfo,
        format_id: selectedFormatId,
        format_type: selectedFormatType,
        custom_name: customName,
      });
      showToast(tr("item_added"));
    } catch (e) {
      showToast(tr("enqueue_failed", { err: String(e) }));
    }
  }, [previewInfo, customName, selectedFormatId, selectedFormatType, showToast, tr]);

  // —— X-Sou 搜索 ——
  const runSearch = useCallback(async (q: string, page: number) => {
    if (!q || isSearching) return;
    setIsSearching(true);
    setSearchPage(page);
    setSelectedSearchItems({});
    try {
      await api.searchXSou(q, page, searchLimit);
    } catch (e) {
      setIsSearching(false);
      showToast(tr("search_error", { err: String(e) }));
    }
  }, [isSearching, searchLimit, showToast, tr]);

  // —— X-Sou 多选 ——
  const toggleSearchItem = useCallback((idx: number, checked: boolean) => {
    setSelectedSearchItems((prev) => {
      const next = { ...prev };
      if (checked) next[idx] = true;
      else delete next[idx];
      return next;
    });
  }, []);

  // —— X-Sou 批量入队 ——
  const batchEnqueueSearch = useCallback(async () => {
    const indices = Object.keys(selectedSearchItems).map(Number);
    if (indices.length === 0) return;
    let count = 0;
    for (const idx of indices) {
      const r = searchResults[idx];
      if (!r?.video_url) continue;
      try {
        await api.addDirectDownloadTask({
          url: r.video_url,
          title: r.content.substring(0, 80),
          platform: "x",
          thumbnail: r.video_cover,
          is_video: true,
          author: r.author || "",
        });
        count += 1;
      } catch (e) {
        console.warn("enqueue search item failed:", e);
      }
    }
    showToast(tr("item_added_count", { n: count }));
    setSelectedSearchItems({});
  }, [selectedSearchItems, searchResults, showToast, tr]);

  // —— X-Sou 视频预览 ——
  const previewXVideo = useCallback(async (videoUrl: string) => {
    if (!videoUrl) {
      showToast(tr("video_url_invalid"));
      return;
    }
    setPreviewProgress(null);
    setPreviewLocalPath(null);
    setPreviewError(null);
    setPreviewProgressDialogOpen(true);
    try {
      await api.previewXVideo(videoUrl);
    } catch (e) {
      setPreviewProgressDialogOpen(false);
      showToast(tr("preview_request_failed", { err: String(e) }));
    }
  }, [showToast, tr]);

  // —— 取消预览 ——
  const cancelPreview = useCallback(async () => {
    try {
      await api.cancelPreview();
    } catch (e) {
      console.warn("cancel preview failed:", e);
    }
    setPreviewProgressDialogOpen(false);
    setPreviewProgress(null);
  }, []);

  // —— 关闭预览对话框 ——
  const closePreviewDialog = useCallback(() => {
    setPreviewDialogOpen(false);
    setPreviewLocalPath(null);
    setPreviewError(null);
  }, []);

  return (
    <div className="h-full overflow-y-auto p-6">
      {/* ============================================================ */}
      {/* HERO 区 — 复刻老版本 QML HomePage.qml 顶部（标签+大标题+副标题+平台徽章） */}
      {/* ============================================================ */}
      <section className="mb-6 flex flex-col items-center pt-4 animate-slide-up">
        {/* Hero tag — 小胶囊标签 */}
        <div
          className="mb-4 inline-flex items-center gap-1.5 rounded-full border px-3.5 py-1"
          style={{
            backgroundColor: "rgba(10, 132, 255, 0.12)",
            borderColor: "rgba(10, 132, 255, 0.35)",
          }}
        >
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ backgroundColor: "#0a84ff" }}
          />
          <span
            className="font-mono text-[10px] font-semibold tracking-wide"
            style={{ color: "#0a84ff" }}
          >
            {tr("neural_capture")}
          </span>
        </div>

        {/* Hero title — 两行大标题 */}
        <h1 className="text-center text-4xl font-extrabold tracking-tight text-text">
          <span className="block">{tr("hero_line1")}</span>
          <span className="block text-text font-extrabold">
            {tr("hero_line2")}
          </span>
        </h1>

        {/* Subtitle */}
        <p className="mt-3.5 text-center text-sm text-text-muted">
          {tr("hero_sub")}
        </p>

        {/* Platform pills — 8 个平台徽章 */}
        <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
          {PLATFORM_PILLS.map((p) => {
            const label = p.labelKey ? tr(p.labelKey) : p.defaultLabel;
            return (
              <span
                key={p.plat}
                className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3.5 py-1.5 text-xs font-semibold text-text-muted transition-all hover:-translate-y-0.5 hover:border-white/20 hover:text-text"
              >
                <span
                  className="h-1.5 w-1.5 rounded-full"
                  style={{ backgroundColor: p.color }}
                />
                {label}
              </span>
            );
          })}
        </div>
      </section>

      {/* URL 输入卡片 */}
      <div className="glass-card mb-4 p-5 animate-slide-up">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-text">{tr("url_input")}</h2>
          <div className="flex gap-1.5">
            <button
              onClick={pasteFromClipboard}
              className="rounded-lg bg-white/5 px-3 py-1 text-xs text-text-muted transition-colors hover:bg-white/10 hover:text-text"
            >
              {tr("paste")}
            </button>
            <button
              onClick={clearInput}
              disabled={!urlText}
              className="rounded-lg bg-white/5 px-3 py-1 text-xs text-text-muted transition-colors hover:bg-white/10 hover:text-text disabled:opacity-30"
            >
              {tr("reset")}
            </button>
          </div>
        </div>
        <textarea
          value={urlText}
          onChange={(e) => setUrlText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              parseUrl();
            }
          }}
          placeholder={tr("url_placeholder")}
          rows={3}
          className="w-full resize-none rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-text placeholder:text-text-muted/60 focus:border-accent focus:outline-none"
        />
        <div className="mt-3 flex items-center justify-between">
          <span className="text-xs text-text-muted">
            {isParsing ? tr("parsing") : "Ctrl+Enter"}
          </span>
          <button
            onClick={parseUrl}
            disabled={!urlText.trim() || isParsing}
            className="rounded-xl bg-accent px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-glow disabled:cursor-not-allowed disabled:opacity-40"
          >
            {isParsing ? tr("parsing") : tr("parse")}
          </button>
        </div>
      </div>

      {/* 解析错误 */}
      {parseError && (
        <div className="glass-card mb-4 border-danger/30 p-4 animate-slide-up">
          <div className="flex items-center gap-2 text-sm text-danger">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            {parseError}
          </div>
        </div>
      )}

      {/* Media Items 横向列表（多项帖） */}
      {previewInfo && sortedItems.length > 1 && (
        <MediaItemsList
          items={sortedItems}
          selectedItemIndex={selectedItemIndex}
          addedItemIndices={addedItemIndices}
          onSelect={setSelectedItemIndex}
          onEnqueue={enqueueSingleItem}
        />
      )}

      {/* 预览区 */}
      {previewInfo && (
        <>
          <PreviewArea
            previewInfo={previewInfo}
            selectedItemIndex={selectedItemIndex}
            sortedItems={sortedItems}
          />

          {/* 格式选择 + 文件名 + 入队 */}
          <div className="glass-card mb-4 p-4 animate-slide-up">
            <div className="mb-3 flex items-center gap-3">
              <input
                type="text"
                value={customName}
                onChange={(e) => setCustomName(e.target.value)}
                placeholder={tr("leave_empty")}
                className="flex-1 rounded-xl border border-text/15 bg-bg-surface px-3 py-2 text-sm text-text shadow-sm transition-colors hover:border-text/25 placeholder:text-text-muted/60 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/40"
              />
              {previewInfo.formats.length > 1 && (
                <select
                  value={selectedFormatId}
                  onChange={(e) => {
                    const f = previewInfo.formats.find((x) => x.format_id === e.target.value);
                    if (f) {
                      setSelectedFormatId(f.format_id);
                      setSelectedFormatType(f.type);
                    }
                  }}
                  className="rounded-xl border border-text/15 bg-bg-surface px-3 py-2 text-sm text-text shadow-sm transition-colors hover:border-text/25 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/40"
                >
                  {previewInfo.formats.map((f) => (
                    <option key={f.format_id} value={f.format_id} className="bg-bg-surface text-text">
                      {f.label}
                    </option>
                  ))}
                </select>
              )}
              <button
                onClick={enqueue}
                className="rounded-xl bg-accent px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-glow"
              >
                {tr("add_to_queue")}
              </button>
            </div>
          </div>
        </>
      )}

      {/* X-Sou 搜索面板（开关由 config 控制） */}
      {xsouEnabled && (
        <XSouSearchPanel
          isSearching={isSearching}
          searchResults={searchResults}
          searchTotal={searchTotal}
          searchPage={searchPage}
          searchLimit={searchLimit}
          selectedItems={selectedSearchItems}
          onSearch={(q, p) => runSearch(q, p)}
          onSelectItem={toggleSearchItem}
          onClearSelection={() => setSelectedSearchItems({})}
          onBatchEnqueue={batchEnqueueSearch}
          onPreview={previewXVideo}
          onClose={() => {
            // 清空搜索结果与状态，保留搜索框输入
            setSearchResults([]);
            setSearchTotal(0);
            setSearchPage(0);
            setSelectedSearchItems({});
            setIsSearching(false);
          }}
        />
      )}

      {/* X-Sou 视频预览下载进度对话框 */}
      <PreviewProgressDialog
        open={previewProgressDialogOpen}
        progress={previewProgress}
        onCancel={cancelPreview}
      />

      {/* X-Sou 视频预览播放对话框 */}
      <VideoPreviewDialog
        localPath={previewLocalPath}
        error={previewError}
        onClose={closePreviewDialog}
      />

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-6 left-1/2 z-[60] -translate-x-1/2 animate-fade-in">
          <div className="rounded-xl border border-white/10 bg-bg-elevated/95 px-4 py-2 text-sm text-text shadow-2xl backdrop-blur-lg">
            {toast}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * 构建 sorted items（视频在前、图片在后，同类型按 orig_idx 升序）。
 * 与 QML _buildMediaItems(info) 对齐。
 */
function buildSortedItems(info: VideoInfo): SortedMediaItem[] {
  if (!info.items || info.items.length <= 1) return [];
  const indexed = info.items.map((item, orig_idx) => ({ item, orig_idx }));
  // 视频在前（is_video === true），图片在后
  indexed.sort((a, b) => {
    if (a.item.is_video !== b.item.is_video) {
      return a.item.is_video ? -1 : 1;
    }
    return a.orig_idx - b.orig_idx;
  });
  return indexed.map((s, i) => ({
    orig_idx: s.orig_idx,
    display_pos: i + 1,
    item: s.item,
  }));
}
