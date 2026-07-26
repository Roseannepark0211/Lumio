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
 *
 * 关键：不对路径做 encodeURIComponent！
 * - encodeURIComponent("C:") = "C%3A"，导致 URL 形如 lumio-file:///C%3A/Users/...
 * - Chromium 的 URL safety check 会拒绝带 %3A 的路径，
 *   <video> 报错 "Media load rejected by URL safety check"
 * - lumio-file:// 是自定义 protocol，路径部分直接拼接即可，
 *   main.ts 的 handler 用 decodeURIComponent 兜底解码
 */
function lumioFileUrl(p: string): string {
  if (!p) return "";
  // 反斜杠 → 正斜杠（Windows 路径兼容）
  const normalized = p.replace(/\\/g, "/");
  // lumio-file:/// + 路径（带前导斜杠表示 absolute）
  // 不做 URL 编码，保留 C: 形式
  return `lumio-file:///${normalized}`;
}

contextBridge.exposeInMainWorld("lumio", {
  version: "0.1.0",
  platform: process.platform,
  isElectron: true,
  fastapiBase,
  fastapiToken,
  lumioFileUrl,
});
