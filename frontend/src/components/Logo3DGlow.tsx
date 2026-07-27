/**
 * Logo3DGlow — Lumio 3D Liquid Glass 字标
 *
 * 设计稿：design_preview/logo_wordmark_3d.html
 *
 * 特性：
 *   - 4 层叠加：字母主体渐变 + 顶部高光 + 流动光带 + 立体侧面（text-shadow 堆叠）
 *   - 呼吸动画：scale 1 → 1.035 + drop-shadow 强度变化（4.5s 周期）
 *   - 流动光带：高光从右到左持续扫过（4.2s 周期，mix-blend-mode: screen）
 *   - 内部色球：两个柔光球缓慢漂浮（7s / 9s 错位）
 *   - 地面倒影：仅 xl 尺寸默认开启
 *   - 6 色彩变体：default / ice / hue / cyan / gold / plasma / snow
 *
 * 用法：
 *   <Logo3DGlow size="md" />                          // 默认品牌色 + 呼吸 + 流光
 *   <Logo3DGlow size="xl" reflection variant="hue" />  // 彩虹流光 + 倒影
 *   <Logo3DGlow size="sm" breathing={false} />        // 静态小字标
 */

import { type CSSProperties } from 'react';
import './Logo3DGlow.css';

export type LogoSize = 'sm' | 'md' | 'lg' | 'xl';
export type LogoVariant =
  | 'default'   // 品牌色（蓝→紫）
  | 'ice'        // 纯白冰晶
  | 'hue'        // 彩虹流光
  | 'cyan'       // 炽热青蓝
  | 'gold'       // 金属鎏金
  | 'plasma'     // 黑暗电浆
  | 'snow';      // 极地雪光

export interface Logo3DGlowProps {
  /** 字号档位：sm 32 / md 64 / lg 96 / xl 160 */
  size?: LogoSize;
  /** 色彩变体 */
  variant?: LogoVariant;
  /** 启用呼吸动画（默认 true） */
  breathing?: boolean;
  /** 启用流动光带（默认 true） */
  shimmer?: boolean;
  /** 显示地面倒影（默认 size === 'xl'） */
  reflection?: boolean;
  /** 字标文本（默认 "Lumio"） */
  text?: string;
  /** 自定义类名（合并到根元素） */
  className?: string;
  /** 自定义样式（合并到根元素） */
  style?: CSSProperties;
  /** 无障碍标签 */
  'aria-label'?: string;
}

export function Logo3DGlow({
  size = 'md',
  variant = 'default',
  breathing = true,
  shimmer = true,
  reflection,
  text = 'Lumio',
  className,
  style,
  'aria-label': ariaLabel = 'Lumio',
}: Logo3DGlowProps) {
  // 倒影默认仅 xl 显示
  const showReflection = reflection ?? size === 'xl';

  const rootClass = [
    'lg-logo',
    `lg-logo--${size}`,
    `lg-logo--variant-${variant}`,
    breathing && 'lg-logo--breathing',
    shimmer && 'lg-logo--shimmer',
    className,
  ].filter(Boolean).join(' ');

  return (
    <div
      className={rootClass}
      style={style}
      aria-label={ariaLabel}
      role="img"
    >
      <span className="lg-logo__inner">
        {/* 立体侧面（text-shadow 堆叠） */}
        <span className="lg-logo__depth" aria-hidden="true">{text}</span>
        {/* 字母主体 + 顶部高光 + 流动光带（::before / ::after） */}
        <span className="lg-logo__body" data-text={text}>{text}</span>
        {/* 内部色球 */}
        <span className="lg-logo__orbs" aria-hidden="true" />
        {/* 地面倒影 */}
        {showReflection && <span className="lg-logo__reflection" aria-hidden="true" />}
      </span>
    </div>
  );
}

export default Logo3DGlow;
