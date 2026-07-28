/**
 * 判断 URL 是否为详情页（需要元数据才能发送）
 *
 * background 和 popup 共用同一份实现，避免重复维护
 */
export function isDetailPageUrl(url: string): boolean {
  if (!url) return false;
  // YouTube /watch, IG /p/ 或 /reel/, X /status/, B站 /video/, 小红书 /explore/ 或 /discovery/item/
  return (
    url.includes("/watch") ||
    /\/(p|reel)\//.test(url) ||
    /\/status\//.test(url) ||
    /\/video\/(BV|av)/i.test(url) ||
    /\/(explore|discovery\/item)\//.test(url)
  );
}
