/**
 * LaserProgressBar — 激光粒子进度条（Canvas 80 粒子拖尾版）。
 *
 * 复刻 QML Lumio/Components/LaserProgressBar.qml 的视觉效果：
 *   - 渐变填充（紫→蓝→青）
 *   - bar 高度 8px（细 bar，粒子视觉占比大）
 *   - 激光头白色亮点 + 32px 大光晕
 *   - Canvas 80 粒子拖尾：向后扇形发射 + 径向发光 + 亮核
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
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
  decay: number;
  size: number;
  hue: number;
}

const PARTICLE_MAX = 80;

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
  const headXRef = useRef(0);
  const progressRef = useRef(p);
  progressRef.current = p;
  const particlesEnabledRef = useRef(particlesEnabled);
  particlesEnabledRef.current = particlesEnabled;

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
      // 清空粒子池
      particlesRef.current = [];
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
      // bar 中心 Y（相对 canvas）
      // canvas 比 bar 高 20px（上下各 +10 margin），bar 在 canvas 中央
      const headY = h / 2;
      const p = progressRef.current;
      const pct = p * 100;

      // 高 DPI 适配
      const dpr = window.devicePixelRatio || 1;
      if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
        canvas.width = w * dpr;
        canvas.height = h * dpr;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      }

      ctx.clearRect(0, 0, w, h);

      // 仅在 0..100% 之间发射粒子（每帧 1-2 个）
      if (pct > 0 && pct < 100 && headX > 0) {
        const spawnCount = Math.random() < 0.7 ? 2 : 1;
        for (let i = 0; i < spawnCount; i++) {
          if (particlesRef.current.length < PARTICLE_MAX) {
            const angle = (Math.random() - 0.5) * Math.PI * 0.7 + Math.PI; // backward fan
            const speed = 0.5 + Math.random() * 1.8;
            particlesRef.current.push({
              x: headX,
              y: headY + (Math.random() - 0.5) * 4,
              vx: Math.cos(angle) * speed,
              vy: Math.sin(angle) * speed * 0.6,
              life: 1,
              decay: 0.012 + Math.random() * 0.018,
              size: 1 + Math.random() * 2,
              hue: 200 + Math.random() * 40,
            });
          }
        }
      }

      // 更新 + 绘制粒子
      const particles = particlesRef.current;
      for (let j = particles.length - 1; j >= 0; j--) {
        const particle = particles[j];
        particle.x += particle.vx;
        particle.y += particle.vy;
        particle.vy += 0.02;
        particle.life -= particle.decay;
        if (particle.life <= 0) {
          particles.splice(j, 1);
          continue;
        }
        const alpha = particle.life * 0.9;
        const r = particle.size * particle.life;

        // 外发光（径向渐变 4 倍半径）
        const grad = ctx.createRadialGradient(
          particle.x, particle.y, 0,
          particle.x, particle.y, r * 4
        );
        grad.addColorStop(0, `hsla(${particle.hue}, 100%, 70%, ${alpha})`);
        grad.addColorStop(0.4, `hsla(${particle.hue}, 100%, 60%, ${alpha * 0.4})`);
        grad.addColorStop(1, `hsla(${particle.hue}, 100%, 50%, 0)`);
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(particle.x, particle.y, r * 4, 0, Math.PI * 2);
        ctx.fill();

        // 亮核
        ctx.fillStyle = `hsla(${particle.hue}, 100%, 90%, ${alpha})`;
        ctx.beginPath();
        ctx.arc(particle.x, particle.y, r, 0, Math.PI * 2);
        ctx.fill();
      }

      // 激光头光晕（32px 大光晕，与 QML 版对齐）
      if (pct > 0 && pct < 100 && headX > 0) {
        const headGrad = ctx.createRadialGradient(
          headX, headY, 0,
          headX, headY, 16
        );
        headGrad.addColorStop(0, "rgba(255, 255, 255, 0.9)");
        headGrad.addColorStop(0.3, "rgba(120, 180, 255, 0.5)");
        headGrad.addColorStop(1, "rgba(10, 132, 255, 0)");
        ctx.fillStyle = headGrad;
        ctx.beginPath();
        ctx.arc(headX, headY, 16, 0, Math.PI * 2);
        ctx.fill();
      }

      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    };
  }, [particlesEnabled]);

  // 每次进度变化时更新 headX
  useEffect(() => {
    headXRef.current = p * barWidthRef.current;
  }, [p]);

  // compact 模式：bar 高度 8px（与 QML 对齐），canvas 上下各 +10 margin 容纳粒子
  // 完整模式：上方 label + bar（8px）+ canvas 上下 margin
  if (compact) {
    return (
      <div className="relative flex h-5 w-full items-center">
        {/* canvas 绝对定位覆盖整个区域（含上下 6px margin 容纳粒子） */}
        <canvas
          ref={canvasRef}
          className="pointer-events-none absolute inset-0 h-full w-full"
        />
        {/* bar track 居中 8px 高 */}
        <div
          className="relative h-2 w-full overflow-hidden rounded-full bg-black/30"
          ref={(el) => {
            if (el) {
              const parent = el.parentElement;
              if (parent) {
                const rect = parent.getBoundingClientRect();
                barWidthRef.current = rect.width;
                barHeightRef.current = rect.height;
                headXRef.current = (progressRef.current || 0) * rect.width;
              }
            }
          }}
        >
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
            {/* 激光头白色亮点（4px 宽，高于 bar 4px） */}
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

  // 完整模式
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-text-muted">{labelText}</span>
        <span className="font-semibold text-text">{pct}%</span>
      </div>
      <div className="relative flex h-5 w-full items-center">
        <canvas
          ref={canvasRef}
          className="pointer-events-none absolute inset-0 h-full w-full"
        />
        <div
          className="relative h-2 w-full overflow-hidden rounded-full bg-black/30"
          ref={(el) => {
            if (el) {
              const parent = el.parentElement;
              if (parent) {
                const rect = parent.getBoundingClientRect();
                barWidthRef.current = rect.width;
                barHeightRef.current = rect.height;
                headXRef.current = (progressRef.current || 0) * rect.width;
              }
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
        </div>
      </div>
    </div>
  );
}
