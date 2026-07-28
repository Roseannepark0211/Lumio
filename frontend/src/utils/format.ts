/**
 * 字节格式化：B / KB / MB / GB。
 *
 * 与后端 `utils/media_utils.py::format_size()` 行为一致：
 * - `zeroDefault=false`（默认）：零值返回 "—"（适合统计卡片/列表显示）
 * - `zeroDefault=true`：零值返回 "0 B"（适合设置页/详情页要求非空字符串的场景）
 */
export function formatSize(bytes: number, zeroDefault = false): string {
  if (!bytes || bytes <= 0) return zeroDefault ? "0 B" : "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}
