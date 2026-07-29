/**
 * 判断 URL 是否为详情页（需要元数据才能发送）
 *
 * background 和 popup 共用同一份实现，避免重复维护
 */
export function isDetailPageUrl(url: string): boolean {
  if (!url) return false;
  // YouTube /watch, IG /p/ 或 /reel/, X /status/, B站 /video/, 小红书 /explore/ 或 /discovery/item/
  // 抖音 /video/{id} 或 /note/{id}（注意：B站也是 /video/，但 B站要求 BV/av 前缀）
  // ★ 抖音 modal 模式：/jingxuan?modal_id={id}、/follow?modal_id={id} 等
  //   用户在精选页/关注页点视频会弹出 modal，URL 加 modal_id 参数
  return (
    url.includes("/watch") ||
    /\/(p|reel)\//.test(url) ||
    /\/status\//.test(url) ||
    /\/video\/(BV|av)/i.test(url) ||
    /\/(explore|discovery\/item)\//.test(url) ||
    /douyin\.com\/(video|note)\//.test(url) ||
    /douyin\.com\/[^?]*[?&]modal_id=\d+/.test(url) ||
    // 微博详情页：weibo.com/{uid}/{post_id} 或 m.weibo.cn/status/{post_id} 或 weibo.com/detail/{id}
    // 排除主页 (weibo.com/u/{uid}) 和搜索/列表
    /weibo\.com\/\d+\/[a-zA-Z0-9]+/.test(url) ||
    /m\.weibo\.cn\/(status|detail)\/[a-zA-Z0-9]+/.test(url) ||
    /weibo\.com\/detail\/[a-zA-Z0-9]+/.test(url)
  );
}
