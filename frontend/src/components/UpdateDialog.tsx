/**
 * 更新对话框组件 — 完整的检查更新 → 下载 → 安装流程 UI。
 *
 * 三阶段状态机：
 *   1. idle / checking     — 检查中（loading 动画）
 *   2. available           — 发现新版本，显示 release notes + [立即下载][稍后]
 *   3. downloading         — 下载中，显示进度条（percent + 速度）
 *   4. downloaded          — 下载完成，[立即重启][下次启动时安装]
 *   5. not-available       — 已是最新版本
 *   6. error               — 错误提示
 *
 * 平台差异：
 *   - Windows/Linux: 完整流程（检查→下载→安装）
 *   - macOS: 无自动下载，"立即下载"按钮直接打开 GitHub Release 页面
 */

import { useState, useEffect, useCallback, useMemo } from "react";
import { ModalDialog } from "./ModalDialog";
import { type UpdateInfo, type DownloadProgress } from "../api";
import { renderReleaseNotes } from "../utils/releaseNotes";
import "./ReleaseNotes.css";

// lumioGlobal 在 api.ts 是模块内 const，不导出。这里通过 window.lumio 访问。
const lumioGlobal = (typeof window !== "undefined" ? (window as unknown as { lumio?: any }).lumio : undefined);

type UpdateStage =
  | "idle"
  | "checking"
  | "available"
  | "downloading"
  | "downloaded"
  | "not-available"
  | "error";

interface UpdateDialogProps {
  open: boolean;
  onClose: () => void;
}

