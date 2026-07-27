/**
 * React LibraryPage — 复刻 QML LibraryPage.qml 完整功能。
 *
 * 功能清单（与 QML 版本对齐）：
 *   1. Collections 左侧栏（All Items / Favorites / 用户 Collection）
 *   2. 媒体网格 3 列布局（封面 + 标题 + 作者 + 平台/类型徽章 + 操作栏）
 *   3. 客户端搜索 + 平台筛选 + 类型筛选 + Collection 筛选 + 一键重置
 *   4. 收藏切换（立即翻转 UI，不等 library_changed 信号）
 *   5. 加入/移除 Collection 菜单（切换模式：✓ = 已加入，点击移除）
 *   6. Collection 右键菜单（重命名/删除）
 *   7. 新建 Collection 对话框
 *   8. 文件缺失对话框（source="library" 的 file_missing 事件）
 *   9. WebSocket 事件驱动刷新（library_changed / library_record_added）
 *
 * 与 QML 版本差异：
 *   - QML 用 Menu/MenuItem 弹出菜单，React 用绝对定位的自定义下拉
 *   - QML 用 Dialog，React 用 ModalDialog 组件（与 HistoryPage 同款）
 */

import { useEffect, useState, useCallback, useMemo, useRef, memo } from "react";
import {
  api,
  subscribeEvents,
  thumbProxyUrl,
  lumioFileUrl,
  type AppEvent,
  type LibraryItem,
  type LibraryCollection,
} from "../api";
import { useI18n } from "../i18n";

// ============================================================
// 常量
// ============================================================

// 平台展示名（接受 tr 以支持多语言；YouTube/IG/X 等英文名不翻译）
function platformLabel(p: string, tr: (k: string) => string): string {
  switch (p) {
    case "youtube":
      return "YouTube";
    case "instagram":
      return "IG";
    case "x":
      return "X";
    case "bilibili":
      return tr("platform_bilibili");
    case "douyin":
      return tr("platform_douyin");
    case "kuaishou":
      return tr("platform_kuaishou");
    case "weibo":
      return tr("platform_weibo");
    case "xiaohongshu":
      return tr("platform_xiaohongshu");
    default:
      return p ? p.toUpperCase() : "";
  }
}

// 平台徽章颜色（与 QML Theme.platformColor 对齐）
const PLATFORM_COLOR: Record<string, string> = {
  youtube: "text-red-400",
  instagram: "text-pink-400",
  x: "text-zinc-200",
  bilibili: "text-blue-400",
  douyin: "text-zinc-100",
  kuaishou: "text-orange-400",
  weibo: "text-orange-500",
  xiaohongshu: "text-red-500",
};

function platformColor(p: string): string {
  return PLATFORM_COLOR[p] || "text-text-muted";
}

// 媒体类型徽章颜色（与 QML 实现对齐；label 走 i18n）
function typeBadgeClass(
  t: string,
  tr: (k: string) => string
): { bg: string; text: string; label: string } {
  switch (t) {
    case "video":
      return { bg: "bg-accent/20", text: "text-accent", label: tr("library_filter_video") };
    case "image":
      return { bg: "bg-success/20", text: "text-success", label: tr("library_filter_image") };
    case "audio":
      return { bg: "bg-warning/20", text: "text-warning", label: tr("library_filter_audio") };
    case "mixed":
      return { bg: "bg-purple-500/20", text: "text-purple-400", label: tr("media_mixed") };
    default:
      return { bg: "bg-white/10", text: "text-text-muted", label: t.toUpperCase() };
  }
}

function formatSize(bytes: number): string {
  if (!bytes || bytes <= 0) return "—";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB";
}

function formatCount(n: number): string {
  return n.toLocaleString("en-US");
}

// ============================================================
// 主组件
// ============================================================

