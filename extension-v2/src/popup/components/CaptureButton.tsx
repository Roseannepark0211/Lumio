/**
 * 主按钮 — 发送当前页面到 Lumio Inbox
 *
 * 阶段 3：加入 PreviewPanel 确认流程
 * 1. 解析页面元数据
 * 2. 弹出 PreviewPanel 等用户确认
 * 3. 确认后发送到 Lumio
 * 4. 成功后刷新历史列表
 *
 * ★ 详情页无元数据时直接报错（不弹 PreviewPanel）
 * ★ 非详情页（首页/搜索页）无元数据时跳过 PreviewPanel 直接发送裸 URL
 */
import { useState, useEffect } from "react";
import { useConnectionStore } from "../store/connection";
import { useHistoryStore } from "../store/history";
import { PreviewPanel } from "./PreviewPanel";
import { isDetailPageUrl } from "../../shared/detailPage";
import type { PageMeta } from "../../types";

type SendState = "idle" | "extracting" | "awaiting-confirm" | "sending" | "ok" | "err";

export function CaptureButton() {
  const connected = useConnectionStore((s) => s.connected);
  const reloadHistory = useHistoryStore((s) => s.load);
  const [state, setState] = useState<SendState>("idle");
  const [message, setMessage] = useState("");
  const [meta, setMeta] = useState<PageMeta | null>(null);

  // ── 阶段3：监听 SPA 路由变化 ──────────────────────────────────────
  // 场景：用户在 IG/小红书博主主页（瀑布流）点击帖子 → URL 变成详情页
  // 但 popup 已打开，不会自动重新提取。这里监听 content script 的 urlChanged 消息，
  // URL 变化时自动重新提取并刷新预览。
  //
  // ★ 只在 popup 打开时生效（popup 关闭时 listener 自动清理）
  // ★ 只处理"进入详情页"和"切换帖子"，"离开详情页"时清空预览
  useEffect(() => {
    // ★ popup 打开时：如果当前已在详情页，自动解析
    // 场景：用户直接访问 /p/{id}/ 后才打开 popup，此时没有 urlChanged 事件
    (async () => {
      try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (tab?.url && isDetailPageUrl(tab.url)) {
          setState("extracting");
          setMessage("解析当前页面...");
          autoExtract();
        }
      } catch {
        // 忽略
      }
    })();

    const handler = (msg: unknown) => {
      if (typeof msg !== "object" || msg === null) return;
      const { type, transition } = msg as { type?: string; transition?: string };
      if (type !== "urlChanged") return;

      if (transition === "leave-detail") {
        // 离开详情页：清空预览回到 idle
        setState("idle");
        setMessage("");
        setMeta(null);
        return;
      }

      // enter-detail / switch-detail：自动重新提取
      // ★ 只在非工作状态时触发，避免打断用户正在进行的发送
      setState((prev) => {
        if (prev === "extracting" || prev === "sending" || prev === "awaiting-confirm") {
          return prev; // 不打断进行中的操作
        }
        // 触发重新提取（复用 handleSend 逻辑）
        // ★ 用 setTimeout 避免在 setState 回调里调 setState
        setTimeout(() => {
          autoExtract();
        }, 0);
        return "extracting";
      });
    };

    chrome.runtime.onMessage.addListener(handler);
    return () => chrome.runtime.onMessage.removeListener(handler);
  }, []);

  /** 自动提取（不发送，仅刷新预览） */
  const autoExtract = async () => {
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab?.id || !tab.url) {
        setState("idle");
        return;
      }

      setMessage("检测到帖子切换，重新解析...");
      const pageMeta = (await chrome.runtime.sendMessage({
        type: "extractPageMeta",
        tabId: tab.id,
      })) as PageMeta | null;

      if (pageMeta && (pageMeta.media_items?.length || pageMeta.thumbnail)) {
        setMeta(pageMeta);
        setState("awaiting-confirm");
        setMessage("");
      } else {
        // 提取失败或无媒体：回到 idle
        setState("idle");
        setMessage("");
        setMeta(null);
      }
    } catch {
      setState("idle");
      setMessage("");
      setMeta(null);
    }
  };

  const handleSend = async () => {
    if (!connected || state === "extracting" || state === "sending") return;

    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab?.id || !tab.url) {
        setState("err");
        setMessage("无法获取当前页面");
        return;
      }

      // 阶段 2：通过 background 提取元数据
      setState("extracting");
      setMessage("解析页面...");
      const pageMeta = (await chrome.runtime.sendMessage({
        type: "extractPageMeta",
        tabId: tab.id,
      })) as PageMeta | null;

      // ★ 提取失败不阻塞：详情页 fallback 到发裸 URL，由 Lumio 后端再提取
      //   硬性阻止会导致 content script 未注入/超时时完全无法发送
      //   （IG 帖子 URL 后端可用 cookie + 移动 API 处理）
      const isDetail = isDetailPageUrl(tab.url);
      if (isDetail && !pageMeta) {
        console.log("Lumio: 元数据提取失败，fallback 到发 URL 由后端处理");
      }

      // ★ 阶段 3：有元数据时弹 PreviewPanel 等确认
      if (pageMeta && (pageMeta.media_items?.length || pageMeta.thumbnail)) {
        setMeta(pageMeta);
        setState("awaiting-confirm");
        setMessage("");
        return;
      }

      // 无元数据（非详情页）：直接发送裸 URL
      // 构造最小 PageMeta（仅 url + title，其余字段 doSend 内不依赖）
      await doSend({
        url: tab.url,
        title: tab.title || "",
        author: "",
        platform: "",
        thumbnail: "",
        duration: null,
        source: "browser",
        type: "url",
      });
    } catch (err) {
      setState("err");
      setMessage(err instanceof Error ? err.message : String(err));
    }
  };

  /** 真正发送 */
  const doSend = async (pageMeta: PageMeta | null) => {
    setState("sending");
    setMessage("发送中...");

    try {
      const payload = pageMeta || { url: "", title: "" };
      const result = (await chrome.runtime.sendMessage({
        type: "capture",
        data: payload,
      })) as { success: boolean; error?: string; inbox_id?: string };

      if (result?.success) {
        setState("ok");
        setMessage(
          pageMeta?.media_items && pageMeta.media_items.length > 1
            ? `已发送 ${pageMeta.media_items.length} 项到 Inbox ✓`
            : "已发送到 Inbox ✓",
        );
        reloadHistory();
      } else {
        setState("err");
        setMessage(result?.error || "发送失败");
      }
    } catch (err) {
      setState("err");
      setMessage(err instanceof Error ? err.message : String(err));
    }

    // 2.5 秒后回到 idle
    setTimeout(() => {
      setState("idle");
      setMessage("");
      setMeta(null);
    }, 2500);
  };

  const handleConfirm = () => {
    if (meta) doSend(meta);
  };

  const handleCancel = () => {
    setState("idle");
    setMessage("");
    setMeta(null);
  };

  const isWorking = state === "extracting" || state === "sending";

  return (
    <div className="flex flex-col gap-2">
      {/* 阶段 2 解析预览保留（兼容） */}
      {meta && state === "extracting" && (
        <div className="rounded-lg bg-text/5 p-2 animate-fade-in">
          <div className="flex items-center gap-2">
            {meta.thumbnail && (
              <img
                src={meta.thumbnail}
                alt=""
                className="h-10 w-10 rounded object-cover"
                draggable={false}
              />
            )}
            <div className="min-w-0 flex-1">
              <div className="truncate text-xs font-medium">{meta.title}</div>
              <div className="flex items-center gap-2 text-[10px] text-text-dim">
                {meta.author && <span>@{meta.author}</span>}
                {meta.platform && <span>[{meta.platform}]</span>}
              </div>
            </div>
          </div>
        </div>
      )}

      <button
        className="btn-primary"
        onClick={handleSend}
        disabled={!connected || isWorking}
      >
        <span className="flex items-center justify-center gap-2">
          {isWorking && (
            <svg
              className="h-4 w-4 animate-spin"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <circle
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeOpacity="0.25"
                strokeWidth="3"
              />
              <path
                d="M12 2a10 10 0 0 1 10 10"
                stroke="currentColor"
                strokeWidth="3"
                strokeLinecap="round"
              />
            </svg>
          )}
          {state === "extracting"
            ? "解析中..."
            : state === "sending"
              ? "发送中..."
              : "发送当前页面到 Lumio"}
        </span>
      </button>

      {state !== "idle" && state !== "extracting" && state !== "sending" && state !== "awaiting-confirm" && (
        <div
          className={`rounded-lg px-3 py-2 text-xs animate-slide-up ${
            state === "ok"
              ? "bg-success/10 text-success"
              : "bg-danger/10 text-danger"
          }`}
        >
          {message}
        </div>
      )}

      {state === "extracting" && (
        <div className="rounded-lg bg-accent/10 px-3 py-2 text-xs text-accent animate-slide-up">
          {message}
        </div>
      )}

      {/* 阶段 3：PreviewPanel 确认弹窗 */}
      {state === "awaiting-confirm" && meta && (
        <PreviewPanel meta={meta} onConfirm={handleConfirm} onCancel={handleCancel} />
      )}
    </div>
  );
}
