import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

export const AdminExecutionReadinessPage = () => {
  const [readiness, setReadiness] = useState(null);
  const [gate, setGate] = useState(null);
  const [overrideReason, setOverrideReason] = useState("manual override for testing");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [{ data: readinessData }, { data: gateData }] = await Promise.all([
        apiClient.get("/admin/execution-readiness"),
        apiClient.get("/phase4/admin/release-gate"),
      ]);
      setReadiness(readinessData);
      setGate(gateData);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Execution readiness verisi alınamadı");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const enableOverride = async () => {
    try {
      await apiClient.post("/admin/execution-override", {
        reason_code: "execution_guard_manual_override",
        reason_note: overrideReason,
        ttl_minutes: 30,
        deploy_context: { source: "admin_execution_readiness_page" },
      });
      toast.success("Execution override açıldı");
      load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Override açılamadı");
    }
  };

  return (
    <section className="space-y-4" data-testid="admin-execution-readiness-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="admin-execution-readiness-header">
        <h1 className="text-4xl font-black uppercase tracking-tight text-orange-300" data-testid="admin-execution-readiness-title">Execution Readiness</h1>
        <p className="mt-2 text-sm text-slate-300" data-testid="admin-execution-readiness-description">
          Guard status, override ve trade güvenlik kararları.
        </p>
      </header>

      <div className="grid gap-3 md:grid-cols-3" data-testid="admin-execution-readiness-grid">
        <div className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-execution-readiness-connection-card">
          <p className="text-xs text-slate-400">connection</p>
          <p className="text-lg font-semibold text-white" data-testid="admin-execution-readiness-connection-value">{readiness?.exchange_connection || "-"}</p>
        </div>
        <div className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-execution-readiness-permissions-card">
          <p className="text-xs text-slate-400">permissions</p>
          <p className="text-lg font-semibold text-white" data-testid="admin-execution-readiness-permissions-value">{readiness?.permissions || "-"}</p>
        </div>
        <div className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-execution-readiness-latency-card">
          <p className="text-xs text-slate-400">latency</p>
          <p className="text-lg font-semibold text-white" data-testid="admin-execution-readiness-latency-value">{readiness?.latency_ms ?? "-"} ms</p>
        </div>
        <div className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-execution-readiness-order-test-card">
          <p className="text-xs text-slate-400">order_test</p>
          <p className="text-lg font-semibold text-white" data-testid="admin-execution-readiness-order-test-value">{readiness?.order_test || "-"}</p>
        </div>
        <div className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-execution-readiness-mode-card">
          <p className="text-xs text-slate-400">mode</p>
          <p className="text-lg font-semibold text-white" data-testid="admin-execution-readiness-mode-value">{readiness?.mode || "-"}</p>
          {readiness?.mode === "MOCKED" && <p className="mt-1 text-xs text-orange-300" data-testid="admin-execution-readiness-mocked-badge">MOCKED MODE</p>}
        </div>
        <div className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-execution-readiness-final-status-card">
          <p className="text-xs text-slate-400">final_status</p>
          <p className={`text-lg font-semibold ${readiness?.final_status === "READY" ? "text-emerald-300" : "text-red-300"}`} data-testid="admin-execution-readiness-final-status-value">
            {readiness?.final_status || "-"}
          </p>
        </div>
      </div>

      {readiness?.final_status === "BLOCKED" && (
        <div className="rounded border border-red-700 bg-red-950/30 p-3 text-sm text-red-200" data-testid="admin-execution-readiness-blocked-action-message">
          BLOCKED: Trade execution kapalı. Connection/permission reason_codes çözülmeli veya admin override uygulanmalı.
        </div>
      )}

      <div className="rounded border border-orange-700 bg-slate-900 p-3" data-testid="admin-execution-readiness-override-panel">
        <p className="text-xs uppercase text-orange-300" data-testid="admin-execution-readiness-override-title">Admin Override</p>
        <Input
          value={overrideReason}
          onChange={(event) => setOverrideReason(event.target.value)}
          className="mt-2 bg-slate-950"
          data-testid="admin-execution-readiness-override-reason-input"
        />
        <div className="mt-3 flex gap-2">
          <Button onClick={enableOverride} data-testid="admin-execution-readiness-override-enable-button">Override Enable</Button>
          <Button variant="outline" onClick={load} disabled={loading} data-testid="admin-execution-readiness-refresh-button">Refresh</Button>
        </div>
        <p className="mt-2 text-xs text-slate-300" data-testid="admin-execution-readiness-override-active-flag">
          override_active: {String(Boolean(readiness?.override_active || gate?.override_active))}
        </p>
      </div>
    </section>
  );
};
