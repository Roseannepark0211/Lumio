/**
 * meteor-canvas.ts — 暗夜模式流星雨粒子系统
 *
 * 视觉调性：流星雨盛宴
 *   - 15-20 颗活跃流星，快速连发
 *   - 白色为主 (75%)，偶尔青色 (#5ac8fa) / 蓝色 (#0a84ff) / 浅蓝 (#64d2ff)
 *   - 短拖尾发光，速度快
 *   - 背景加 80-120 颗静态星点（呼吸闪烁）
 *
 * 性能策略：
 *   - 单 canvas 固定满屏，z-index: -1，pointer-events: none
 *   - 仅 html[data-theme="dark"] 时启动；切换到 light 立即停止 RAF + 清空 canvas
 *   - visibilitychange 隐藏标签页时暂停（节省 CPU）
 *   - prefers-reduced-motion 时完全不启动
 *   - DPR 感知，retina 屏清晰渲染
 *   - 粒子上限 30，超出不再 spawn
 */

interface Meteor {
  x: number;
  y: number;
  vx: number;
  vy: number;
  length: number;
  opacity: number;
  color: string;
  // 生命进度 0..1，>1 时移除
  life: number;
  // 最大寿命（帧数）
  maxLife: number;
  // 进入/淡出阶段
  fadeIn: number;
}

interface Star {
  x: number;
  y: number;
  baseAlpha: number;
  phase: number; // 闪烁相位
  speed: number;
}

const CANVAS_ID = 'meteor-canvas';
const MAX_METEORS = 15;
const MAX_STARS = 110;

// 流星颜色池 — 白色为主，偶尔品牌色
const METEOR_COLORS = [
  '#ffffff', '#ffffff', '#ffffff', '#ffffff', // 75% 白
  '#5ac8fa',                                   // 青色
  '#0a84ff',                                   // 蓝色
  '#64d2ff',                                   // 浅蓝
];

let canvas: HTMLCanvasElement | null = null;
let ctx: CanvasRenderingContext2D | null = null;
let rafId: number | null = null;
let meteors: Meteor[] = [];
let stars: Star[] = [];
let lastFrameTime = 0;
let lastSpawnTime = 0;
let isRunning = false;

/** 创建一颗流星 — 从屏幕左上区域生成，斜向右下运动 */
function spawnMeteor(width: number, height: number): Meteor {
  // 角度 25°-45°（向右下方）
  const angle = (25 + Math.random() * 20) * (Math.PI / 180);
  // 速度 800-1500 px/s
  const speed = 800 + Math.random() * 700;

  // 起点：屏幕左侧或顶部偏外，让流星划入视口
  const startFromTop = Math.random() < 0.6;
  let x: number, y: number;
  if (startFromTop) {
    x = Math.random() * width * 1.2 - width * 0.2;
    y = -50;
  } else {
    x = -50;
    y = Math.random() * height * 0.6;
  }

  return {
    x,
    y,
    vx: Math.cos(angle) * speed,
    vy: Math.sin(angle) * speed,
    length: 80 + Math.random() * 100,
    opacity: 0,
    color: METEOR_COLORS[Math.floor(Math.random() * METEOR_COLORS.length)],
    life: 0,
    maxLife: 1.5 + Math.random() * 1.0, // 1.5-2.5 秒寿命
    fadeIn: 0.2, // 0.2 秒淡入
  };
}

/** 初始化静态星空背景 */
function initStars(width: number, height: number) {
  stars = [];
  for (let i = 0; i < MAX_STARS; i++) {
    stars.push({
      x: Math.random() * width,
      y: Math.random() * height,
      baseAlpha: 0.2 + Math.random() * 0.6,
      phase: Math.random() * Math.PI * 2,
      speed: 0.5 + Math.random() * 1.5,
    });
  }
}

