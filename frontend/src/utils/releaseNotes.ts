/**
 * 更新日志渲染工具。
 *
 * 根因（v4.5.3 对话框截图）：
 *   - Windows/Linux 走 electron-updater 的 GitHub Atom 源：GitHub 会把
 *     Release 的 Markdown 正文渲染成 HTML（<h2>/<p>/<table>……），
 *     再由 electron-updater 以 releaseNotes 字符串交给渲染进程；
 *   - macOS 手动模式走 GitHub API，拿到的是原始 Markdown 正文。
 *   而 UpdateDialog 原来把这两种输入都塞进 <pre> 当纯文本输出，
 *   于是 HTML 标签原样露出来，Markdown 符号同样不渲染。
 *
 * 修复策略（不引入 markdown/sanitize 依赖）：
 *   1. 先截取新版本「更新内容」一段：Release 模板全文还包括下载表、
 *      系统要求、安装说明、源码运行等内容，对话框只应显示新版本的
 *      更新日志，不显示这些模板内容；找不到「更新内容」一段时
 *      （如手工补写的简短正文）才回退到全文，避免丢信息；
 *   2. 含 HTML 标签的输入 → 白名单清洗后直接渲染；
 *   3. Markdown 输入 → 先转成同款 HTML，再走同一道清洗；
 *   4. 清洗只保留排版标签，剥掉全部属性；<a> 只留文字（渲染进程没有
 *      通用 open-external 桥接，点链接会让应用窗口导航走，干脆不保留
 *      href），<script>/<style>/<iframe>/<img> 等整棵丢弃。
 */

const ALLOWED_TAGS = new Set([
  "H1", "H2", "H3", "H4",
  "P", "UL", "OL", "LI", "HR", "BLOCKQUOTE", "PRE", "CODE",
  "STRONG", "EM", "B", "I", "SPAN", "BR",
  "TABLE", "THEAD", "TBODY", "TR", "TH", "TD",
]);

/** 整棵丢弃的标签（含子节点，不留文字） */
const DROP_SUBTREE_TAGS = new Set([
  "SCRIPT", "STYLE", "IFRAME", "OBJECT", "EMBED", "FORM",
  "INPUT", "BUTTON", "TEXTAREA", "SELECT", "SVG", "MATH",
  "LINK", "META", "TITLE", "HEAD",
]);

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function decodeBasicEntities(text: string): string {
  return text
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, "&");
}

/** 行内 Markdown：代码段优先占位，避免 ** / * 误伤代码里的符号 */
function inlineMarkdown(text: string): string {
  const codeSpans: string[] = [];
  let out = escapeHtml(text);
  out = out.replace(/`([^`]+)`/g, (_m, code: string) => {
    codeSpans.push(`<code>${code}</code>`);
    return `\u0000${codeSpans.length - 1}\u0000`;
  });
  // 粗体只处理 **，不处理 __：安装包文件名里有单下划线/双下划线
  // （如 lumio_4.5.3_amd64.deb），__ 规则很容易把文件名误当成粗体。
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  // 链接只留文字：见文件头注释，渲染进程没有通用外部打开能力。
  out = out.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, "$1");
  out = out.replace(/\u0000(\d+)\u0000/g, (_m, idx: string) => codeSpans[Number(idx)] ?? "");
  return out;
}

function splitTableRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((cell) => cell.trim());
}

function isTableSeparator(line: string): boolean {
  const trimmed = line.trim();
  return trimmed.includes("-") && /^[\s|:.-]+$/.test(trimmed);
}

function isBlockStart(line: string): boolean {
  const t = line.trim();
  return (
    t.startsWith("```") ||
    /^#{1,4}\s/.test(t) ||
    /^(-{3,}|\*{3,}|_{3,})$/.test(t) ||
    t.startsWith(">") ||
    /^[-*]\s/.test(t) ||
    /^\d+[.)]\s/.test(t)
  );
}

/**
 * 最小 Markdown → HTML：只覆盖 Release 模板实际用到的结构
 * （标题、分隔线、引用、列表、表格、代码块、段落），不求通用解析器。
 */
