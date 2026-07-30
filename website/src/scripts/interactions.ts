/**
 * interactions.ts — Lumio 官网交互层 v4
 *
 * 设计方向（直角基调）：
 * 1. 滚动进度条 — transform: scaleX()，rAF 节流
 * 2. 鼠标光晕 — transform 移动，独立合成层（桌面端）
 * 3. Web Audio API 合成机械直角咔哒声音效（方波 + 高通滤波）
 *    仅挂载主 CTA 按钮 + 平台卡片 + 控制条开关，避免泛滥
 * 4. IntersectionObserver 触发 reveal + 视口外暂停动画
 * 5. 暗夜模式切换 — 手动覆盖 + localStorage 持久化
 *    未设置时跟随系统 prefers-color-scheme
 * 6. 音效默认关闭，用户首次开启后激活 AudioContext
 */

interface SoundConfig {
  enabled: boolean;
  volume: number;
}

type ThemeMode = 'light' | 'dark';

class LumioInteractions {
  private progress: HTMLElement | null = null;
  private cursorGlow: HTMLElement | null = null;
  private observer: IntersectionObserver | null = null;
  private rafId: number | null = null;
  private lastScrollY = 0;

  // 音效系统
  private audioCtx: AudioContext | null = null;
  private soundConfig: SoundConfig = { enabled: false, volume: 0.18 };
  private soundToggle: HTMLElement | null = null;

  // 暗夜模式
  private themeToggle: HTMLElement | null = null;

  init() {
    if (typeof window === 'undefined') return;

    this.progress = document.getElementById('scroll-progress');
    this.cursorGlow = document.getElementById('cursor-glow');
    this.soundToggle = document.getElementById('sound-toggle');
    this.themeToggle = document.getElementById('theme-toggle');

    this.setupScrollProgress();
    this.setupCursorGlow();
    this.setupRevealObserver();
    this.setupSoundSystem();
    this.setupThemeToggle();
    this.setupInteractionSounds();
    this.setupMobileMenu();
    this.setupLazyVideos();
    this.setupDownloadDialog();
  }

