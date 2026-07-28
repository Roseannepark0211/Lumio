/**
 * 历史记录管理 — IndexedDB（idb-keyval 极简封装）
 *
 * 容量：200 条（每条含缩略图 base64 约 50KB，总计约 10MB，IndexedDB 配额充足）
 * Schema：HistoryItem
 */
import { get, set, del } from "idb-keyval";
import type { HistoryItem, PageMeta, CaptureResult } from "../types";

const HISTORY_PREFIX = "lumio_history_";
const HISTORY_INDEX_KEY = "lumio_history_index"; // 存储 id 列表，按时间倒序

interface HistoryIndex {
  ids: string[]; // 倒序（最新在前）
}

async function getIndex(): Promise<HistoryIndex> {
  return (await get<HistoryIndex>(HISTORY_INDEX_KEY)) || { ids: [] };
}

async function setIndex(index: HistoryIndex): Promise<void> {
  await set(HISTORY_INDEX_KEY, index);
}

/** 生成历史记录 ID */
function genId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

/** 保存一条历史记录 */
export async function saveToHistory(
  meta: PageMeta,
  result: CaptureResult,
): Promise<HistoryItem | null> {
  if (!result.success) return null;

  const id = genId();
  const item: HistoryItem = {
    ...meta,
    id,
    time: Date.now(),
    inbox_id: result.inbox_id,
    status: "pending",
  };

  await set(`${HISTORY_PREFIX}${id}`, item);

  // 更新索引（最新在前，最多 200 条）
  const index = await getIndex();
  index.ids.unshift(id);
  if (index.ids.length > 200) {
    // 删除溢出的旧记录
    const removed = index.ids.splice(200);
    for (const oldId of removed) {
      await del(`${HISTORY_PREFIX}${oldId}`);
    }
  }
  await setIndex(index);

  return item;
}

/** 获取最近 N 条历史记录 */
export async function getRecentHistory(limit = 50): Promise<HistoryItem[]> {
  const index = await getIndex();
  const ids = index.ids.slice(0, limit);
  const items: HistoryItem[] = [];
  for (const id of ids) {
    const item = await get<HistoryItem>(`${HISTORY_PREFIX}${id}`);
    if (item) items.push(item);
  }
  return items;
}

/** 获取单条历史记录 */
export async function getHistoryItem(id: string): Promise<HistoryItem | undefined> {
  return get<HistoryItem>(`${HISTORY_PREFIX}${id}`);
}

/** 删除单条历史记录 */
export async function deleteHistoryItem(id: string): Promise<void> {
  await del(`${HISTORY_PREFIX}${id}`);
  const index = await getIndex();
  index.ids = index.ids.filter((x) => x !== id);
  await setIndex(index);
}

/** 清空所有历史记录 */
export async function clearHistory(): Promise<void> {
  const index = await getIndex();
  for (const id of index.ids) {
    await del(`${HISTORY_PREFIX}${id}`);
  }
  await del(HISTORY_INDEX_KEY);
}

/** 批量删除 */
export async function deleteHistoryItems(ids: string[]): Promise<void> {
  for (const id of ids) {
    await del(`${HISTORY_PREFIX}${id}`);
  }
  const index = await getIndex();
  const idSet = new Set(ids);
  index.ids = index.ids.filter((x) => !idSet.has(x));
  await setIndex(index);
}

/** 获取历史总数 */
export async function getHistoryCount(): Promise<number> {
  const index = await getIndex();
  return index.ids.length;
}