export function LibraryPage() {
  const { tr } = useI18n();

  // 平台/类型筛选选项（label 走 i18n，lang 切换时随 tr 重建）
  const platformOptions = useMemo(
    () => [
      { value: "all", label: tr("library_filter_all_platform") },
      { value: "youtube", label: "YouTube" },
      { value: "instagram", label: "Instagram" },
      { value: "x", label: "X" },
      { value: "bilibili", label: tr("platform_bilibili") },
      { value: "douyin", label: tr("platform_douyin") },
      { value: "kuaishou", label: tr("platform_kuaishou") },
      { value: "weibo", label: tr("platform_weibo") },
      { value: "xiaohongshu", label: tr("platform_xiaohongshu") },
    ],
    [tr]
  );

  const typeOptions = useMemo(
    () => [
      { value: "all", label: tr("library_filter_all_type") },
      { value: "video", label: tr("library_filter_video") },
      { value: "audio", label: tr("library_filter_audio") },
      { value: "image", label: tr("library_filter_image") },
    ],
    [tr]
  );

  // —— 数据状态 ——
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [collections, setCollections] = useState<LibraryCollection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // —— 筛选状态（与 QML root 属性对齐） ——
  const [searchText, setSearchText] = useState("");
  const [filterPlatform, setFilterPlatform] = useState("all");
  const [filterType, setFilterType] = useState("all");
  // -1 = All Items, -2 = Favorites, >0 = 指定 Collection
  const [activeCollectionId, setActiveCollectionId] = useState(-1);

  // —— 对话框 / 菜单状态 ——
  const [newCollectionOpen, setNewCollectionOpen] = useState(false);
  const [renameCollection, setRenameCollection] = useState<{
    id: number;
    name: string;
  } | null>(null);
  const [confirmDeleteCollection, setConfirmDeleteCollection] = useState<{
    id: number;
    name: string;
  } | null>(null);
  const [fileMissing, setFileMissing] = useState<{
    path: string;
    itemId: string;
  } | null>(null);

  // —— 「加入 Collection」菜单 ——
  // 以卡片上的 + 按钮为锚点弹出
  const [collectionMenu, setCollectionMenu] = useState<{
    itemId: string;
    joinedIds: number[];
    anchor: { x: number; y: number };
  } | null>(null);

  // 在事件回调中引用最新 items，用于 file_missing 反查 item_id
  const itemsRef = useRef<LibraryItem[]>([]);
  itemsRef.current = items;

  // —— 拉取数据 ——
  const reload = useCallback(async () => {
    try {
      const [its, cols] = await Promise.all([
        api.getLibrary(),
        api.getCollections(),
      ]);
      setItems(its);
      setCollections(cols);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // —— 初次加载 ——
  useEffect(() => {
    reload();
  }, [reload]);

  // —— WebSocket 事件订阅 ——
  useEffect(() => {
    const unsub = subscribeEvents((e: AppEvent) => {
      switch (e.type) {
        case "library_changed":
        case "library_record_added":
          reload();
          break;

        case "file_missing": {
          // 文件被外部删除 → 弹「是否删除本条记录」对话框
          const p = e.data as { path?: string; source?: string } | null;
          if (!p || p.source !== "library" || !p.path) break;
          const it = itemsRef.current.find((i) => i.file_path === p.path);
          setFileMissing({
            path: p.path,
            itemId: it?.id || "",
          });
          break;
        }

        default:
          break;
      }
    });
    return unsub;
  }, [reload]);

  // —— 收藏筛选（activeCollectionId === -2 时启用） ——
  const filterFavorites = activeCollectionId === -2;

  // —— 客户端筛选（与 QML _applyFilter 对齐） ——
  const filtered = useMemo(() => {
    const q = searchText.toLowerCase();
    return items.filter((it) => {
      if (filterFavorites && !it.is_favorite) return false;
      if (filterPlatform !== "all" && it.platform !== filterPlatform) return false;
      if (filterType !== "all" && it.media_type !== filterType) return false;
      // Collection 筛选：仅当指定了具体 Collection 时生效
      if (activeCollectionId > 0) {
        const cids = it.collection_ids || [];
        if (!cids.includes(activeCollectionId)) return false;
      }
      // 搜索
      if (q.length > 0) {
        const hay = (
          (it.title || "") +
          " " +
          (it.author || "") +
          " " +
          (it.url || "")
        ).toLowerCase();
        if (hay.indexOf(q) < 0) return false;
      }
      return true;
    });
  }, [items, searchText, filterPlatform, filterType, filterFavorites, activeCollectionId]);

  // —— 统计 ——
  const totalSize = useMemo(
    () => items.reduce((s, it) => s + (it.file_size || 0), 0),
    [items]
  );
  const favoritesCount = useMemo(
    () => items.filter((it) => it.is_favorite).length,
    [items]
  );

  // —— 单项操作 ——
  const onToggleFavorite = useCallback(async (itemId: string) => {
    // 乐观更新：立即翻转 UI，不等 library_changed 信号
    setItems((prev) =>
      prev.map((it) =>
        it.id === itemId ? { ...it, is_favorite: !it.is_favorite } : it
      )
    );
    try {
      await api.toggleFavorite(itemId);
      // 后端不再发 library_changed 信号（避免全量刷新闪烁）
    } catch (e) {
      console.warn("toggle favorite failed:", e);
      // 失败时回滚
      setItems((prev) =>
        prev.map((it) =>
          it.id === itemId ? { ...it, is_favorite: !it.is_favorite } : it
        )
      );
    }
  }, []);

  const onDeleteItem = useCallback(async (itemId: string) => {
    try {
      await api.deleteLibraryItem(itemId);
      // 后端会推 library_changed 事件触发 reload
    } catch (e) {
      console.warn("delete library item failed:", e);
    }
  }, []);

  const onOpenFile = useCallback(async (path: string) => {
    try {
      await api.openFile(path, "library");
    } catch (e) {
      console.warn("open file failed:", e);
    }
  }, []);

  const onOpenFolder = useCallback(async (path: string) => {
    try {
      await api.openFolder(path, "library");
    } catch (e) {
      console.warn("open folder failed:", e);
    }
  }, []);

  // —— Collection 操作 ——
  const onCreateCollection = useCallback(
    async (name: string) => {
      if (!name.trim()) {
        setNewCollectionOpen(false);
        return;
      }
      try {
        await api.createCollection(name.trim());
        // 后端会推 library_changed
      } catch (e) {
        console.warn("create collection failed:", e);
      }
      setNewCollectionOpen(false);
    },
    []
  );

  const onRenameCollection = useCallback(
    async (cid: number, name: string) => {
      if (!name.trim()) {
        setRenameCollection(null);
        return;
      }
      try {
        await api.renameCollection(cid, name.trim());
      } catch (e) {
        console.warn("rename collection failed:", e);
      }
      setRenameCollection(null);
    },
    []
  );

  const onDeleteCollection = useCallback(async (cid: number) => {
    try {
      await api.deleteCollection(cid);
      // 如果当前在删掉的分类视图下，切回 All Items
      if (activeCollectionId === cid) {
        setActiveCollectionId(-1);
      }
    } catch (e) {
      console.warn("delete collection failed:", e);
    }
    setConfirmDeleteCollection(null);
  }, [activeCollectionId]);

  // —— 「加入 Collection」菜单 ——
  const onShowCollectionMenu = useCallback(
    async (itemId: string, anchor: { x: number; y: number }) => {
      try {
        const joinedIds = await api.getItemCollections(itemId);
        setCollectionMenu({ itemId, joinedIds, anchor });
      } catch (e) {
        console.warn("get item collections failed:", e);
        setCollectionMenu({ itemId, joinedIds: [], anchor });
      }
    },
    []
  );

  const onToggleItemCollection = useCallback(
    async (itemId: string, cid: number, isJoined: boolean) => {
      try {
        if (isJoined) {
          await api.removeItemFromCollection(itemId, cid);
        } else {
          await api.addItemToCollection(itemId, cid);
        }
        // 更新菜单中的 joinedIds
        setCollectionMenu((prev) => {
          if (!prev || prev.itemId !== itemId) return prev;
          const newIds = isJoined
            ? prev.joinedIds.filter((id) => id !== cid)
            : [...prev.joinedIds, cid];
          return { ...prev, joinedIds: newIds };
        });
      } catch (e) {
        console.warn("toggle item collection failed:", e);
      }
    },
    []
  );

  // —— 一键重置筛选 ——
  const onResetFilters = useCallback(() => {
    setSearchText("");
    setFilterPlatform("all");
    setFilterType("all");
    setActiveCollectionId(-1);
  }, []);

  // —— file_missing 确认删除 ——
  const onConfirmFileMissingDelete = useCallback(async () => {
    const id = fileMissing?.itemId;
    setFileMissing(null);
    if (id) {
      try {
        await api.deleteLibraryItem(id);
      } catch (e) {
        console.warn("delete missing-item failed:", e);
      }
    }
  }, [fileMissing]);

  // —— 渲染 ——
  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-text-muted">{tr("loading")}</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="glass-card max-w-md p-6">
          <h2 className="text-lg font-semibold text-danger">{tr("load_failed")}</h2>
          <p className="mt-2 text-sm text-text-muted">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div
      className="flex h-full"
      onClick={() => {
        // 点击页面任意位置关闭 Collection 菜单
        if (collectionMenu) setCollectionMenu(null);
      }}
    >
      {/* ============================================================ */}
      {/* Collections 左侧栏 — 收窄到 180px，去掉 glass-card 改为透明背景 + 细分隔线 */}
      {/* ============================================================ */}
      <aside className="flex w-[180px] shrink-0 flex-col gap-1 border-r border-text/10 bg-transparent px-2.5 py-4">
        {/* 顶部标题 + 新建按钮 */}
        <div className="mb-2 flex items-center justify-between px-1.5">
          <span className="text-[10px] font-bold uppercase tracking-wider text-text-dim">
            {tr("collections")}
          </span>
          <button
            onClick={() => setNewCollectionOpen(true)}
            className="flex h-5 w-5 items-center justify-center rounded text-text-muted transition-colors hover:bg-text/10 hover:text-text"
            title={tr("collection_create")}
          >
            +
          </button>
        </div>

        {/* All Items */}
        <CollectionSidebarItem
          active={activeCollectionId === -1}
          icon="📚"
          label={tr("all_items")}
          count={items.length}
          onClick={() => setActiveCollectionId(-1)}
        />

        {/* Favorites */}
        <CollectionSidebarItem
          active={activeCollectionId === -2}
          icon="❤"
          label={tr("favorites")}
          count={favoritesCount}
          onClick={() => setActiveCollectionId(-2)}
        />

        {/* 分隔线 */}
        <div className="my-1.5 h-px bg-text/10" />

        {/* User Collections */}
        {collections.length === 0 ? (
          <div className="px-2.5 py-1.5 text-xs text-text-dim">
            {tr("no_collections")}
          </div>
        ) : (
          collections.map((c) => (
            <CollectionSidebarItem
              key={c.id}
              active={activeCollectionId === c.id}
              icon="📁"
              label={c.name}
              count={c.count}
              onClick={() => setActiveCollectionId(c.id)}
              onContextMenu={(e) => {
                e.preventDefault();
                setRenameCollection({ id: c.id, name: c.name });
              }}
            />
          ))
        )}

        <div className="flex-1" />
      </aside>

      {/* ============================================================ */}
      {/* 媒体网格主区 */}
      {/* ============================================================ */}
      <main className="flex min-w-0 flex-1 flex-col gap-4 p-4 pl-0">
        {/* PageHeader */}
        <header className="flex animate-slide-up items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-text">{tr("library_title")}</h1>
            <p className="mt-0.5 text-xs text-text-muted">
              {tr("library_subtitle")}
            </p>
          </div>
          {/* 统计 badge */}
          <div className="rounded-full border border-accent/30 bg-accent/15 px-2.5 py-1 text-xs font-semibold text-accent">
            {formatCount(items.length)} 条 · {formatSize(totalSize)}
          </div>
        </header>

        {/* Filter bar */}
        <div className="glass-card flex items-center gap-2.5 px-3.5 py-2.5">
          <input
            type="text"
            placeholder={tr("library_search")}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="flex-1 rounded-lg border border-text/15 bg-bg-surface px-3 py-1.5 text-sm text-text shadow-sm transition-colors hover:border-text/25 placeholder:text-text-dim focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/40"
          />
          <select
            value={filterPlatform}
            onChange={(e) => setFilterPlatform(e.target.value)}
            className="w-36 rounded-lg border border-text/15 bg-bg-surface px-3 py-1.5 text-sm text-text shadow-sm transition-colors hover:border-text/25 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/40"
          >
            {platformOptions.map((o) => (
              <option key={o.value} value={o.value} className="bg-bg-surface text-text">
                {o.label}
              </option>
            ))}
          </select>
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="w-28 rounded-lg border border-text/15 bg-bg-surface px-3 py-1.5 text-sm text-text shadow-sm transition-colors hover:border-text/25 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/40"
          >
            {typeOptions.map((o) => (
              <option key={o.value} value={o.value} className="bg-bg-surface text-text">
                {o.label}
              </option>
            ))}
          </select>
          <button
            onClick={onResetFilters}
            className="rounded-lg px-3 py-1.5 text-xs font-medium text-text-muted transition-colors hover:bg-white/5 hover:text-text"
            title={tr("library_reset_filters")}
          >
            {tr("library_reset_filters")}
          </button>
        </div>

        {/* 空状态 */}
        {items.length === 0 && (
          <div className="mt-20 text-center text-sm text-text-muted">
            {tr("library_empty")}
          </div>
        )}

        {/* 筛选后无结果 */}
        {items.length > 0 && filtered.length === 0 && (
          <div className="mt-20 text-center text-sm text-text-muted">
            没有匹配的素材
          </div>
        )}

        {/* 媒体网格 — 3 列固定布局 */}
        {filtered.length > 0 && (
          <div
            className="min-h-0 flex-1 overflow-y-auto"
            style={{
              // 提升为合成层，滚动时独立于背景层重绘
              willChange: "scroll-position",
              // 滚动到边界不冒泡到父级，避免触发整体 layout
              overscrollBehavior: "contain",
              // 触摸设备惯性滚动
              WebkitOverflowScrolling: "touch",
            }}
          >
            <div
              className="grid grid-cols-3 gap-6 p-1"
              style={{
                // 让浏览器跳过不可见卡片的渲染工作（大幅提升滚动性能）
                // paint + size 让 contain 更完整
                contain: "layout style paint",
              }}
            >
              {filtered.map((it) => (
                <LibraryCard
                  key={it.id}
                  item={it}
                  activeCollectionId={activeCollectionId}
                  onToggleFavorite={onToggleFavorite}
                  onDelete={onDeleteItem}
                  onOpenFile={onOpenFile}
                  onOpenFolder={onOpenFolder}
                  onShowCollectionMenu={onShowCollectionMenu}
                />
              ))}
            </div>
            {/* 底部 spacer */}
            <div className="h-12" />
          </div>
        )}
      </main>

      {/* ============================================================ */}
      {/* 对话框 / 菜单 */}
      {/* ============================================================ */}

      {/* 新建 Collection 对话框 */}
      {newCollectionOpen && (
        <CollectionNameDialog
          title={tr("collection_create")}
          onCancel={() => setNewCollectionOpen(false)}
          onConfirm={onCreateCollection}
        />
      )}

      {/* 重命名 Collection 对话框 */}
      {renameCollection && (
        <CollectionNameDialog
          title={tr("collection_rename")}
          initialName={renameCollection.name}
          onCancel={() => setRenameCollection(null)}
          onConfirm={(name) => onRenameCollection(renameCollection.id, name)}
        />
      )}

      {/* 删除 Collection 确认 */}
      {confirmDeleteCollection && (
        <ModalDialog
          title={tr("collection_delete")}
          onClose={() => setConfirmDeleteCollection(null)}
        >
          <p className="text-sm text-text">
            确定要删除 Collection「{confirmDeleteCollection.name}」吗？
          </p>
          <p className="mt-2 text-xs text-text-muted">
            注意：仅删除分类本身，不会删除分类下的素材文件。
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <button
              onClick={() => setConfirmDeleteCollection(null)}
              className="rounded-lg bg-white/5 px-4 py-1.5 text-sm font-medium text-text-muted transition-colors hover:bg-white/10 hover:text-text"
            >
              {tr("cancel")}
            </button>
            <button
              onClick={() => onDeleteCollection(confirmDeleteCollection.id)}
              className="rounded-lg bg-danger px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-danger-glow"
            >
              {tr("delete")}
            </button>
          </div>
        </ModalDialog>
      )}

      {/* 文件缺失对话框 */}
      {fileMissing && (
        <ModalDialog
          title={tr("file_missing_title")}
          onClose={() => setFileMissing(null)}
        >
          <p className="text-sm font-semibold text-danger">
            文件已被外部删除或移动
          </p>
          <p className="mt-2 text-xs text-text">是否删除这条素材记录？</p>
          <p className="mt-2 break-all rounded-md bg-white/5 px-2 py-1.5 font-mono text-[10px] text-text-dim">
            {fileMissing.path}
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <button
              onClick={() => setFileMissing(null)}
              className="rounded-lg bg-white/5 px-4 py-1.5 text-sm font-medium text-text-muted transition-colors hover:bg-white/10 hover:text-text"
            >
              {tr("cancel")}
            </button>
            <button
              onClick={onConfirmFileMissingDelete}
              disabled={!fileMissing.itemId}
              className="rounded-lg bg-danger px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-danger-glow disabled:opacity-40"
            >
              删除记录
            </button>
          </div>
        </ModalDialog>
      )}

      {/* 「加入 Collection」菜单 */}
      {collectionMenu && (
        <CollectionMenu
          menu={collectionMenu}
          collections={collections}
          onToggle={(cid, isJoined) =>
            onToggleItemCollection(collectionMenu.itemId, cid, isJoined)
          }
          onCreateNew={() => {
            setCollectionMenu(null);
            setNewCollectionOpen(true);
          }}
          onClose={() => setCollectionMenu(null)}
        />
      )}
    </div>
  );
}

// ============================================================
// 子组件：Collection 左侧栏项
// ============================================================

interface CollectionSidebarItemProps {
  active: boolean;
  icon: string;
  label: string;
  count: number;
  onClick: () => void;
  onContextMenu?: (e: React.MouseEvent) => void;
}

function CollectionSidebarItem({
  active,
  icon,
  label,
  count,
  onClick,
  onContextMenu,
}: CollectionSidebarItemProps) {
  return (
    <div
      onClick={onClick}
      onContextMenu={onContextMenu}
      className={`flex h-9 cursor-pointer items-center gap-2.5 rounded-lg px-2.5 transition-colors ${
        active ? "bg-text/10" : "hover:bg-text/[0.06]"
      }`}
    >
      <span
        className={`text-xs ${active ? "text-text" : "text-text-muted"}`}
      >
        {icon}
      </span>
      <span
        className={`flex-1 truncate text-xs ${
          active ? "text-text" : "text-text-muted"
        }`}
      >
        {label}
      </span>
      <span className="font-mono text-[10px] text-text-dim">
        {count}
      </span>
    </div>
  );
}

// ============================================================
// 子组件：素材卡片
// ============================================================

interface LibraryCardProps {
  item: LibraryItem;
  activeCollectionId: number;
  onToggleFavorite: (itemId: string) => void;
  onDelete: (itemId: string) => void;
  onOpenFile: (path: string) => void;
  onOpenFolder: (path: string) => void;
  onShowCollectionMenu: (
    itemId: string,
    anchor: { x: number; y: number }
  ) => void;
}

function LibraryCardInner({
  item,
  activeCollectionId,
  onToggleFavorite,
  onDelete,
  onOpenFile,
  onOpenFolder,
  onShowCollectionMenu,
}: LibraryCardProps) {
  const { tr } = useI18n();

  // 本地缩略图优先（thumbnail_path 是本地路径），否则用远程 URL 走 thumb-proxy
  const localThumb = item.thumbnail_path || "";
  const remoteThumb = item.thumbnail_url || "";
  const thumbSrc = localThumb
    ? lumioFileUrl(localThumb)
    : remoteThumb
    ? thumbProxyUrl(remoteThumb)
    : "";

  const typeBadge = typeBadgeClass(item.media_type, tr);
  const isInActiveCollection =
    activeCollectionId > 0 &&
    (item.collection_ids || []).includes(activeCollectionId);

  return (
    <div
      className="library-card flex h-[260px] flex-col overflow-hidden"
      style={{
        // 卡片不在视口内时跳过渲染（contain-intrinsic-size 给占位高度防滚动条抖动）
        contentVisibility: "auto",
        containIntrinsicSize: "260px",
      }}
    >
      {/* 封面区 */}
      <div className="relative mx-2.5 mt-2.5 h-[150px] overflow-hidden rounded-lg bg-black/30">
        {thumbSrc ? (
          <img
            src={thumbSrc}
            alt=""
            loading="lazy"
            decoding="async"
            className="h-full w-full object-cover"
            onError={(e) => {
              // 清空 src 避免下次挂载重新请求失败 URL
              const img = e.currentTarget as HTMLImageElement;
              img.onerror = null;
              img.src = "";
              img.style.display = "none";
            }}
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-3xl text-white/40">
            {item.media_type === "audio"
              ? "🎵"
              : item.media_type === "image"
              ? "🖼"
              : "🎬"}
          </div>
        )}

        {/* 收藏按钮（右上） */}
        <button
          onClick={() => onToggleFavorite(item.id)}
          className="absolute right-1.5 top-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-black/50 backdrop-blur transition-colors hover:bg-black/70"
          title={item.is_favorite ? tr("unfavorite") : tr("favorite")}
        >
          <span
            className={`text-xs ${
              item.is_favorite ? "text-danger" : "text-zinc-400"
            }`}
          >
            ❤
          </span>
        </button>
      </div>

      {/* 信息区 */}
      <div className="mt-2.5 flex-1 px-3">
        {/* 标题 */}
        <div className="truncate text-sm font-semibold text-text">
          {item.title || "(无标题)"}
        </div>
        {/* 作者 + 大小 */}
        <div className="mt-1 truncate font-mono text-[10px] text-text-muted">
          {item.author || "—"} · {formatSize(item.file_size)}
        </div>
        {/* 徽章行 */}
        <div className="mt-1.5 flex gap-1">
          {item.platform && (
            <span className="rounded bg-black/40 px-1.5 py-0.5 font-mono text-[9px] font-semibold">
              <span className={platformColor(item.platform)}>
                {platformLabel(item.platform, tr)}
              </span>
            </span>
          )}
          {item.media_type && (
            <span
              className={`rounded px-1.5 py-0.5 font-mono text-[9px] font-semibold ${typeBadge.bg} ${typeBadge.text}`}
            >
              {typeBadge.label}
            </span>
          )}
        </div>
      </div>

      {/* 操作栏（锚定底部） */}
      <div className="flex items-center gap-0.5 px-2 pb-2">
        <button
          onClick={() => onOpenFile(item.file_path)}
          disabled={!item.file_path}
          className="flex h-7 w-9 items-center justify-center rounded text-text-muted transition-colors hover:bg-white/10 hover:text-text disabled:opacity-30"
          title={tr("library_open_file")}
        >
          ▶
        </button>
        <button
          onClick={() => onOpenFolder(item.file_path)}
          disabled={!item.file_path}
          className="flex h-7 w-9 items-center justify-center rounded text-text-muted transition-colors hover:bg-white/10 hover:text-text disabled:opacity-30"
          title={tr("library_open_dir")}
        >
          📂
        </button>
        <button
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            onShowCollectionMenu(item.id, {
              x: rect.left + rect.width / 2,
              y: rect.bottom + 4,
            });
          }}
          className="flex h-7 w-9 items-center justify-center rounded text-text-muted transition-colors hover:bg-white/10 hover:text-text"
          title={isInActiveCollection ? tr("collection_remove") : tr("collection_add_to")}
        >
          {isInActiveCollection ? "✕" : "📁+"}
        </button>
        <div className="w-1" />
        <button
          onClick={() => onDelete(item.id)}
          className="flex h-7 w-9 items-center justify-center rounded text-text-muted transition-colors hover:bg-danger/10 hover:text-danger"
          title={tr("library_delete")}
        >
          🗑
        </button>
      </div>
    </div>
  );
}

