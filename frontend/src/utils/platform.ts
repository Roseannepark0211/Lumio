/**
 * 平台展示名 / 颜色映射工具（与 QML Theme.platformColor/platformLabel 对齐）。
 *
 * 各页面原本各自维护一份平台映射，此处统一收敛：
 * - 国外平台（YouTube/Instagram/X/Telegram）显示英文原名，不翻译
 * - 国内平台（B站/抖音/快手/微博/小红书）走 i18n tr() 调用
 */

/** 国外平台英文名（不需要翻译）。 */
const PLATFORM_LABEL_EN: Record<string, string> = {
  youtube: "YouTube",
  instagram: "Instagram",
  x: "X",
  telegram: "Telegram",
};

/** 国内平台 i18n key 映射。 */
const PLATFORM_I18N_KEY: Record<string, string> = {
  bilibili: "platform_bilibili",
  douyin: "platform_douyin",
  kuaishou: "platform_kuaishou",
  weibo: "platform_weibo",
  xiaohongshu: "platform_xiaohongshu",
};

/** 平台展示名（默认全称，如 "Instagram"）。 */
export function platformLabel(p: string, tr: (k: string) => string): string {
  if (!p) return "—";
  if (PLATFORM_LABEL_EN[p]) return PLATFORM_LABEL_EN[p];
  if (PLATFORM_I18N_KEY[p]) return tr(PLATFORM_I18N_KEY[p]);
  return p.toUpperCase();
}

/** 平台圆点颜色（纯 bg-* 类，用于 StatsPage 圆点）。 */
const PLATFORM_DOT_COLOR: Record<string, string> = {
  youtube: "bg-red-500",
  instagram: "bg-pink-500",
  x: "bg-zinc-200",
  bilibili: "bg-blue-500",
  douyin: "bg-zinc-100",
  kuaishou: "bg-orange-500",
  weibo: "bg-orange-600",
  xiaohongshu: "bg-red-600",
  telegram: "bg-sky-500",
  unknown: "bg-zinc-500",
};

/** 平台圆点颜色（与 QML Theme.platformColor 对齐）。 */
export function platformDotColor(p: string): string {
  return PLATFORM_DOT_COLOR[p] || "bg-zinc-500";
}
