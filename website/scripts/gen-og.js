/**
 * gen-og.js — 构建时生成 public/og.png
 *
 * 背景：GitHub API 推送二进制文件不可靠（MCP 工具链只支持文本），
 * 因此仓库中以 base64 文本形式存放 og.png.b64，构建前解码为 og.png。
 * `prebuild` 会在 `npm run build` 之前自动执行（npm 生命周期）。
 *
 * 本地如需重新生成源图，见当时生成脚本（PIL），b64 由其输出转码。
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const dir = join(dirname(fileURLToPath(import.meta.url)), '..', 'public');
const src = join(dir, 'og.png.b64');
const dst = join(dir, 'og.png');

if (!existsSync(src)) {
  console.log('[gen-og] og.png.b64 不存在，跳过');
  process.exit(0);
}

const b64 = readFileSync(src, 'utf8').trim();
const buf = Buffer.from(b64, 'base64');

// PNG 魔数校验，防止写入损坏文件
if (buf[0] !== 0x89 || buf[1] !== 0x50 || buf[2] !== 0x4e || buf[3] !== 0x47) {
  console.error('[gen-og] base64 解码后不是有效 PNG，拒绝写入');
  process.exit(1);
}

writeFileSync(dst, buf);
console.log(`[gen-og] 已生成 og.png (${buf.length} bytes)`);