export function markdownToHtml(md: string): string {
  const lines = md.replace(/\r\n?/g, "\n").split("\n");
  const out: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();
    if (trimmed === "") {
      i += 1;
      continue;
    }

    // 代码块
    if (trimmed.startsWith("```")) {
      const body: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        body.push(lines[i]);
        i += 1;
      }
      i += 1; // 跳过结束 ```
      out.push(`<pre><code>${escapeHtml(body.join("\n"))}</code></pre>`);
      continue;
    }

    // 标题
    const heading = /^(#{1,4})\s+(.*)$/.exec(trimmed);
    if (heading) {
      out.push(`<h${heading[1].length}>${inlineMarkdown(heading[2])}</h${heading[1].length}>`);
      i += 1;
      continue;
    }

    // 分隔线
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      out.push("<hr>");
      i += 1;
      continue;
    }

    // 引用（连续的 > 行合并）
    if (trimmed.startsWith(">")) {
      const quotes: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) {
        quotes.push(lines[i].trim().replace(/^>\s?/, ""));
        i += 1;
      }
      out.push(`<blockquote>${quotes.map((q) => `<p>${inlineMarkdown(q)}</p>`).join("")}</blockquote>`);
      continue;
    }

    // 表格：表头行 + 分隔行 + 数据行
    if (
      trimmed.startsWith("|") &&
      i + 1 < lines.length &&
      isTableSeparator(lines[i + 1])
    ) {
      const header = splitTableRow(trimmed);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|") && !isTableSeparator(lines[i].trim())) {
        rows.push(splitTableRow(lines[i]));
        i += 1;
      }
      const headHtml = header.map((cell) => `<th>${inlineMarkdown(cell)}</th>`).join("");
      const bodyHtml = rows
        .map((row) => `<tr>${row.map((cell) => `<td>${inlineMarkdown(cell)}</td>`).join("")}</tr>`)
        .join("");
      out.push(`<table><thead><tr>${headHtml}</tr></thead><tbody>${bodyHtml}</tbody></table>`);
      continue;
    }

    // 列表（连续的列表行合并，取首行决定有序/无序）
    if (/^[-*]\s/.test(trimmed) || /^\d+[.)]\s/.test(trimmed)) {
      const ordered = /^\d+[.)]\s/.test(trimmed);
      const items: string[] = [];
      while (i < lines.length) {
        const lt = lines[i].trim();
        const m = /^(?:[-*]\s+|\d+[.)]\s+)(.*)$/.exec(lt);
        if (!m) break;
        items.push(m[1]);
        i += 1;
      }
      const tag = ordered ? "ol" : "ul";
      out.push(`<${tag}>${items.map((item) => `<li>${inlineMarkdown(item)}</li>`).join("")}</${tag}>`);
      continue;
    }

    // 段落：连续的普通行合并成一段
    const para: string[] = [trimmed];
    i += 1;
    while (i < lines.length) {
      const lt = lines[i].trim();
      if (lt === "" || isBlockStart(lt) || (lt.startsWith("|") && i + 1 < lines.length && isTableSeparator(lines[i + 1]))) {
        break;
      }
      para.push(lt);
      i += 1;
    }
    out.push(`<p>${inlineMarkdown(para.join(" "))}</p>`);
  }

  return out.join("\n");
}

/** 白名单清洗 HTML：只留排版标签，剥掉全部属性，危险标签整棵丢弃 */
export function sanitizeReleaseNotesHtml(html: string): string {
  if (typeof DOMParser === "undefined") {
    // 非浏览器环境兜底：去标签后转义，不让原始标签漏到界面上。
    const text = decodeBasicEntities(html.replace(/<[^>]*>/g, ""));
    return `<p>${escapeHtml(text).replace(/\n/g, "<br>")}</p>`;
  }

  const doc = new DOMParser().parseFromString(html, "text/html");
  const body = doc.body;

  const unwrap = (parent: Node, el: Element): void => {
    while (el.firstChild) {
      parent.insertBefore(el.firstChild, el);
    }
    parent.removeChild(el);
  };

  const clean = (parent: Node): void => {
    for (const child of Array.from(parent.childNodes)) {
      if (child.nodeType === Node.TEXT_NODE) continue;
      if (child.nodeType !== Node.ELEMENT_NODE) {
        parent.removeChild(child);
        continue;
      }
      const el = child as Element;
      const tag = el.tagName;
      if (DROP_SUBTREE_TAGS.has(tag)) {
        parent.removeChild(child);
        continue;
      }
      if (tag === "IMG") {
        const alt = el.getAttribute("alt");
        parent.replaceChild(doc.createTextNode(alt ? ` ${alt} ` : ""), child);
        continue;
      }
      if (tag === "A" || !ALLOWED_TAGS.has(tag)) {
        // <a> 只留文字（见文件头注释）；其他不在白名单的标签只剥标签留内容。
        clean(el);
        unwrap(parent, el);
        continue;
      }
      for (const attr of Array.from(el.attributes)) {
        el.removeAttribute(attr.name);
      }
      clean(el);
    }
  };

  clean(body);
  return body.innerHTML;
}

