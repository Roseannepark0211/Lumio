/**
 * Electron 预加载脚本。
 *
 * 通过 contextBridge 暴露安全的 API 给渲染进程。
 * 渲染进程通过 lumio.fastapiBase / lumio.fastapiToken 访问动态生成的后端地址。
 */

import { contextBridge } from "electron";

const fastapiBase = process.env.LUMIO_FASTAPI_BASE || "http://127.0.0.1:38910";
const fastapiToken = process.env.LUMIO_FASTAPI_TOKEN || "";

contextBridge.exposeInMainWorld("lumio", {
  version: "0.1.0",
  platform: process.platform,
  isElectron: true,
  fastapiBase,
  fastapiToken,
});
