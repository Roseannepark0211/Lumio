/**
 * 从主项目 frontend/build/icon.png 生成插件所需的多个尺寸图标
 *
 * 用法：npm run icons
 *
 * 输出：src/assets/icons/logo-{16,32,48,128}.png
 *
 * 维护规则：主项目图标更新后，重新运行此脚本即可同步到插件
 */
import sharp from "sharp";
import path from "node:path";
import fs from "node:fs/promises";
import { fileURLToPath } from "node:url";

// fileURLToPath 正确处理跨平台路径：
//   Linux: file:///home/user/x.ts → /home/user/x.ts
//   Windows: file:///C:/Users/x.ts → C:\Users\x.ts
// 旧实现 new URL().pathname.replace(/^\//, "") 在 Linux 上会把绝对路径变成相对路径，
// 导致 path.resolve 拼接到 cwd 下，找不到源文件。
const __dirname = path.dirname(fileURLToPath(import.meta.url));

const SOURCE = path.resolve(__dirname, "../../frontend/build/icon.png");
const OUT_DIR = path.resolve(__dirname, "../src/assets/icons");

const SIZES = [16, 32, 48, 128];

async function main() {
  // 检查源文件
  try {
    await fs.access(SOURCE);
  } catch {
    console.error(`✗ 源文件不存在: ${SOURCE}`);
    console.error("  请确认主项目 frontend/build/icon.png 已生成");
    process.exit(1);
  }

  // 创建输出目录
  await fs.mkdir(OUT_DIR, { recursive: true });

  // 生成各尺寸
  for (const size of SIZES) {
    const outPath = path.join(OUT_DIR, `logo-${size}.png`);
    await sharp(SOURCE)
      .resize(size, size, {
        fit: "cover",
        position: "center",
      })
      .png({
        compressionLevel: 9,
        quality: 100,
      })
      .toFile(outPath);
    console.log(`✓ logo-${size}.png`);
  }

  console.log(`\n✓ 所有图标已生成到 ${path.relative(process.cwd(), OUT_DIR)}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
