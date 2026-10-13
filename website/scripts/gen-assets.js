/**
 * gen-assets.js — 构建时从 base64 文本解码生成二进制资源（prebuild）
 *
 * 背景：GitHub API 推送二进制文件不可靠（MCP 工具链只支持文本），
 * 因此二进制资源以 .b64 文本形式存放在 bin-assets/ 中，构建前解码还原到 public/。
 * `prebuild` 会在 `npm run build` 之前自动执行（npm 生命周期）。
 *
 * 清单：[public/ 下的输出路径, bin-assets/ 下的 .b64 源文件, 魔数校验（头 4 字节）]
 */
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const rootDir = join(dirname(fileURLToPath(import.meta.url)), '..');
const srcDir = join(rootDir, 'bin-assets');
const publicDir = join(rootDir, 'public');

// [输出文件名, base64 源文件名, 魔数校验（头 4 字节）]
const MANIFEST = [
  ['og.png', 'og.png.b64', [0x89, 0x50, 0x4e, 0x47]], // PNG
  ['fonts/Geist-400-latin.woff2', 'fonts/Geist-400-latin.woff2.b64', [0x77, 0x4f, 0x46, 0x32]], // wOF2
  ['fonts/Geist-500-latin.woff2', 'fonts/Geist-500-latin.woff2.b64', [0x77, 0x4f, 0x46, 0x32]],
  ['fonts/Geist-600-latin.woff2', 'fonts/Geist-600-latin.woff2.b64', [0x77, 0x4f, 0x46, 0x32]],
  ['fonts/Geist-700-latin.woff2', 'fonts/Geist-700-latin.woff2.b64', [0x77, 0x4f, 0x46, 0x32]],
  ['fonts/Geist-800-latin.woff2', 'fonts/Geist-800-latin.woff2.b64', [0x77, 0x4f, 0x46, 0x32]],
  ['fonts/GeistMono-400-latin.woff2', 'fonts/GeistMono-400-latin.woff2.b64', [0x77, 0x4f, 0x46, 0x32]],
  ['fonts/GeistMono-500-latin.woff2', 'fonts/GeistMono-500-latin.woff2.b64', [0x77, 0x4f, 0x46, 0x32]],
  ['fonts/GeistMono-600-latin.woff2', 'fonts/GeistMono-600-latin.woff2.b64', [0x77, 0x4f, 0x46, 0x32]],
];

let failed = 0;
for (const [out, src, magic] of MANIFEST) {
  const srcPath = join(srcDir, src);
  const outPath = join(publicDir, out);
  if (!existsSync(srcPath)) {
    console.log(`[gen-assets] 跳过 ${out}：bin-assets/${src} 不存在`);
    continue;
  }
  mkdirSync(dirname(outPath), { recursive: true });
  const buf = Buffer.from(readFileSync(srcPath, 'utf8').trim(), 'base64');
  const ok = magic.every((b, i) => buf[i] === b);
  if (!ok) {
    console.error(`[gen-assets] ${out} 魔数校验失败，拒绝写入`);
    failed++;
    continue;
  }
  writeFileSync(outPath, buf);
  console.log(`[gen-assets] 已生成 ${out} (${buf.length} bytes)`);
}
if (failed > 0) process.exit(1);
