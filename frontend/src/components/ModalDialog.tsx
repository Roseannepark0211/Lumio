/**
 * 通用模态对话框（4 个页面共用，原 HistoryPage/InboxPage/LibraryPage/SettingsPage
 * 各自维护一份逐字符相同的实现，此处统一收敛）。
 *
 * 设计：固定 420px 宽（小屏自适应 90vw），点击遮罩关闭。
 */
import React from "react";

export function ModalDialog({
  title,
  children,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="glass-card w-[420px] max-w-[90vw] p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-3 text-base font-semibold text-text">{title}</h2>
        {children}
      </div>
    </div>
  );
}
