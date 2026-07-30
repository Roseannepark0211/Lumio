/**
 * types.ts — 共享类型定义
 */

export interface ReleaseInfo {
  /** Git tag，如 "v4.4.2" */
  tag_name: string;
  /** Release 标题，如 "V4.4.2" */
  name: string;
  /** 发布时间 ISO 字符串 */
  published_at: string;
  /** GitHub Release 页面 URL */
  html_url: string;
  /** Release body markdown 内容 */
  body: string;
  /** 是否草稿（GitHub API 字段） */
  draft?: boolean;
  /** 是否预发布（GitHub API 字段） */
  prerelease?: boolean;
}