export function UpdateDialog({ open, onClose }: UpdateDialogProps) {
  const [stage, setStage] = useState<UpdateStage>("idle");
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null);
  const [progress, setProgress] = useState<DownloadProgress | null>(null);
  const [errorMsg, setErrorMsg] = useState<string>("");
  /** 原始技术错误（小字展示，方便报障排查） */
  const [errorDetail, setErrorDetail] = useState<string>("");

  /**
   * 更新日志渲染：electron-updater 给的是 GitHub Atom 的 HTML，
   * macOS 手动模式给的是原始 Markdown；renderReleaseNotes 会把
   * 两者统一成白名单清洗过的安全 HTML，不再当纯文本原样输出，
   * 且只显示新版本「更新内容」一段（下载表、系统要求等模板内容不显示）。
   */
  const renderedReleaseNotes = useMemo(
    () => renderReleaseNotes(updateInfo?.releaseNotes),
    [updateInfo?.releaseNotes],
  );

  // 当前平台（macOS 走手动下载模式）
  const isMacos = lumioGlobal?.platform === "darwin";

  /** 监听主进程推送的更新事件 */
  useEffect(() => {
    if (!open) return;
    const updater = lumioGlobal?.updater;
    if (!updater) return;

    updater.onEvent((channel: string, data: any) => {
      switch (channel) {
        case "update:checking":
          setStage("checking");
          break;
        case "update:available":
          setUpdateInfo(data);
          setStage("available");
          break;
        case "update:not-available":
          setStage("not-available");
          break;
        case "update:download-progress":
          setProgress(data);
          setStage("downloading");
          break;
        case "update:downloaded":
          setUpdateInfo(data);
          setStage("downloaded");
          break;
        case "update:error":
          setErrorMsg(data?.message || "未知错误");
          setErrorDetail(data?.detail || "");
          setStage("error");
          break;
      }
    });
  }, [open]);

  /** 执行检查更新（打开对话框时 + 重试按钮共用） */
  const runCheck = useCallback(async () => {
    const updater = lumioGlobal?.updater;
    if (!updater) {
      setStage("error");
      setErrorMsg("非 Electron 环境，无法检查更新");
      setErrorDetail("");
      return;
    }
    setStage("checking");
    setProgress(null);
    setErrorMsg("");
    setErrorDetail("");
    const result = await updater.check();
    if (result.error) {
      setErrorMsg(result.error);
      setErrorDetail(result.errorDetail || "");
      setStage("error");
    } else if (result.hasUpdate && result.info) {
      setUpdateInfo(result.info);
      setStage("available");
    } else {
      setStage("not-available");
    }
  }, []);

  /** 打开对话框时自动检查更新 */
  useEffect(() => {
    if (!open) return;
    runCheck();
  }, [open, runCheck]);

  /** 报错时打开 GitHub Release 页面手动下载 */
  const onOpenReleases = useCallback(async () => {
    const updater = lumioGlobal?.updater;
    if (!updater) return;
    await updater.openReleasesPage();
  }, []);

  /** 用户点"立即下载" */
  const onDownload = useCallback(async () => {
    const updater = lumioGlobal?.updater;
    if (!updater) return;

    // macOS: 直接打开 Release 页面
    if (isMacos) {
      await updater.download(); // 内部会 shell.openExternal
      onClose();
      return;
    }

    // Windows/Linux: 开始下载，等待 update:download-progress / update:downloaded 事件
    setStage("downloading");
    setProgress({ percent: 0, transferredBytes: 0, totalBytes: 0, bytesPerSecond: 0 });
    const result = await updater.download();
    if (!result.ok) {
      setErrorMsg(result.error || "下载失败");
      setStage("error");
    }
    // 成功的话等 download-progress / update:downloaded 事件推动状态
  }, [isMacos, onClose]);

  /** 用户点"立即重启" */
  const onQuitAndInstall = useCallback(async () => {
    const updater = lumioGlobal?.updater;
    if (!updater) return;
    await updater.quitAndInstall();
  }, []);

  if (!open) return null;

  // 标题根据阶段动态变化
  const title =
    stage === "checking" ? "检查更新中..." :
    stage === "available" ? `发现新版本 v${updateInfo?.version}` :
    stage === "downloading" ? "下载更新中..." :
    stage === "downloaded" ? "更新已就绪" :
    stage === "not-available" ? "已是最新版本" :
    stage === "error" ? "更新失败" :
    "检查更新";

  return (
    <ModalDialog title={title} onClose={onClose}>
      <div className="space-y-3">
        {/* 检查中 */}
        {stage === "checking" && (
          <div className="flex items-center justify-center py-6">
            <div className="flex gap-1.5">
              <span className="h-2 w-2 animate-pulse rounded-full bg-cyan-400" style={{ animationDelay: "0ms" }} />
              <span className="h-2 w-2 animate-pulse rounded-full bg-cyan-400" style={{ animationDelay: "150ms" }} />
              <span className="h-2 w-2 animate-pulse rounded-full bg-cyan-400" style={{ animationDelay: "300ms" }} />
            </div>
          </div>
        )}

        {/* 发现新版本 */}
        {stage === "available" && updateInfo && (
          <>
            <div className="text-xs text-text-muted">
              {isMacos
                ? "macOS 需手动下载 DMG 安装包，点击下方按钮跳转 GitHub Release 页面。"
                : "点击「立即下载」开始后台下载，下载完成后会提示重启安装。"}
            </div>
            {renderedReleaseNotes && (
              <div className="max-h-60 overflow-y-auto rounded-lg bg-black/20 p-3">
                <div
                  className="release-notes text-text"
                  dangerouslySetInnerHTML={{ __html: renderedReleaseNotes }}
                />
              </div>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <button
                className="rounded-lg px-3 py-1.5 text-xs text-text-muted hover:bg-white/5"
                onClick={onClose}
              >
                稍后
              </button>
              <button
                className="rounded-lg bg-accent px-4 py-1.5 text-xs font-medium text-white hover:bg-accent-hover"
                onClick={onDownload}
              >
                {isMacos ? "打开下载页面" : "立即下载"}
              </button>
            </div>
          </>
        )}

        {/* 下载中 */}
        {stage === "downloading" && (
          <div className="space-y-2 py-2">
            <div className="h-2 w-full overflow-hidden rounded-full bg-black/30">
              <div
                className="h-full rounded-full bg-gradient-to-r from-cyan-400 to-blue-500 transition-all duration-200"
                style={{ width: `${progress?.percent || 0}%` }}
              />
            </div>
            <div className="flex justify-between text-xs text-text-muted">
              <span>{progress?.percent.toFixed(1) || 0}%</span>
              <span>
                {progress && progress.bytesPerSecond > 0
                  ? `${formatBytes(progress.bytesPerSecond)}/s`
                  : "..."}
              </span>
            </div>
            {progress && progress.totalBytes > 0 && (
              <div className="text-center text-xs text-text-muted">
                {formatBytes(progress.transferredBytes)} / {formatBytes(progress.totalBytes)}
              </div>
            )}
            <div className="text-center text-xs text-text-muted">
              下载中，请勿关闭应用
            </div>
          </div>
        )}

        {/* 下载完成 */}
        {stage === "downloaded" && (
          <>
            <div className="text-sm text-text">
              新版本 v{updateInfo?.version} 已下载完成，是否立即重启安装？
            </div>
            <div className="text-xs text-text-muted">
              选择「下次启动时安装」会在退出应用时自动安装。
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                className="rounded-lg px-3 py-1.5 text-xs text-text-muted hover:bg-white/5"
                onClick={onClose}
              >
                下次启动时安装
              </button>
              <button
                className="rounded-lg bg-accent px-4 py-1.5 text-xs font-medium text-white hover:bg-accent-hover"
                onClick={onQuitAndInstall}
              >
                立即重启
              </button>
            </div>
          </>
        )}

        {/* 已是最新 */}
        {stage === "not-available" && (
          <div className="space-y-3">
            <div className="py-4 text-center text-sm text-text">
              ✅ 当前已是最新版本
            </div>
            <div className="flex justify-end">
              <button
                className="rounded-lg bg-accent px-4 py-1.5 text-xs font-medium text-white hover:bg-accent-hover"
                onClick={onClose}
              >
                确定
              </button>
            </div>
          </div>
        )}

        {/* 错误 — 中文友好提示 + 原始错误小字 + 重试/手动下载 */}
        {stage === "error" && (
          <div className="space-y-3">
            <div className="py-2 text-sm text-red-400">
              ❌ {errorMsg}
            </div>
            {errorDetail && (
              <div className="break-all rounded bg-black/20 p-2 font-mono text-[11px] text-text-dim">
                {errorDetail}
              </div>
            )}
            <div className="flex justify-end gap-2">
              <button
                className="rounded-lg px-3 py-1.5 text-xs text-text-muted hover:bg-white/5"
                onClick={onClose}
              >
                关闭
              </button>
              <button
                className="rounded-lg px-3 py-1.5 text-xs text-text-muted hover:bg-white/5"
                onClick={onOpenReleases}
              >
                去官网手动下载
              </button>
              <button
                className="rounded-lg bg-accent px-4 py-1.5 text-xs font-medium text-white hover:bg-accent-hover"
                onClick={runCheck}
              >
                重试
              </button>
            </div>
          </div>
        )}
      </div>
    </ModalDialog>
  );
}

/** 字节数格式化工具 */
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}
