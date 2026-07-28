/**
 * 主按钮 — 发送当前页面到 Lumio Inbox
 *
 * 阶段 1：仅发送 tab.url（不调 content.js）
 * 阶段 2：接入 content.js 元数据 + 预览面板
 */
import { useState } from "react";
import { useConnectionStore } from "../store/connection";

type SendState = "idle" | "sending" | "ok" | "err";

export function CaptureButton() {
  const connected = useConnectionStore((s) => s.connected);
  const [state, setState] = useState<SendState>("idle");
  const [message, setMessage] = useState("");

  const handleSend = async () => {
    if (!connected || state === "sending") return;

    setState("sending");
    setMessage("发送中...");

    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab?.url) {
        setState("err");
        setMessage("无法获取当前页面 URL");
        return;
      }

      // 阶段 1：直接发 tab.url，让 background 补全 platform/author
      // 阶段 2 会改为：先 extractNow 拿元数据，PreviewPanel 确认后再发
      const result = (await chrome.runtime.sendMessage({
        type: "capture",
        data: { url: tab.url, title: tab.title },
      })) as { success: boolean; error?: string };

      if (result?.success) {
        setState("ok");
        setMessage("已发送到 Inbox ✓");
      } else {
        setState("err");
        setMessage(result?.error || "发送失败");
      }
    } catch (err) {
      setState("err");
      setMessage(err instanceof Error ? err.message : String(err));
    }

    // 2 秒后回到 idle
    setTimeout(() => {
      setState("idle");
      setMessage("");
    }, 2000);
  };

  const isSending = state === "sending";

  return (
    <div className="flex flex-col gap-2">
      <button
        className="btn-primary"
        onClick={handleSend}
        disabled={!connected || isSending}
      >
        <span className="flex items-center justify-center gap-2">
          {isSending && (
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
          {isSending ? "发送中..." : "发送当前页面到 Lumio"}
        </span>
      </button>

      {state !== "idle" && (
        <div
          className={`rounded-lg px-3 py-2 text-xs animate-slide-up ${
            state === "ok"
              ? "bg-success/10 text-success"
              : state === "err"
                ? "bg-danger/10 text-danger"
                : "bg-accent/10 text-accent"
          }`}
        >
          {message}
        </div>
      )}
    </div>
  );
}