  // ============================================================
  // 视频懒加载 — IntersectionObserver
  //   - 默认 data-src（不加载资源）
  //   - 进入视口：赋值 src + play
  //   - 离开视口：pause（保留 src，再次进入直接 play）
  //   - 首屏已可见的视频会在 observer 触发时立即加载
  // ============================================================
  private setupLazyVideos() {
    const videos = document.querySelectorAll<HTMLVideoElement>('video[data-src]');
    if (videos.length === 0) return;

    if (!('IntersectionObserver' in window)) {
      // 不支持 IO：直接加载所有视频
      videos.forEach((v) => {
        v.src = v.dataset.src || '';
        v.play().catch(() => {});
      });
      return;
    }

    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          const v = entry.target as HTMLVideoElement;
          if (entry.isIntersecting) {
            // 首次进入视口：赋值 src 触发加载
            if (!v.src && v.dataset.src) {
              v.src = v.dataset.src;
              v.load();
            }
            // 尝试播放，失败则忽略（用户未交互时浏览器可能拦截）
            v.play().catch(() => {});
          } else {
            // 离开视口：暂停节省 CPU
            v.pause();
          }
        });
      },
      { threshold: 0.25, rootMargin: '100px 0px' }
    );

    videos.forEach((v) => io.observe(v));
  }

  // ============================================================
  // 移动端汉堡菜单 — < 768px 显示
  // 点击按钮展开/折叠，点击链接自动关闭
  // ============================================================
  private setupMobileMenu() {
    const toggle = document.getElementById('mobile-menu-toggle');
    const menu = document.getElementById('mobile-menu');
    if (!toggle || !menu) return;

    const closeMenu = () => {
      toggle.classList.remove('is-open');
      menu.classList.remove('is-open');
      toggle.setAttribute('aria-expanded', 'false');
      toggle.setAttribute('aria-label', '打开菜单');
    };

    const openMenu = () => {
      toggle.classList.add('is-open');
      menu.classList.add('is-open');
      toggle.setAttribute('aria-expanded', 'true');
      toggle.setAttribute('aria-label', '关闭菜单');
    };

    toggle.addEventListener('click', (e) => {
      e.stopPropagation();
      if (toggle.classList.contains('is-open')) {
        closeMenu();
      } else {
        openMenu();
      }
    });

    // 点击面板内链接自动关闭
    menu.querySelectorAll('[data-close]').forEach((link) => {
      link.addEventListener('click', closeMenu);
    });

    // 点击页面外部关闭
    document.addEventListener('click', (e) => {
      if (!toggle.classList.contains('is-open')) return;
      const target = e.target as Node;
      if (!menu.contains(target) && !toggle.contains(target)) {
        closeMenu();
      }
    });

    // 按 Esc 关闭
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && toggle.classList.contains('is-open')) {
        closeMenu();
        toggle.focus();
      }
    });

    // 窗口尺寸变化到桌面端时关闭
    window.addEventListener('resize', () => {
      if (window.innerWidth >= 768 && toggle.classList.contains('is-open')) {
        closeMenu();
      }
    });
  }

  // ============================================================
  // 下载弹窗 — 原生 <dialog> + 构建时预取数据
  //   - [data-download-trigger] 触发 → showModal()
  //   - release 数据在构建时 fetch 并写入 <script type="application/json">
  //   - 运行时零 fetch，直接读取 JSON 渲染（不受用户网络影响）
  //   - 构建时 fetch 失败 → 显示 fallback（指向 /releases/latest）
  //   - 资产按扩展名分类：.exe → Windows / .dmg → macOS / .AppImage .deb .rpm → Linux
  //   - 点击 backdrop 或 ESC 自动关闭（原生 dialog 行为）
  //   - 文件实际走 GitHub CDN，本站零流量
  // ============================================================
  private setupDownloadDialog() {
    const dialog = document.getElementById('download-dialog') as HTMLDialogElement | null;
    if (!dialog) return;

    const triggers = document.querySelectorAll('[data-download-trigger]');
    const platformsEl = dialog.querySelector('[data-dl-platforms]') as HTMLElement | null;
    const fallbackEl = dialog.querySelector('[data-dl-fallback]') as HTMLElement | null;
    const versionEl = dialog.querySelector('[data-dl-version]') as HTMLElement | null;
    const closeBtn = dialog.querySelector('[data-dl-close]') as HTMLButtonElement | null;
    const dataScript = document.getElementById('dl-release-data') as HTMLScriptElement | null;

    if (!platformsEl || !fallbackEl || !versionEl) return;

    interface ReleaseAsset {
      name: string;
      url: string;
      size: number;
    }
    interface ReleaseInfo {
      version: string;
      assets: ReleaseAsset[];
    }

    const formatSize = (bytes: number): string => {
      if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
      return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    };

    const platformIcon = (kind: 'windows' | 'macos' | 'linux'): string => {
      const paths: Record<string, string> = {
        windows: 'M3 5.5L10.5 4.4v7.1H3V5.5zm0 13L10.5 19.6v-7.1H3v6.0zm8.0 1.2L21 21V12.5h-10v7.2zm0-15.4v7.4h10V3l-10 1.3z',
        macos: 'M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.14 17 2.94 12.45 4.7 9.36c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.85M13.5 4.5c.7-.85 1.17-2.04 1.04-3.21-1.01.04-2.23.67-2.95 1.52-.65.74-1.22 1.93-1.07 3.08 1.13.09 2.29-.57 2.98-1.39',
        linux: 'M12.504 0c-.155 0-.315.008-.48.021-4.226.333-3.105 4.807-3.17 6.298-.076 1.092-.3 1.953-1.05 3.02-.885 1.051-2.127 2.75-2.716 4.521-.278.832-.41 1.684-.287 2.489a.424.424 0 00-.11.135c-.26.268-.45.6-.663.839-.199.199-.485.267-.797.4-.313.136-.658.269-.864.68-.09.189-.136.394-.132.602 0 .199.027.4.055.536.058.399.116.728.04.97-.249.68-.28 1.145-.106 1.484.174.334.535.47.94.601.81.2 1.91.135 2.774.6.926.466 1.866.67 2.616.47.526-.116.97-.464 1.208-.946.587-.003 1.23-.269 2.26-.334.699-.058 1.574.267 2.577.2.025.134.063.198.114.333l.003.003c.391.778 1.113 1.132 1.884 1.071.771-.06 1.592-.536 2.257-1.306.631-.765 1.683-1.084 2.378-1.503.348-.199.629-.469.649-.853.023-.4-.2-.811-.714-1.376v-.097l-.003-.003c-.17-.2-.25-.535-.338-.926-.085-.401-.182-.786-.492-1.046h-.003c-.059-.054-.123-.067-.188-.135a.357.357 0 00-.19-.064c.431-1.278.264-2.55-.173-3.694-.533-1.41-1.465-2.638-2.175-3.483-.796-1.005-1.576-1.957-1.56-3.368.026-2.152.236-6.133-3.544-6.139z',
      };
      return `<svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="${paths[kind]}"/></svg>`;
    };

    const renderPlatforms = (info: ReleaseInfo) => {
      const { version, assets } = info;

      // 按扩展名分类
      const windows = assets.find((a) => a.name.endsWith('.exe') && !a.name.endsWith('.blockmap'));
      const macos = assets.find((a) => a.name.endsWith('.dmg') && !a.name.endsWith('.blockmap'));
      const linuxAssets = assets.filter((a) =>
        a.name.endsWith('.AppImage') || a.name.endsWith('.deb') || a.name.endsWith('.rpm')
      );

      versionEl.textContent = version ? `Lumio V${version}` : 'Lumio';

      const cards: string[] = [];

      // Windows 卡片
      if (windows) {
        cards.push(`
          <div class="dl-platform">
            <div class="dl-platform__icon">${platformIcon('windows')}</div>
            <div class="dl-platform__info">
              <p class="dl-platform__name">Windows 10 / 11</p>
              <p class="dl-platform__meta">${windows.name} · ${formatSize(windows.size)}</p>
            </div>
            <a class="dl-platform__btn" href="${windows.url}" target="_blank" rel="noopener">
              下载
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="square" aria-hidden="true">
                <line x1="5" y1="12" x2="19" y2="12"/>
                <polyline points="12 5 19 12 12 19"/>
              </svg>
            </a>
          </div>
        `);
      }

      // macOS 卡片
      if (macos) {
        const arch = macos.name.includes('arm64') ? 'Apple Silicon' : macos.name.includes('x64') ? 'Intel' : '';
        cards.push(`
          <div class="dl-platform">
            <div class="dl-platform__icon">${platformIcon('macos')}</div>
            <div class="dl-platform__info">
              <p class="dl-platform__name">macOS${arch ? ` · ${arch}` : ''}</p>
              <p class="dl-platform__meta">${macos.name} · ${formatSize(macos.size)}</p>
            </div>
            <a class="dl-platform__btn" href="${macos.url}" target="_blank" rel="noopener">
              下载
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="square" aria-hidden="true">
                <line x1="5" y1="12" x2="19" y2="12"/>
                <polyline points="12 5 19 12 12 19"/>
              </svg>
            </a>
          </div>
        `);
      }

      // Linux 卡片（多发行版按钮）
      if (linuxAssets.length > 0) {
        const variants = linuxAssets.map((a) => {
          const label = a.name.endsWith('.AppImage') ? 'AppImage'
            : a.name.endsWith('.deb') ? 'deb'
            : 'rpm';
          return `<a class="dl-variant" href="${a.url}" target="_blank" rel="noopener" title="${a.name} · ${formatSize(a.size)}">${label}</a>`;
        }).join('');
        const primary = linuxAssets.find((a) => a.name.endsWith('.AppImage')) || linuxAssets[0];
        cards.push(`
          <div class="dl-platform">
            <div class="dl-platform__icon">${platformIcon('linux')}</div>
            <div class="dl-platform__info">
              <p class="dl-platform__name">Linux</p>
              <p class="dl-platform__meta">${primary.name} · ${formatSize(primary.size)}</p>
            </div>
            <div class="dl-platform__variants">${variants}</div>
          </div>
        `);
      }

      // 兜底：如果都没匹配到，展示所有资产
      if (cards.length === 0 && assets.length > 0) {
        const fallback = assets.map((a) => `
          <div class="dl-platform">
            <div class="dl-platform__info">
              <p class="dl-platform__name">${a.name}</p>
              <p class="dl-platform__meta">${formatSize(a.size)}</p>
            </div>
            <a class="dl-platform__btn" href="${a.url}" target="_blank" rel="noopener">下载</a>
          </div>
        `).join('');
        cards.push(fallback);
      }

      platformsEl.innerHTML = cards.join('');
      platformsEl.hidden = false;
      fallbackEl.hidden = true;
    };

    const showFallback = () => {
      platformsEl.hidden = true;
      fallbackEl.hidden = false;
    };

    // 从构建时 JSON 读取数据（零运行时 fetch）
    const loadRelease = () => {
      if (!dataScript) {
        showFallback();
        return;
      }
      try {
        const raw = dataScript.textContent || '';
        const info = JSON.parse(raw) as ReleaseInfo | null;
        if (info && info.assets && info.assets.length > 0) {
          renderPlatforms(info);
        } else {
          showFallback();
        }
      } catch {
        showFallback();
      }
    };

    // 立即加载（数据已在 HTML 中，同步渲染）
    loadRelease();

    const openDialog = () => {
      if (typeof dialog.showModal !== 'function') {
        // 浏览器不支持 <dialog>，回退到直接跳 GitHub Releases
        window.open('https://github.com/Roseannepark0211/Lumio/releases/latest', '_blank', 'noopener');
        return;
      }
      if (dialog.open) return;
      dialog.showModal();
      this.playClick(1.0);
    };

    const closeDialog = () => {
      if (dialog.open) dialog.close();
    };

    // 触发按钮
    triggers.forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        openDialog();
      });
    });

    // 关闭按钮
    closeBtn?.addEventListener('click', closeDialog);

    // 点击 backdrop 关闭（点击 dialog 自身而非内部内容）
    dialog.addEventListener('click', (e) => {
      if (e.target === dialog) closeDialog();
    });
  }

  // ============================================================
  // 滚动进度条 — rAF 节流，transform 驱动避免 layout
  // ============================================================
  private setupScrollProgress() {
    if (!this.progress) return;

    const update = () => {
      this.rafId = null;
      const scrollTop = window.scrollY;
      const docHeight = document.documentElement.scrollHeight - window.innerHeight;
      const pct = docHeight > 0 ? scrollTop / docHeight : 0;
      this.progress!.style.transform = `scaleX(${pct})`;
    };

    const onScroll = () => {
      this.lastScrollY = window.scrollY;
      if (this.rafId === null) {
        this.rafId = requestAnimationFrame(update);
      }
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    update();
  }

  // ============================================================
  // 鼠标光晕 — lerp 平滑跟随，独立合成层
  // ============================================================
  private setupCursorGlow() {
    if (!this.cursorGlow) return;
    if (window.matchMedia('(max-width: 768px)').matches) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    let targetX = window.innerWidth / 2;
    let targetY = window.innerHeight / 2;
    let currentX = targetX;
    let currentY = targetY;
    let glowRafId: number | null = null;

    const onMove = (e: MouseEvent) => {
      targetX = e.clientX;
      targetY = e.clientY;
      if (glowRafId === null) {
        glowRafId = requestAnimationFrame(tick);
      }
    };

    const tick = () => {
      glowRafId = null;
      currentX += (targetX - currentX) * 0.15;
      currentY += (targetY - currentY) * 0.15;

      if (Math.abs(targetX - currentX) > 0.5 || Math.abs(targetY - currentY) > 0.5) {
        glowRafId = requestAnimationFrame(tick);
      }

      this.cursorGlow!.style.transform = `translate(${currentX}px, ${currentY}px) translate(-50%, -50%)`;
    };

    window.addEventListener('mousemove', onMove, { passive: true });
  }

  // ============================================================
  // Reveal 动画 — IntersectionObserver
  // ============================================================
  private setupRevealObserver() {
    if (!('IntersectionObserver' in window)) {
      document.querySelectorAll('.reveal').forEach((el) => el.classList.add('is-visible'));
      return;
    }

    this.observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            this.observer!.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -40px 0px' }
    );

    document.querySelectorAll('.reveal').forEach((el) => this.observer!.observe(el));
  }

  // ============================================================
  // Web Audio — 机械直角咔哒声
  //
  // 信号链：方波振荡器 → 高通滤波器 → 增益包络 → destination
  //   - 方波提供「直角 / 数字」基音
  //   - 高通滤波器（1.6kHz）去掉低频轰隆，保留尖锐"咔哒"质感
  //   - ADSR：1ms attack → 30ms decay → 0，短促不拖尾
  //   - 双层叠加：高频短音 + 低频长音，模拟机械按键「咔-哒」双层质感
  // ============================================================
  private setupSoundSystem() {
    if (!this.soundToggle) return;

    const saved = localStorage.getItem('lumio-sound');
    if (saved === 'true') {
      this.soundConfig.enabled = true;
      this.soundToggle.classList.add('is-active');
      this.soundToggle.setAttribute('aria-pressed', 'true');
      this.soundToggle.setAttribute('aria-label', '关闭音效');
    } else {
      this.soundToggle.setAttribute('aria-pressed', 'false');
      this.soundToggle.setAttribute('aria-label', '开启音效');
    }

    this.soundToggle.addEventListener('click', (e) => {
      e.preventDefault();
      this.soundConfig.enabled = !this.soundConfig.enabled;
      localStorage.setItem('lumio-sound', String(this.soundConfig.enabled));

      if (this.soundConfig.enabled) {
        this.soundToggle!.classList.add('is-active');
        this.soundToggle!.setAttribute('aria-pressed', 'true');
        this.soundToggle!.setAttribute('aria-label', '关闭音效');
        // 激活时播放机械确认音
        this.playClick(1.0);
      } else {
        this.soundToggle!.classList.remove('is-active');
        this.soundToggle!.setAttribute('aria-pressed', 'false');
        this.soundToggle!.setAttribute('aria-label', '开启音效');
        // 关闭时仍播一次轻音作为反馈（之后不再响）
        this.playClick(0.6);
      }
    });
  }

  private ensureAudioContext(): boolean {
    if (this.audioCtx) return true;
    try {
      const Ctx = window.AudioContext || (window as any).webkitAudioContext;
      this.audioCtx = new Ctx();
      return true;
    } catch {
      return false;
    }
  }

  /**
   * 播放机械直角咔哒声
   *
   * 实现：
   *   - 第一层：方波 2200Hz，超短 8ms，做"咔"
   *   - 第二层：方波 660Hz，稍长 30ms，做"哒"
   *   - 共用 BiquadFilter 高通 1.6kHz 滤去闷音
   *   - 整体音量乘以 intensity（0..1）作为情境缩放
   *
   * @param intensity 音量系数 0..1（hover=0.6，click=1.0）
   */
  private playClick(intensity = 1.0) {
    if (!this.soundConfig.enabled) return;
    if (!this.ensureAudioContext()) return;
    if (!this.audioCtx) return;

    // 浏览器自动播放策略：suspended 时需 resume
    if (this.audioCtx.state === 'suspended') {
      this.audioCtx.resume();
    }

    const ctx = this.audioCtx;
    const now = ctx.currentTime;
    const baseVol = this.soundConfig.volume * intensity;

    // ── 第一层：高频「咔」─ 1ms attack, 8ms decay ──
    this.emitLayer({
      ctx,
      now,
      freq: 2200,
      duration: 0.012,
      gain: baseVol * 0.85,
      attackMs: 1,
      filterFreq: 2400,
      filterQ: 1.2,
    });

    // ── 第二层：中频「哒」─ 2ms attack, 30ms decay，延迟 4ms ──
    this.emitLayer({
      ctx,
      now: now + 0.004,
      freq: 660,
      duration: 0.04,
      gain: baseVol * 0.55,
      attackMs: 2,
      filterFreq: 1600,
      filterQ: 0.8,
    });
  }

  /**
   * 单层方波 + 高通滤波 + 增益包络
   */
  private emitLayer(opts: {
    ctx: AudioContext;
    now: number;
    freq: number;
    duration: number;
    gain: number;
    attackMs: number;
    filterFreq: number;
    filterQ: number;
  }) {
    const { ctx, now, freq, duration, gain, attackMs, filterFreq, filterQ } = opts;

    const osc = ctx.createOscillator();
    const filter = ctx.createBiquadFilter();
    const gainNode = ctx.createGain();

    // 方波 — 直角数字质感
    osc.type = 'square';
    osc.frequency.setValueAtTime(freq, now);

    // 高通滤波 — 去掉低频轰隆，保留尖锐瞬态
    filter.type = 'highpass';
    filter.frequency.setValueAtTime(filterFreq, now);
    filter.Q.setValueAtTime(filterQ, now);

    // ADSR — 短促衰减，无 sustain
    const attackSec = attackMs / 1000;
    gainNode.gain.setValueAtTime(0, now);
    gainNode.gain.linearRampToValueAtTime(gain, now + attackSec);
    gainNode.gain.exponentialRampToValueAtTime(0.0001, now + duration);

    osc.connect(filter);
    filter.connect(gainNode);
    gainNode.connect(ctx.destination);

    osc.start(now);
    osc.stop(now + duration + 0.005);
  }

  // ============================================================
  // 暗夜模式切换
  //   - 优先级：localStorage > prefers-color-scheme
  //   - 切换时同时更新按钮 is-active + aria-pressed
  //   - 播放机械咔哒声作为反馈
  // ============================================================
  private setupThemeToggle() {
    if (!this.themeToggle) return;

    // 初始化按钮状态
    this.syncThemeButtonState();

    this.themeToggle.addEventListener('click', (e) => {
      e.preventDefault();
      const current = this.getCurrentTheme();
      const next: ThemeMode = current === 'dark' ? 'light' : 'dark';

      this.applyTheme(next);
      localStorage.setItem('lumio-theme', next);
      this.playClick(1.0);
    });
  }

  /**
   * 获取当前主题
   *   - 有 data-theme 属性就用它
   *   - 没有就跟随系统 prefers-color-scheme
   */
  private getCurrentTheme(): ThemeMode {
    const attr = document.documentElement.getAttribute('data-theme');
    if (attr === 'dark' || attr === 'light') return attr;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  private applyTheme(mode: ThemeMode) {
    document.documentElement.setAttribute('data-theme', mode);
    this.syncThemeButtonState();
  }

  private syncThemeButtonState() {
    if (!this.themeToggle) return;
    const current = this.getCurrentTheme();
    if (current === 'dark') {
      this.themeToggle.classList.add('is-active');
      this.themeToggle.setAttribute('aria-pressed', 'true');
      this.themeToggle.setAttribute('aria-label', '切换亮色模式');
    } else {
      this.themeToggle.classList.remove('is-active');
      this.themeToggle.setAttribute('aria-pressed', 'false');
      this.themeToggle.setAttribute('aria-label', '切换暗夜模式');
    }
  }

  // ============================================================
  // 交互音效挂载
  //   设计原则：仅在主 CTA + 关键卡片上挂音效，避免音效泛滥
  //   挂载点：
  //     - .btn-primary       — 主 CTA 按钮（click 强音 + hover 轻音）
  //     - .btn-ghost         — 次按钮（click + hover）
  //     - .platform-tile     — 8 平台卡片（click + hover）
  //     - .control-strip__btn — 控制条按钮（click，已在自身 setup 中处理）
  // ============================================================
  private setupInteractionSounds() {
    // hover 轻音 — intensity 0.55
    const onHover = () => this.playClick(0.55);

    // click 强音 — intensity 1.0
    const onClick = () => this.playClick(1.0);

    // 主 CTA + 次按钮
    document.querySelectorAll('.btn-primary, .btn-ghost').forEach((btn) => {
      btn.addEventListener('mouseenter', onHover, { passive: true });
      btn.addEventListener('click', onClick);
    });

    // 平台卡片 — hover + click 都用机械音
    document.querySelectorAll('.platform-tile').forEach((el) => {
      el.addEventListener('mouseenter', onHover, { passive: true });
      el.addEventListener('click', onClick);
    });
  }

  destroy() {
    if (this.rafId !== null) cancelAnimationFrame(this.rafId);
    if (this.observer) this.observer.disconnect();
    if (this.audioCtx) this.audioCtx.close();
  }
}

const interactions = new LumioInteractions();

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => interactions.init());
} else {
  interactions.init();
}

export {};
