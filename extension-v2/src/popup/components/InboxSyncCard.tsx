/**
 * InboxSyncCard — 收件箱同步状态卡片
 *
 * 阶段 3：
 * - 显示 Lumio Inbox 未读数量
 * - 显示队列任务数（活跃/总数）
 * - 10s 轮询 Flask /stats（固定端口 38900，不依赖 FastAPI 随机端口）
 *
 * ★ 架构：插件只连 Flask 38900，不接触 FastAPI
 *   Flask /stats 返回 inbox_unread + queue_total + queue_active 等
 */
import { useEffect, useState } from "react";
import { useConnectionStore } from "../store/connection";

interface InboxState {
  unread: number;
  queueActive: number;
  queueTotal: number;
  loading: boolean;
  error: boolean;
}

export function InboxSyncCard() {
  const connected = useConnectionStore((s) => s.connected);
  const settings = useConnectionStore((s) => s.settings);
  const [state, setState] = useState<InboxState>({
    unread: 0,
    queueActive: 0,
    queueTotal: 0,
    loading: true,
    error: false,
  });

  const fetchData = async () => {
    if (!connected) {
      setState({ unread: 0, queueActive: 0, queueTotal: 0, loading: false, error: false });
      return;
    }
    try {
      const base = settings.apiBaseUrl.replace(/\/$/, "");
      const resp = await fetch(`${base}/stats`, {
        signal: AbortSignal.timeout(3000),
      });
      if (!resp.ok) {
        setState({ unread: 0, queueActive: 0, queueTotal: 0, loading: false, error: true });
        return;
      }
      const data = await resp.json();
      setState({
        unread: data.inbox_unread || 0,
        queueActive: data.queue_active || 0,
        queueTotal: data.queue_total || 0,
        loading: false,
        error: false,
      });
    } catch {
      setState({ unread: 0, queueActive: 0, queueTotal: 0, loading: false, error: true });
    }
  };

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, 10000);
    return () => clearInterval(id);
  }, [connected, settings.apiBaseUrl]);

  if (!connected) {
    return (
      <div className="glass-card p-3">
        <div className="flex items-center justify-between">
          <span className="text-xs text-text-muted">Inbox 状态</span>
          <span className="rounded-full bg-danger/15 px-2 py-0.5 text-[10px] text-danger">
            未连接
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="glass-card p-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-text">Lumio 状态</span>
        {state.loading ? (
          <span className="text-[10px] text-text-dim">加载中...</span>
        ) : state.error ? (
          <span className="text-[10px] text-warning">统计不可用</span>
        ) : (
          <span className="text-[10px] text-text-dim">实时同步</span>
        )}
      </div>

      <div className="mt-2 grid grid-cols-3 gap-2">
        <div className="rounded-lg bg-accent/10 px-2 py-1.5 text-center">
          <div className="text-base font-semibold text-accent">
            {state.unread > 99 ? "99+" : state.unread}
          </div>
          <div className="text-[10px] text-text-muted">Inbox</div>
        </div>
        <div className="rounded-lg bg-success/10 px-2 py-1.5 text-center">
          <div className="text-base font-semibold text-success">
            {state.queueActive > 99 ? "99+" : state.queueActive}
          </div>
          <div className="text-[10px] text-text-muted">下载中</div>
        </div>
        <div className="rounded-lg bg-text/10 px-2 py-1.5 text-center">
          <div className="text-base font-semibold text-text">
            {state.queueTotal > 99 ? "99+" : state.queueTotal}
          </div>
          <div className="text-[10px] text-text-muted">队列</div>
        </div>
      </div>
    </div>
  );
}
