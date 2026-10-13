#!/usr/bin/env python3
"""
sync-website-version.py — 发版后自动同步官网版本号

由 .github/workflows/website.yml 在 release published 时调用。
从 GitHub Release 读取 tag / assets / body，更新 website/ 下的硬编码版本信息，
然后 commit 到 main，Cloudflare Pages 随即自动重新构建部署。

更新目标：
  1. website/src/pages/index.astro            — const VERSION
  2. website/src/components/SiteFooter.astro  — const VERSION
  3. website/src/layouts/Layout.astro         — JSON-LD softwareVersion
  4. website/src/components/DownloadDialog.astro — FALLBACK_RELEASE（版本 + 资产列表）
  5. website/src/scripts/changelog.ts         — FALLBACK_RELEASES 数组头部插入新条目

用法：
  python3 sync-website-version.py --tag v4.5.0 --repo Roseannepark0211/Lumio
  需要 gh CLI 已登录（workflow 中使用 GITHUB_TOKEN）。

幂等：若 website 中的版本已是目标版本，直接退出（exit 0，不做任何修改）。
任一替换模式未命中则报错退出（exit 1），避免静默写坏文件。
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB = REPO_ROOT / 'website'

# 下载弹窗 fallback 只收录这 5 类安装包（与历史行为一致）
ASSET_RE = re.compile(r'\.(exe|dmg|AppImage|deb|rpm)$', re.IGNORECASE)


def gh_api(path: str):
    out = subprocess.run(
        ['gh', 'api', path, '--paginate'],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--tag', required=True, help='如 v4.5.0')
    ap.add_argument('--repo', required=True, help='如 Roseannepark0211/Lumio')
    args = ap.parse_args()

    version = args.tag.lstrip('v')
    print(f'目标版本: {version} (tag {args.tag})')

    # 幂等检查
    index_astro = (WEB / 'src/pages/index.astro').read_text(encoding='utf-8')
    if f"const VERSION = '{version}';" in index_astro:
        print('官网已是目标版本，无需更新')
        return 0

    # 拉取 release 信息
    rel = gh_api(f'repos/{args.repo}/releases/tags/{args.tag}')
    body = rel.get('body') or ''
    published = (rel.get('published_at') or '')[:10]
    tag_url = f'https://github.com/{args.repo}/releases/tag/{args.tag}'
    assets = [
        {'name': a['name'], 'url': a['browser_download_url'], 'size': a['size']}
        for a in rel.get('assets', [])
        if a.get('browser_download_url') and a.get('size', 0) > 0
        and ASSET_RE.search(a['name'])
    ]
    if not assets:
        print('警告：未找到安装包资产，FALLBACK 资产列表将为空', file=sys.stderr)
    print(f'资产: {len(assets)} 个')

    # 1/2. VERSION 常量
    for p in [WEB / 'src/pages/index.astro', WEB / 'src/components/SiteFooter.astro']:
        s = p.read_text(encoding='utf-8')
        s2, n = re.subn(r"const VERSION = '[^']+';", f"const VERSION = '{version}';", s, count=1)
        if n != 1:
            print(f'错误：{p.relative_to(REPO_ROOT)} VERSION 未命中', file=sys.stderr)
            sys.exit(1)
        p.write_text(s2, encoding='utf-8')
        print(f'已更新 {p.relative_to(REPO_ROOT)}')

    # 3. JSON-LD softwareVersion
    p = WEB / 'src/layouts/Layout.astro'
    s = p.read_text(encoding='utf-8')
    s2, n = re.subn(r'"softwareVersion": "[^"]+"', f'"softwareVersion": "{version}"', s, count=1)
    if n != 1:
        print('错误：Layout.astro softwareVersion 未命中', file=sys.stderr)
        sys.exit(1)
    p.write_text(s2, encoding='utf-8')
    print('已更新 website/src/layouts/Layout.astro (softwareVersion)')

    # 4. DownloadDialog FALLBACK_RELEASE
    asset_lines = []
    for a in assets:
        asset_lines.append(
            f"    {{\n"
            f"      name: '{a['name']}',\n"
            f"      url: '{a['url']}',\n"
            f"      size: {a['size']},\n"
            f"    }},"
        )
    new_block = (
        f"// 硬编码 fallback — 当前版本（v{version}）的资产数据\n"
        f"// 用于：构建时 fetch 失败（网络问题/限流）+ dev 模式跳过 fetch\n"
        f"// 发新 Release 后需手动更新此处（或 prod 构建时 fetch 成功则自动覆盖）\n"
        f"// 注：此块由 .github/workflows/website.yml 自动维护，请勿手工改版本号\n"
        f"const FALLBACK_RELEASE: ReleaseInfo = {{\n"
        f"  version: '{version}',\n"
        f"  assets: [\n" + "\n".join(asset_lines) + "\n  ],\n};"
    )
    p = WEB / 'src/components/DownloadDialog.astro'
    s = p.read_text(encoding='utf-8')
    pat = re.compile(r"// 硬编码 fallback — 当前版本.*?const FALLBACK_RELEASE: ReleaseInfo = \{.*?\n\};", re.S)
    s2, n = pat.subn(new_block, s, count=1)
    if n != 1:
        print('错误：DownloadDialog.astro FALLBACK_RELEASE 未命中', file=sys.stderr)
        sys.exit(1)
    p.write_text(s2, encoding='utf-8')
    print('已更新 website/src/components/DownloadDialog.astro (FALLBACK_RELEASE)')

    # 5. changelog.ts — 解析 release body 的 ### 段落，插入新条目
    sections = []
    cur_title, cur_items = None, []
    for line in body.splitlines():
        line = line.strip()
        if line.startswith('### '):
            if cur_title:
                sections.append((cur_title, cur_items))
            cur_title, cur_items = line[4:].strip(), []
        elif line.startswith('- ') and cur_title:
            cur_items.append(line[2:].strip())
    if cur_title:
        sections.append((cur_title, cur_items))
    if not sections:
        sections = [('✨ 更新', ['详见 GitHub Release 页面'])]

    sec_strs = []
    for title, items in sections:
        item_strs = "\n".join(f"          '{i.replace(chr(39), chr(34))}'," for i in items)
        sec_strs.append(
            f"      {{\n        title: '{title}',\n        items: [\n{item_strs}\n        ],\n      }},"
        )
    new_entry = (
        f"  {{\n    version: '{version}',\n    date: '{published}',\n"
        f"    sections: [\n" + "\n".join(sec_strs) + f"\n    ],\n    url: '{tag_url}',\n  }},\n"
    )
    p = WEB / 'src/scripts/changelog.ts'
    s = p.read_text(encoding='utf-8')
    anchor = 'export const FALLBACK_RELEASES: ParsedRelease[] = [\n'
    if anchor not in s:
        print('错误：changelog.ts FALLBACK_RELEASES 未命中', file=sys.stderr)
        sys.exit(1)
    # 保持最新 3 个版本：插入新条目后，若超过 3 个则移除最旧的一个
    s = s.replace(anchor, anchor + new_entry, 1)
    arr_start = s.index('export const FALLBACK_RELEASES: ParsedRelease[] = [')
    arr_end = s.index('\n];', arr_start)
    versions = re.findall(r"    version: '([^']+)',", s[arr_start:arr_end])
    if len(versions) > 3:
        oldest = versions[-1]
        pat_old = re.compile(r"  \{\n    version: '" + re.escape(oldest) + r"',.*?\n  \},\n", re.S)
        s, n = pat_old.subn('', s, count=1)
        print(f'移除最旧 fallback 条目 v{oldest}（保持最新 3 个）')
    p.write_text(s, encoding='utf-8')
    print(f'已更新 website/src/scripts/changelog.ts（新增 v{version}，当前: {versions[:3]}）')

    print('全部更新完成')
    return 0


if __name__ == '__main__':
    sys.exit(main())
