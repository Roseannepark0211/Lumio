/**
 * LaserProgressBar — 激光粒子进度条（Canvas 80 粒子拖尾版）。
 *
 * 复刻 QML Lumio/Components/LaserProgressBar.qml 的视觉效果：
 *   - 渐变填充（紫→蓝→青）
 *   - 激光头白色亮点 + 光晕
 *   - Canvas 80 粒子拖尾（每帧更新位置/透明度/大小）
 *   - rAF 驱动 60fps 动画
 *   - compact 模式无 label
 *
 * Electron 用 Chromium 渲染，Canvas 性能与 QML Canvas 等价。
 */

import { useEffect, useRef } from "react";

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

interface Particle {
  x: number;       // 相对 bar 左上角的 x 坐标
  y: number;       // 相对 bar 左上角的 y 坐标
  vx: number;      // x 速度
  vy: number;      // y 速度
  life: number;    // 0..1，1=新生，0=死亡
  size: number;    // 粒子半径
  hue: number;     // 色相 180..280（青→紫）
}

const PARTICLE_COUNT = 80;
const MAX_SPEED = 0.6;

export function LaserProgressBar({
  progress,
  compact = false,
  particlesEnabled = false,
  labelText = "",
}: LaserProgressBarProps) {
  // clamp progress 到 0..1
  const p = Math.max(0, Math.min(1, progress || 0));
  const pct = Math.round(p * 100);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const particlesRef = useRef<Particle[]>([]);
  const rafRef = useRef<number | null>(null);
  const barWidthRef = useRef(0);
  const barHeightRef = useRef(0);
  // 用 ref 保存最新 progress 和 headX，避免 rAF 闭包陈旧
  const progressRef = useRef(p);
  progressRef.current = p;
  const headXRef = useRef(0);
  const particlesEnabledRef = useRef(particlesEnabled);
  particlesEnabledRef.current = particlesEnabled;

  // 初始化粒子池
  useEffect(() => {
    if (particlesRef.current.length === 0) {
      particlesRef.current = Array.from({ length: PARTICLE_COUNT }, () => ({
        x: 0, y: 0, vx: 0, vy: 0, life: 0, size: 0, hue: 200,
      }));
    }
  }, []);

  // 每次进度变化时更新 headX（依赖 barWidth）
  useEffect(() => {
    headXRef.current = p * barWidthRef.current;
  }, [p]);

  // rAF 动画循环（仅在 particlesEnabled 时运行）
  useEffect(() => {
    if (!particlesEnabled) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
      // 清空 canvas
      const canvas = canvasRef.current;
      if (canvas) {
        const ctx = canvas.getContext("2d");
        ctx?.clearRect(0, 0, canvas.width, canvas.height);
      }
      return;
    }

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const tick = () => {
      const w = barWidthRef.current;
      const h = barHeightRef.current;
      const headX = headXRef.current;
      const p = progressRef.current;
      const pct = p * 100;

      // 高 DPI 适配
      const dpr = window.devicePixelRatio || 1;
      const cssW = w;
      const cssH = h;
      if (canvas.width !== cssW * dpr || canvas.height !== cssH * dpr) {
        canvas.width = cssW * dpr;
        canvas.height = cssH * dpr;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      }

      ctx.clearRect(0, 0, cssW, cssH);

      // 仅在 0..100% 之间发射粒子
      if (pct > 0 && pct < 100 && headX > 0) {
        for (const particle of particlesRef.current) {
          // 死亡粒子在激光头重生
          if (particle.life <= 0) {
            particle.x = headX;
            particle.y = h / 2 + (Math.random() - 0.5) * h * 0.6;
            particle.vx = -Math.random() * MAX_SPEED - 0.2;
            particle.vy = (Math.random() - 0.5) * 0.4;
            particle.life = 1;
            particle.size = Math.random() * 1.5 + 0.5;
            particle.hue = 180 + Math.random() * 100;
          }

          // 更新位置
          particle.x += particle.vx;
          particle.y += particle.vy;
          particle.life -= 0.02;

          // 绘制
          if (particle.life > 0) {
            const alpha = particle.life * 0.8;
            ctx.fillStyle = `hsla(${particle.hue}, 100%, 70%, ${alpha})`;
            ctx.beginPath();
            ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
            ctx.fill();
          }
        }
      }

      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    };
  }, [particlesEnabled]);

  // compact 模式
  if (compact) {
    return (
      <div
        className="relative h-5 w-full overflow-hidden rounded-full bg-black/30"
        ref={(el) => {
          if (el) {
            const rect = el.getBoundingClientRect();
            barWidthRef.current = rect.width;
            barHeightRef.current = rect.height;
            headXRef.current = (progressRef.current || 0) * rect.width;
          }
        }}
      >
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
        </div>
        {/* Canvas 粒子层（绝对定位覆盖整个 bar） */}
        <canvas
          ref={canvasRef}
          className="pointer-events-none absolute inset-0 h-full w-full"
        />
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
      <div
        className="relative h-5 w-full overflow-hidden rounded-full bg-black/30"
        ref={(el) => {
          if (el) {
            const rect = el.getBoundingClientRect();
            barWidthRef.current = rect.width;
            barHeightRef.current = rect.height;
            headXRef.current = (progressRef.current || 0) * rect.width;
          }
        }}
      >
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
        <canvas
          ref={canvasRef}
          className="pointer-events-none absolute inset-0 h-full w-full"
        />
      </div>
    </div>
  );
}