function stripTagsText(html: string): string {
  return decodeBasicEntities(html.replace(/<[^>]*>/g, "")).trim();
}

/**
 * 从 HTML 正文里截取「更新内容」一段：从含「更新内容」的标题之后，
 * 到下一个标题或分隔线之前。找不到则返回 null（调用方回退到全文）。
 */
export function extractChangelogSectionHtml(html: string): string | null {
  if (typeof DOMParser === "undefined") {
    // 非浏览器环境兜底：正则截取，浏览器里走下面的 DOM 路径。
    const heading = /<h[1-4][^>]*>[^<]*(?:更新内容|What's Changed|Changelog)[^<]*<\/h[1-4]>/i.exec(html);
    if (!heading) return null;
    const rest = html.slice(heading.index + heading[0].length);
    const end = rest.search(/<hr[\s/>]|<h[1-4][\s>]/i);
    const section = (end === -1 ? rest : rest.slice(0, end)).trim();
    return section && stripTagsText(section) ? section : null;
  }

  const doc = new DOMParser().parseFromString(html, "text/html");
  const headings = Array.from(doc.body.querySelectorAll("h1,h2,h3,h4"));
  const target = headings.find((h) =>
    /(更新内容|What's Changed|Changelog)/i.test(h.textContent ?? ""),
  );
  if (!target) return null;
  const holder = doc.createElement("div");
  let node: Node | null = target.nextSibling;
  while (node) {
    const next = node.nextSibling;
    if (node.nodeType === Node.ELEMENT_NODE) {
      const tag = (node as Element).tagName;
      if (tag === "HR" || /^H[1-4]$/.test(tag)) break;
    }
    holder.appendChild(node);
    node = next;
  }
  const section = holder.innerHTML.trim();
  return section && (holder.textContent ?? "").trim() ? section : null;
}

/**
 * 从 Markdown 正文里截取「更新内容」一段：从含「更新内容」的标题行之后，
 * 到下一个标题行或 --- 分隔线之前。找不到则返回 null。
 */
export function extractChangelogSectionMarkdown(md: string): string | null {
  const lines = md.replace(/\r\n?/g, "\n").split("\n");
  const start = lines.findIndex((l) =>
    /^#{1,4}\s+.*(?:更新内容|What's Changed|Changelog)/i.test(l.trim()),
  );
  if (start === -1) return null;
  const section: string[] = [];
  for (let i = start + 1; i < lines.length; i += 1) {
    const t = lines[i].trim();
    if (/^#{1,4}\s/.test(t) || /^(-{3,}|\*{3,})$/.test(t)) break;
    section.push(lines[i]);
  }
  const text = section.join("\n").trim();
  return text ? text : null;
}

/** 统一入口：HTML 或 Markdown 输入都返回可直接渲染的安全 HTML */
export function renderReleaseNotes(notes: string | null | undefined): string {
  if (!notes) return "";
  const trimmed = notes.trim();
  if (!trimmed) return "";
  if (/<[a-zA-Z][\s\S]*?>/.test(trimmed)) {
    const section = extractChangelogSectionHtml(trimmed);
    if (section) {
      const rendered = sanitizeReleaseNotesHtml(section);
      if (stripTagsText(rendered)) return rendered;
    }
    return sanitizeReleaseNotesHtml(trimmed);
  }
  const section = extractChangelogSectionMarkdown(trimmed);
  if (section) {
    const rendered = sanitizeReleaseNotesHtml(markdownToHtml(section));
    if (stripTagsText(rendered)) return rendered;
  }
  return sanitizeReleaseNotesHtml(markdownToHtml(trimmed));
}
