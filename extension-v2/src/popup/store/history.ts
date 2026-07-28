/**
 * 历史记录状态管理（Zustand）
 */
import { create } from "zustand";
import type { HistoryItem } from "../../types";

interface HistoryState {
  items: HistoryItem[];
  loading: boolean;
  selectedIds: Set<string>;
  multiSelectMode: boolean;

  load: () => Promise<void>;
  toggleSelect: (id: string) => void;
  selectAll: () => void;
  clearSelection: () => void;
  setMultiSelectMode: (on: boolean) => void;
  deleteItem: (id: string) => Promise<void>;
  deleteSelected: () => Promise<void>;
  resendItem: (id: string) => Promise<boolean>;
  clearAll: () => Promise<void>;
}

export const useHistoryStore = create<HistoryState>((set, get) => ({
  items: [],
  loading: false,
  selectedIds: new Set(),
  multiSelectMode: false,

  load: async () => {
    set({ loading: true });
    const items = (await chrome.runtime.sendMessage({
      type: "getHistory",
      limit: 50,
    })) as HistoryItem[] | undefined;
    set({ items: items || [], loading: false });
  },

  toggleSelect: (id) => {
    const next = new Set(get().selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    set({ selectedIds: next });
  },

  selectAll: () => {
    set({ selectedIds: new Set(get().items.map((i) => i.id)) });
  },

  clearSelection: () => set({ selectedIds: new Set() }),

  setMultiSelectMode: (on) =>
    set({ multiSelectMode: on, selectedIds: on ? get().selectedIds : new Set() }),

  deleteItem: async (id) => {
    await chrome.runtime.sendMessage({ type: "deleteHistoryItem", id });
    await get().load();
  },

  deleteSelected: async () => {
    const ids = Array.from(get().selectedIds);
    if (ids.length === 0) return;
    await chrome.runtime.sendMessage({ type: "deleteHistoryItems", ids });
    set({ selectedIds: new Set(), multiSelectMode: false });
    await get().load();
  },

  resendItem: async (id) => {
    const result = (await chrome.runtime.sendMessage({
      type: "resendHistoryItem",
      id,
    })) as { success: boolean; error?: string } | undefined;
    return result?.success ?? false;
  },

  clearAll: async () => {
    await chrome.runtime.sendMessage({ type: "clearHistory" });
    await get().load();
  },
}));
