/**
 * og:* meta 标签通用提取
 */

export function meta(prop: string): string {
  const el =
    document.querySelector(`meta[property='${prop}']`) ||
    document.querySelector(`meta[name='${prop}']`);
  return el?.getAttribute("content") || "";
}

interface OgInfo {
  title: string;
  thumbnail: string;
  author: string;
  duration: number | null;
}

export function commonOg(): OgInfo {
  return {
    title: meta("og:title") || document.title,
    thumbnail: meta("og:image") || "",
    author: "",
    duration: null,
  };
}

/** 从 JSON-LD 解析 duration（PT1H2M3S → 3723 秒） */
export function parseDurationFromLd(): number | null {
  try {
    const ld = document.querySelector('script[type="application/ld+json"]');
    if (!ld?.textContent) return null;
    const data = JSON.parse(ld.textContent);
    const duration = data?.duration;
    if (typeof duration !== "string") return null;
    const m = duration.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/);
    if (!m) return null;
    return (
      (parseInt(m[1] || "0") * 3600) +
      (parseInt(m[2] || "0") * 60) +
      parseInt(m[3] || "0")
    );
  } catch {
    return null;
  }
}
