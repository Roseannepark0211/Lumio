/**
 * 前端 i18n loader — 与后端 src/lumio/i18n.py 的翻译字典对齐。
 *
 * 设计：
 *   - 启动时一次性拉 /api/i18n 缓存到内存（避免每次 tr() 都走网络）
 *   - 同时拉 /api/config 取当前 lang 字段
 *   - 监听 WS `lang_changed` 事件，自动切换 lang 并触发 re-render
 *   - setLang(lang) 调 api.setLang → 后端发 lang_changed → 自动刷新
 *
 * 用法：
 *   <I18nProvider><App /></I18nProvider>
 *   const { tr, lang, setLang } = useI18n();
 *   tr("home")  // → "主页" / "Home"
 *   tr("videos", { n: 3 })  // → "3 个视频" / "3 video(s)"
 *
 * 模板占位符与后端 i18n.py 一致：`{name}` 形式（不支持 `{0}` 位置参数，
 * 前端调用统一用 keyword）。
 */
import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, subscribeEvents, type AppEvent } from "./api";

export type Lang = "zh" | "en";

interface I18nContextValue {
  /** 当前语言 */
  lang: Lang;
  /** 翻译字典是否已加载完成（启动时拉 /api/i18n 期间为 false） */
  ready: boolean;
  /** 切换语言（调后端 → 后端发 lang_changed 事件 → 自动刷新） */
  setLang: (lang: Lang) => Promise<void>;
  /** 翻译函数。找不到 key 时回退到 key 本身（与后端 t() 一致） */
  tr: (key: string, params?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue>({
  lang: "zh",
  ready: false,
  setLang: async () => {},
  tr: (k) => k,
});

export const useI18n = () => useContext(I18nContext);

/** 完整翻译字典：{ zh: {key: text}, en: {key: text} } */
type TranslationTable = Record<Lang, Record<string, string>>;

/** 模板变量替换 — 与后端 i18n.py 的 `text.format(**kwargs)` 对齐 */
function formatTemplate(text: string, params?: Record<string, string | number>): string {
  if (!params) return text;
  // 用正则替换 {name} 占位符，避免 format() 对 `{` `}` 报错
  return text.replace(/\{(\w+)\}/g, (m, key: string) => {
    if (Object.prototype.hasOwnProperty.call(params, key)) {
      return String(params[key]);
    }
    return m; // 找不到占位符变量，保留原文
  });
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [table, setTable] = useState<TranslationTable | null>(null);
  const [lang, setLangState] = useState<Lang>("zh");

  // 启动时拉翻译字典 + 当前语言
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [i18nTable, cfg] = await Promise.all([api.getI18n(), api.getConfig()]);
        if (cancelled) return;
        setTable(i18nTable as TranslationTable);
        const l = (cfg as { lang?: string }).lang;
        if (l === "zh" || l === "en") setLangState(l);
      } catch {
        // 拉失败时保持默认 zh，tr() 会回退到 key 本身
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // 监听 lang_changed 事件 — 后端 setLang 后会推送
  useEffect(() => {
    const unsub = subscribeEvents((e: AppEvent) => {
      if (e.type === "lang_changed") {
        const l = (e.data as { lang?: string })?.lang;
        if (l === "zh" || l === "en") setLangState(l);
      }
    });
    return unsub;
  }, []);

  const setLang = useCallback(async (next: Lang) => {
    // 乐观更新：立即切换 lang state，让所有 consumer 同步 re-render
    // 不依赖 WS lang_changed 事件（事件可能延迟或丢失）
    setLangState(next);
    try {
      await api.setLang(next);
      // 后端会发 lang_changed 事件，但 lang 已经是 next，setLangState 是幂等的
    } catch {
      // 失败时静默 — 由调用方 toast；lang 保持乐观更新的值
    }
  }, []);

  const tr = useCallback(
    (key: string, params?: Record<string, string | number>) => {
      if (!table) return key; // 字典未加载完，回退到 key
      const dict = table[lang] || table.zh;
      const text = dict[key] || table.zh[key] || key;
      return formatTemplate(text, params);
    },
    [table, lang]
  );

  const value: I18nContextValue = {
    lang,
    ready: table !== null,
    setLang,
    tr,
  };

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