/**
 * 用 React.memo 包裹 LibraryCard，仅在 props 真正变化时重渲染。
 * 父组件的 searchText / filterPlatform 等状态变化导致 items 数组重建时，
 * memo 会逐项对比 item 引用，未变化的卡片直接跳过渲染。
 */
const LibraryCard = memo(LibraryCardInner);

// ============================================================
// 子组件：Collection 菜单（加入/移除）
// ============================================================

interface CollectionMenuProps {
  menu: {
    itemId: string;
    joinedIds: number[];
    anchor: { x: number; y: number };
  };
  collections: LibraryCollection[];
  onToggle: (cid: number, isJoined: boolean) => void;
  onCreateNew: () => void;
  onClose: () => void;
}

function CollectionMenu({
  menu,
  collections,
  onToggle,
  onCreateNew,
  onClose,
}: CollectionMenuProps) {
  const { tr } = useI18n();

  // 计算菜单位置：以 anchor.x 为右边界，避免溢出右侧
  const MENU_WIDTH = 220;
  const left = Math.max(8, menu.anchor.x - MENU_WIDTH);
  const top = menu.anchor.y;

  return (
    <>
      {/* 背景遮罩（点击关闭） */}
      <div className="fixed inset-0 z-40" onClick={onClose} />

      {/* 菜单 */}
      <div
        className="glass-card fixed z-50 w-[220px] p-1.5"
        style={{ left, top }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 新建 Collection */}
        <button
          onClick={onCreateNew}
          className="flex h-8 w-full items-center rounded px-3 text-xs text-text transition-colors hover:bg-accent/15 hover:text-accent"
        >
          {tr("collection_create")}
        </button>

        <div className="my-1 h-px bg-white/5" />

        {/* 已有 Collection 列表 */}
        {collections.length === 0 ? (
          <div className="px-3 py-2 text-xs text-text-dim">
            {tr("no_collections")}
          </div>
        ) : (
          collections.map((c) => {
            const joined = menu.joinedIds.includes(c.id);
            return (
              <button
                key={c.id}
                onClick={() => onToggle(c.id, joined)}
                className="flex h-8 w-full items-center gap-2 rounded px-3 text-xs text-text transition-colors hover:bg-white/10"
              >
                <span
                  className={`w-3.5 font-mono font-bold text-success ${
                    joined ? "opacity-100" : "opacity-0"
                  }`}
                >
                  ✓
                </span>
                <span className="flex-1 truncate text-left">
                  {c.name} ({c.count})
                </span>
              </button>
            );
          })
        )}
      </div>
    </>
  );
}

