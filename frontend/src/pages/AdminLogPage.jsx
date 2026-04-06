import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

const AUTO_REFRESH_MS = 5000;
const LOG_LIMIT = 50;

const formatDateTime = (value) => {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("tr-TR", { hour12: false });
};

const severityClass = {
  info: "bg-cyan-900/30 text-cyan-200",
  warning: "bg-amber-900/30 text-amber-200",
  critical: "bg-rose-900/30 text-rose-200",
  error: "bg-rose-900/30 text-rose-200",
};

export const AdminLogPage = () => {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState([]);
  const [errorLogs, setErrorLogs] = useState([]);
  const [meta, setMeta] = useState({
    refreshedAt: null,
    roleBreakdown: {},
    scannedCount: 0,
  });

  const fetchLogs = useCallback(async ({ silent = false } = {}) => {
    if (!silent) {
      setLoading(true);
    }
    try {
      const sharedParams = {
        limit: LOG_LIMIT,
        actor_roles: "admin,user",
        q: query.trim() || undefined,
      };

      const [allRes, errRes] = await Promise.all([
        apiClient.get("/audit-logs/admin/log-feed", { params: sharedParams }),
        apiClient.get("/audit-logs/admin/log-feed", { params: { ...sharedParams, include_error_only: true } }),
      ]);

      const allData = allRes?.data || {};
      const errData = errRes?.data || {};

      setLogs(Array.isArray(allData.items) ? allData.items : []);
      setErrorLogs(Array.isArray(errData.items) ? errData.items : []);
      setMeta({
        refreshedAt: allData.refreshed_at || null,
        roleBreakdown: allData.role_breakdown || {},
        scannedCount: Number(allData.total_scanned || 0),
      });
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Admin log feed alınamadı", { id: "admin-log-feed-error" });
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  }, [query]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  useEffect(() => {
    const timer = setInterval(() => {
      if (typeof document !== "undefined" && document.hidden) {
        return;
      }
      fetchLogs({ silent: true });
    }, AUTO_REFRESH_MS);
    return () => clearInterval(timer);
  }, [fetchLogs]);

  const roleSummary = useMemo(() => {
    const adminCount = Number(meta.roleBreakdown?.admin || 0) + Number(meta.roleBreakdown?.super_admin || 0) + Number(meta.roleBreakdown?.ops || 0);
    const userCount = Number(meta.roleBreakdown?.user || 0);
    return { adminCount, userCount };
  }, [meta.roleBreakdown]);

  return (
    <section className="space-y-6" data-testid="admin-log-page">
      <header className="rounded-2xl border border-slate-700 bg-slate-950/70 p-6" data-testid="admin-log-header">
        <h1 className="text-4xl font-black text-slate-100" data-testid="admin-log-title">Admin Log</h1>
        <p className="mt-2 text-sm text-slate-300" data-testid="admin-log-subtitle">
          Son {LOG_LIMIT} kayıt (en yeni en üstte) · admin + user hata/log akışı · auto-refresh 5sn
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-3" data-testid="admin-log-controls">
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Aksiyon, entity veya detay içinde ara"
            className="max-w-lg border-slate-600 bg-slate-900 text-slate-100"
            data-testid="admin-log-search-input"
          />
          <Button
            type="button"
            onClick={() => fetchLogs()}
            disabled={loading}
            className="inline-flex items-center gap-2"
            data-testid="admin-log-refresh-button"
          >
            <RefreshCw size={16} />
            {loading ? "Yükleniyor..." : "Yenile"}
          </Button>
          <span className="text-xs text-slate-400" data-testid="admin-log-last-refreshed-at">
            son_güncelleme: {formatDateTime(meta.refreshedAt)}
          </span>
        </div>
      </header>

      <div className="grid gap-3 md:grid-cols-4" data-testid="admin-log-summary-grid">
        <article className="rounded-xl border border-slate-700 bg-slate-950/60 p-4" data-testid="admin-log-summary-scanned">
          <p className="text-xs uppercase tracking-widest text-slate-400">taranan</p>
          <p className="mt-1 text-2xl font-bold text-slate-100" data-testid="admin-log-summary-scanned-value">{meta.scannedCount}</p>
        </article>
        <article className="rounded-xl border border-slate-700 bg-slate-950/60 p-4" data-testid="admin-log-summary-list-size">
          <p className="text-xs uppercase tracking-widest text-slate-400">log listesi</p>
          <p className="mt-1 text-2xl font-bold text-slate-100" data-testid="admin-log-summary-list-size-value">{logs.length}</p>
        </article>
        <article className="rounded-xl border border-rose-700 bg-rose-950/20 p-4" data-testid="admin-log-summary-error-size">
          <p className="text-xs uppercase tracking-widest text-rose-300">hata listesi</p>
          <p className="mt-1 text-2xl font-bold text-rose-200" data-testid="admin-log-summary-error-size-value">{errorLogs.length}</p>
        </article>
        <article className="rounded-xl border border-slate-700 bg-slate-950/60 p-4" data-testid="admin-log-summary-role-split">
          <p className="text-xs uppercase tracking-widest text-slate-400">rol dağılımı</p>
          <p className="mt-1 text-sm text-slate-200" data-testid="admin-log-summary-role-admin">admin={roleSummary.adminCount}</p>
          <p className="text-sm text-slate-200" data-testid="admin-log-summary-role-user">user={roleSummary.userCount}</p>
        </article>
      </div>

      <section className="rounded-2xl border border-slate-700 bg-slate-950/40 p-4" data-testid="admin-log-main-list-section">
        <h2 className="text-base font-semibold text-slate-100" data-testid="admin-log-main-list-title">Log Akışı (50)</h2>
        <div className="mt-3 overflow-x-auto" data-testid="admin-log-main-list-table-wrap">
          <Table data-testid="admin-log-main-list-table">
            <TableHeader>
              <TableRow>
                <TableHead>Zaman</TableHead>
                <TableHead>Rol</TableHead>
                <TableHead>Severity</TableHead>
                <TableHead>Aksiyon</TableHead>
                <TableHead>Route</TableHead>
                <TableHead>Hata Sınıfı</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {logs.length === 0 ? (
                <TableRow data-testid="admin-log-main-list-empty-row">
                  <TableCell colSpan={6} className="text-center text-slate-400" data-testid="admin-log-main-list-empty-message">kayıt yok</TableCell>
                </TableRow>
              ) : (
                logs.map((row, index) => (
                  <TableRow key={row.id || `${row.created_at}-${index}`} data-testid={`admin-log-main-list-row-${index}`}>
                    <TableCell data-testid={`admin-log-main-list-time-${index}`}>{formatDateTime(row.created_at)}</TableCell>
                    <TableCell data-testid={`admin-log-main-list-role-${index}`}>{row.actor_role || "-"}</TableCell>
                    <TableCell data-testid={`admin-log-main-list-severity-${index}`}>
                      <span className={`rounded px-2 py-1 text-xs ${severityClass[String(row.severity || "").toLowerCase()] || "bg-slate-800 text-slate-200"}`}>
                        {row.severity || "-"}
                      </span>
                    </TableCell>
                    <TableCell className="max-w-[360px] truncate" title={row.action || ""} data-testid={`admin-log-main-list-action-${index}`}>{row.action || "-"}</TableCell>
                    <TableCell className="max-w-[320px] truncate" title={row.route || ""} data-testid={`admin-log-main-list-route-${index}`}>{row.route || "-"}</TableCell>
                    <TableCell data-testid={`admin-log-main-list-error-class-${index}`}>{row.error_class || "none"}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </section>

      <section className="rounded-2xl border border-rose-700 bg-rose-950/20 p-4" data-testid="admin-log-error-list-section">
        <h2 className="text-base font-semibold text-rose-200" data-testid="admin-log-error-list-title">Hata Logları (50)</h2>
        <div className="mt-3 space-y-2" data-testid="admin-log-error-list-wrap">
          {errorLogs.length === 0 ? (
            <p className="text-sm text-rose-100/80" data-testid="admin-log-error-list-empty">hata kaydı yok</p>
          ) : (
            errorLogs.map((row, index) => (
              <article key={row.id || `${row.created_at}-${index}`} className="rounded border border-rose-800/70 bg-slate-950/60 p-3" data-testid={`admin-log-error-list-item-${index}`}>
                <div className="flex flex-wrap items-center gap-2 text-xs text-rose-200" data-testid={`admin-log-error-list-item-meta-${index}`}>
                  <span data-testid={`admin-log-error-list-item-time-${index}`}>{formatDateTime(row.created_at)}</span>
                  <span data-testid={`admin-log-error-list-item-role-${index}`}>rol={row.actor_role || "-"}</span>
                  <span data-testid={`admin-log-error-list-item-class-${index}`}>class={row.error_class || "trade_blocker"}</span>
                  <span data-testid={`admin-log-error-list-item-status-${index}`}>status={row.status_code ?? "-"}</span>
                </div>
                <p className="mt-2 text-sm text-rose-100" data-testid={`admin-log-error-list-item-action-${index}`}>{row.action || "-"}</p>
                <p className="mt-1 text-xs text-rose-100/90" data-testid={`admin-log-error-list-item-message-${index}`}>
                  {row.error_message || "hata mesajı bulunamadı"}
                </p>
              </article>
            ))
          )}
        </div>
      </section>
    </section>
  );
};
