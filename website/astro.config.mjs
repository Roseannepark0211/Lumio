// @ts-check
import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';

// https://astro.build/config
export default defineConfig({
  // 部署站点 URL — 用于 sitemap/canonical URL 生成
  // 自定义域名优先；Cloudflare Pages 默认域名作为备用
  site: 'https://xksye7.dpdns.org',
  vite: {
    plugins: [tailwindcss()],
  },
});
