/**
 * Electron 预加载脚本。
 *
 * 通过 contextBridge 暴露安全的 API 给渲染进程。
 * 渲染进程通过 lumio.fastapiBase / lumio.fastapiToken 访问动态生成的后端地址。
 * lumio.lumioFileUrl(path) 把本地文件路径转成 lumio-file:// URL（用于 <video>/<img>）。
 */

import { contextBridge } from "electron";

const fastapiBase = process.env.LUMIO_FASTAPI_BASE || "http://127.0.0.1:38910";
const fastapiToken = process.env.LUMIO_FASTAPI_TOKEN || "";

/**
 * 把本地文件绝对路径转成 lumio-file:// URL。
 * 例：C:\Users\foo\bar.mp4 → lumio-file:///C:/Users/foo/bar.mp4
 * 渲染进程用 <video src={lumioFileUrl(path)}> 播放本地视频。
 */
function lumioFileUrl(p: string): string {
  if (!p) return "";
  // 反斜杠 → 正斜杠（Windows 路径兼容）
  const normalized = p.replace(/\\/g, "/");
  // URL-encode 路径段，但保留 / 分隔符
  const encoded = normalized
    .split("/")
    .map((seg) => encodeURIComponent(seg))
    .join("/");
  // lumio-file:/// + 路径（带前导斜杠表示 absolute）
  return `lumio-file:///${encoded}`;
}

contextBridge.exposeInMainWorld("lumio", {
  version: "0.1.0",
  platform: process.platform,
  isElectron: true,
  fastapiBase,
  fastapiToken,
  lumioFileUrl,
});