/** 绘制一帧 */
function draw(deltaTime: number) {
  if (!ctx || !canvas) return;

  const width = canvas.width;
  const height = canvas.height;

  // 清空 — 用深色背景而非透明，避免残影
  ctx.fillStyle = 'rgba(8, 8, 10, 1)';
  ctx.fillRect(0, 0, width, height);

  // ── 1. 绘制星空（呼吸闪烁） ──
  for (const star of stars) {
    star.phase += star.speed * deltaTime;
    const alpha = star.baseAlpha * (0.5 + 0.5 * Math.sin(star.phase));
    ctx.beginPath();
    ctx.arc(star.x, star.y, 0.6, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(255, 255, 255, ${alpha})`;
    ctx.fill();
  }

  // ── 2. 生成新流星（间隔 600-1500ms — 降低密度避免干扰阅读） ──
  const now = performance.now();
  if (now - lastSpawnTime > 600 + Math.random() * 900 && meteors.length < MAX_METEORS) {
    meteors.push(spawnMeteor(width, height));
    lastSpawnTime = now;
  }

  // ── 3. 更新 + 绘制流星 ──
  for (let i = meteors.length - 1; i >= 0; i--) {
    const m = meteors[i];
    m.life += deltaTime;
    m.x += m.vx * deltaTime;
    m.y += m.vy * deltaTime;

    // 淡入淡出：前 20% 寿命淡入，后 30% 淡出
    const lifeRatio = m.life / m.maxLife;
    if (lifeRatio < 0.2) {
      m.opacity = lifeRatio / 0.2;
    } else if (lifeRatio > 0.7) {
      m.opacity = (1 - lifeRatio) / 0.3;
    } else {
      m.opacity = 1;
    }
    m.opacity = Math.max(0, Math.min(1, m.opacity));

    // 寿终或飞出屏幕则移除
    if (lifeRatio >= 1 || m.x > width + 100 || m.y > height + 100) {
      meteors.splice(i, 1);
      continue;
    }

    // 绘制流星：拖尾 + 头部
    const tailX = m.x - m.vx * (m.length / 1000);
    const tailY = m.y - m.vy * (m.length / 1000);

    // 拖尾渐变
    const gradient = ctx.createLinearGradient(m.x, m.y, tailX, tailY);
    gradient.addColorStop(0, hexWithAlpha(m.color, m.opacity));
    gradient.addColorStop(1, hexWithAlpha(m.color, 0));

    ctx.strokeStyle = gradient;
    ctx.lineWidth = 1.5;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(m.x, m.y);
    ctx.lineTo(tailX, tailY);
    ctx.stroke();

    // 头部高亮 + 发光
    ctx.shadowColor = m.color;
    ctx.shadowBlur = 8;
    ctx.fillStyle = hexWithAlpha('#ffffff', m.opacity);
    ctx.beginPath();
    ctx.arc(m.x, m.y, 1.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;
  }
}

/** hex 颜色 + alpha → rgba 字符串 */
function hexWithAlpha(hex: string, alpha: number): string {
  const h = hex.replace('#', '');
  const r = parseInt(h.substring(0, 2), 16);
  const g = parseInt(h.substring(2, 4), 16);
  const b = parseInt(h.substring(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/** 单帧动画循环 */
function tick(timestamp: number) {
  if (!isRunning) return;
  if (!lastFrameTime) lastFrameTime = timestamp;
  const deltaTime = Math.min((timestamp - lastFrameTime) / 1000, 0.05); // 上限 50ms 防大跳
  lastFrameTime = timestamp;

  draw(deltaTime);

  rafId = requestAnimationFrame(tick);
}

/** 调整 canvas 尺寸 — DPR 感知 */
function resize() {
  if (!canvas) return;
  const dpr = window.devicePixelRatio || 1;
  const width = window.innerWidth;
  const height = window.innerHeight;
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  if (ctx) {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(dpr, dpr);
  }
  // 重新初始化星点
  initStars(width, height);
}

/** 启动流星系统 */
function start() {
  if (isRunning) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  canvas = document.getElementById(CANVAS_ID) as HTMLCanvasElement;
  if (!canvas) return;
  ctx = canvas.getContext('2d');
  if (!ctx) return;

  // canvas 可见性由 CSS 控制（opacity + visibility + 0.4s 过渡）
  // JS 仅负责启动 rAF 循环渲染粒子
  resize();
  meteors = [];
  lastFrameTime = 0;
  lastSpawnTime = 0;
  isRunning = true;
  rafId = requestAnimationFrame(tick);
}

/** 停止流星系统 */
function stop() {
  isRunning = false;
  if (rafId !== null) {
    cancelAnimationFrame(rafId);
    rafId = null;
  }
  if (ctx && canvas) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }
  meteors = [];
}

/** 处理可见性变化 — 隐藏时暂停 */
function handleVisibility() {
  if (document.hidden) {
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
  } else if (isRunning) {
    lastFrameTime = 0;
    rafId = requestAnimationFrame(tick);
  }
}

/** 检查当前主题并启动/停止 */
function syncWithTheme() {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  if (isDark) {
    start();
  } else {
    stop();
  }
}

/** 监听主题变化 */
function observeThemeChanges() {
  const observer = new MutationObserver((mutations) => {
    for (const m of mutations) {
      if (m.type === 'attributes' && m.attributeName === 'data-theme') {
        syncWithTheme();
        return;
      }
    }
  });
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
}

/** 初始化入口 */
export function initMeteorCanvas(): () => void {
  // 延迟到 DOMContentLoaded 后再启动
  const ready = () => {
    syncWithTheme();
    observeThemeChanges();
    window.addEventListener('resize', resize);
    document.addEventListener('visibilitychange', handleVisibility);
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ready);
  } else {
    ready();
  }

  // 返回销毁函数
  return () => {
    stop();
    window.removeEventListener('resize', resize);
    document.removeEventListener('visibilitychange', handleVisibility);
  };
}
