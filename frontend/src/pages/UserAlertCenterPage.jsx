import { useEffect, useState } from "react";
import { toast } from "sonner";

import { FRONTEND_BACKEND_URL, getSessionDeviceId } from "@/lib/api";

export const UserAlertCenterPage = () => {
  const [snapshot, setSnapshot] = useState({ alerts: [], queue: { pending_decisions: [], pending_orders: [] } });
  const [streamState, setStreamState] = useState("connecting");

  useEffect(() => {
    const token = window.localStorage.getItem("token");
    if (!token || !FRONTEND_BACKEND_URL) return undefined;
    const base = FRONTEND_BACKEND_URL.replace(/\/$/, "");
    const wsUrl = base.startsWith("https://") ? `${base.replace("https://", "wss://")}/api/user/live/ws/stream` : `${base.replace("http://", "ws://")}/api/user/live/ws/stream`;
    let reconnectTimer = null;
    let socket = null;
    const connect = () => {
      const deviceId = getSessionDeviceId();
      socket = new WebSocket(`${wsUrl}?token=${encodeURIComponent(token)}&device_id=${encodeURIComponent(deviceId)}`);
      socket.onopen = () => setStreamState("connected");
      socket.onclose = () => {
        setStreamState("disconnected");
        reconnectTimer = window.setTimeout(connect, 2500);
      };
      socket.onerror = () => setStreamState("error");
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.event_type !== "user_live_snapshot") return;
          setSnapshot(payload);
        } catch {
          toast.error("Alert stream çözümlenemedi");
        }
      };
    };
    connect();
    const heartbeat = window.setInterval(() => {
      if (socket && socket.readyState === WebSocket.OPEN) socket.send("ping");
    }, 15000);
    return () => {
      window.clearInterval(heartbeat);
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      if (socket) socket.close();
    };
  }, []);

  return (
    <section className="space-y-4" data-testid="user-alert-center-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="user-alert-center-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-alert-center-title">Alert Center</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-alert-center-description">Risk alerts, execution alerts ve system alerts websocket ile canlı akar.</p>
        <p className="mt-2 font-mono text-xs text-slate-300" data-testid="user-alert-center-stream-state">stream={streamState}</p>
      </header>

      <div className="grid gap-4 xl:grid-cols-12" data-testid="user-alert-center-main-grid">
        <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-7" data-testid="user-alert-center-alerts-panel">
          <h3 className="text-base font-semibold" data-testid="user-alert-center-alerts-title">Notifications</h3>
          <div className="mt-3 space-y-2" data-testid="user-alert-center-alerts-list">
            {(snapshot.alerts || []).map((item, idx) => (
              <div key={`${item.code}-${idx}`} className="border border-amber-700 bg-amber-950/30 p-3" data-testid={`user-alert-center-alert-item-${idx}`}>
                <p className="text-xs uppercase tracking-wide text-amber-300" data-testid={`user-alert-center-alert-code-${idx}`}>{item.code}</p>
                <p className="text-sm text-slate-100" data-testid={`user-alert-center-alert-message-${idx}`}>{item.message}</p>
              </div>
            ))}
            {(snapshot.alerts || []).length === 0 && <p className="text-sm text-emerald-300" data-testid="user-alert-center-alerts-empty">Aktif alert yok</p>}
          </div>
        </article>

        <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-5" data-testid="user-alert-center-queue-panel">
          <h3 className="text-base font-semibold" data-testid="user-alert-center-queue-title">Queue Visibility</h3>
          <div className="mt-3 space-y-2" data-testid="user-alert-center-queue-list">
            {(snapshot.queue?.pending_orders || []).slice(0, 8).map((item, idx) => (
              <div key={`${item.intent_id}-${idx}`} className="border border-slate-700 p-2 text-xs" data-testid={`user-alert-center-queue-item-${idx}`}>
                <p className="font-mono">{item.intent_id}</p>
                <p>{item.symbol} · {item.status}</p>
              </div>
            ))}
          </div>
        </article>
      </div>
    </section>
  );
};