// ============================================================
// 子组件：Collection 名称对话框（新建/重命名共用）
// ============================================================

interface CollectionNameDialogProps {
  title: string;
  initialName?: string;
  onCancel: () => void;
  onConfirm: (name: string) => void;
}

function CollectionNameDialog({
  title,
  initialName = "",
  onCancel,
  onConfirm,
}: CollectionNameDialogProps) {
  const { tr } = useI18n();
  const [name, setName] = useState(initialName);

  return (
    <ModalDialog title={title} onClose={onCancel}>
      <input
        type="text"
        autoFocus
        placeholder={tr("collection_name_label")}
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") onConfirm(name);
          if (e.key === "Escape") onCancel();
        }}
        className="w-full rounded-lg border border-white/5 bg-white/5 px-3 py-2 text-sm text-text placeholder:text-text-dim focus:border-accent/50 focus:outline-none"
      />
      <div className="mt-5 flex justify-end gap-2">
        <button
          onClick={onCancel}
          className="rounded-lg bg-white/5 px-4 py-1.5 text-sm font-medium text-text-muted transition-colors hover:bg-white/10 hover:text-text"
        >
          {tr("cancel")}
        </button>
        <button
          onClick={() => onConfirm(name)}
          disabled={!name.trim()}
          className="rounded-lg bg-accent px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-accent-glow disabled:opacity-40"
        >
          确认
        </button>
      </div>
    </ModalDialog>
  );
}

// ============================================================
// 简易模态对话框（与 HistoryPage 同款，复制以避免跨页面耦合）
// ============================================================

function ModalDialog({
  title,
  children,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="glass-card w-[420px] max-w-[90vw] p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-3 text-base font-semibold text-text">{title}</h2>
        {children}
      </div>
    </div>
  );
}
