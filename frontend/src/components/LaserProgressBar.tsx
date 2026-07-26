/**
 * LaserProgressBar — 激光粒子进度条（简化版）。
 *
 * 复刻 QML Lumio/Components/LaserProgressBar.qml 的视觉效果：
 *   - 渐变填充（紫→蓝→青）
 *   - 激光头白色亮点 + 光晕
 *   - compact 模式无 label
 *
 * 简化项（与 QML 版差异）：
 *   - 未实现 Canvas 粒子拖尾（80 粒子），改用 CSS 光晕模拟
 *   - 未实现 background-clip:text 渐变百分比文字
 *   原因：Canvas 粒子需要 rAF 驱动 + 复杂状态管理，React 中用 CSS 即可达到 90% 视觉效果
 */

interface LaserProgressBarProps {
  /** 进度 0..1（自动 clamp） */
  progress: number;
  /** compact 模式：只显示 bar，无 label */
  compact?: boolean;
  /** 是否启用激光动效（仅在 downloading 时启用） */
  particlesEnabled?: boolean;
  /** 左侧标签文本（compact 模式不显示） */
  labelText?: string;
}

export function LaserProgressBar({
  progress,
  compact = false,
  particlesEnabled = false,
  labelText = "",
}: LaserProgressBarProps) {
  // clamp progress 到 0..1，防止后端异常值导致宽度越界
  const p = Math.max(0, Math.min(1, progress || 0));
  const pct = Math.round(p * 100);

  if (compact) {
    return (
      <div className="relative h-5 w-full overflow-hidden rounded-full bg-black/30">
        {/* 轨道边框 */}
        <div className="pointer-events-none absolute inset-0 rounded-full border border-white/5" />
        {/* 渐变填充 */}
        <div
          className="relative h-full rounded-full transition-[width] duration-200 ease-out"
          style={{
            width: `${pct}%`,
            background:
              "linear-gradient(90deg, rgba(167, 139, 250, 0.9) 0%, rgba(99, 179, 237, 0.95) 50%, rgba(34, 211, 238, 1) 100%)",
            boxShadow: particlesEnabled
              ? "0 0 12px rgba(99, 179, 237, 0.6), 0 0 24px rgba(34, 211, 238, 0.3)"
              : "0 0 6px rgba(167, 139, 250, 0.3)",
          }}
        >
          {/* 激光头白色亮点 */}
          {pct > 0 && pct < 100 && (
            <div
              className="absolute top-0 right-0 h-full w-1 rounded-full bg-white"
              style={{
                boxShadow: particlesEnabled
                  ? "0 0 8px rgba(255, 255, 255, 0.9), 0 0 16px rgba(255, 255, 255, 0.5)"
                  : "0 0 4px rgba(255, 255, 255, 0.6)",
              }}
            />
          )}
          {/* 粒子动效（仅在 particlesEnabled 时显示） */}
          {particlesEnabled && pct > 0 && pct < 100 && (
            <div className="absolute inset-0 overflow-hidden rounded-full">
              <div
                className="absolute top-1/2 h-0.5 w-8 -translate-y-1/2 rounded-full bg-white/60"
                style={{
                  left: "calc(100% - 16px)",
                  filter: "blur(1px)",
                  animation: "laser-particle 1.2s linear infinite",
                }}
              />
            </div>
          )}
        </div>
      </div>
    );
  }

  // 完整模式：上方 label + 百分比，下方 bar
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-text-muted">{labelText}</span>
        <span className="font-semibold text-text">{pct}%</span>
      </div>
      <div className="relative h-5 w-full overflow-hidden rounded-full bg-black/30">
        <div className="pointer-events-none absolute inset-0 rounded-full border border-white/5" />
        <div
          className="relative h-full rounded-full transition-[width] duration-200 ease-out"
          style={{
            width: `${pct}%`,
            background:
              "linear-gradient(90deg, rgba(167, 139, 250, 0.9) 0%, rgba(99, 179, 237, 0.95) 50%, rgba(34, 211, 238, 1) 100%)",
            boxShadow: particlesEnabled
              ? "0 0 12px rgba(99, 179, 237, 0.6), 0 0 24px rgba(34, 211, 238, 0.3)"
              : "0 0 6px rgba(167, 139, 250, 0.3)",
          }}
        >
          {pct > 0 && pct < 100 && (
            <div
              className="absolute top-0 right-0 h-full w-1 rounded-full bg-white"
              style={{
                boxShadow: particlesEnabled
                  ? "0 0 8px rgba(255, 255, 255, 0.9), 0 0 16px rgba(255, 255, 255, 0.5)"
                  : "0 0 4px rgba(255, 255, 255, 0.6)",
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
