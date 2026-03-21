import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { ProdConfigRemediationModal } from "@/components/ProdConfigRemediationModal";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const AdminExecutionReadinessPage = () => {
  const [readiness, setReadiness] = useState(null);
  const [gate, setGate] = useState(null);
  const [remediationState, setRemediationState] = useState(null);
  const [isRemediationOpen, setIsRemediationOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [{ data: readinessData }, { data: gateData }, { data: remediationData }] = await Promise.all([
        apiClient.get("/admin/execution-readiness"),
        apiClient.get("/phase4/admin/release-gate"),
        apiClient.get("/admin/system/remediate-config"),
      ]);
      setReadiness(readinessData);
      setGate(gateData);
      setRemediationState(remediationData);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Execution readiness verisi alınamadı");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const isBlocked = remediationState?.release_gate_status === "BLOCKED" || gate?.status === "BLOCKED";

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

      {isBlocked && (
        <div className="rounded border border-red-700 bg-red-950/30 p-3 text-sm text-red-200" data-testid="admin-execution-readiness-blocked-action-message">
          BLOCKED: Deploy ve live enable kapalı. "Blokajı Çöz" ile production config girip yeniden doğrula.
        </div>
      )}

      <div className="rounded border border-red-700/70 bg-slate-900 p-3" data-testid="admin-execution-readiness-remediation-panel">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-execution-readiness-remediation-header">
          <p className="text-xs uppercase text-red-300" data-testid="admin-execution-readiness-remediation-title">Release Gate Remediation</p>
          <div className="flex gap-2" data-testid="admin-execution-readiness-remediation-actions">
            <Button variant="outline" onClick={load} disabled={loading} data-testid="admin-execution-readiness-refresh-button">Yenile</Button>
            <Button
              className="bg-red-600 text-white hover:bg-red-700"
              onClick={() => setIsRemediationOpen(true)}
              data-testid="admin-execution-readiness-open-remediation-button"
            >
              Blokajı Çöz
            </Button>
          </div>
        </div>

        <div className="mt-3 grid gap-2 text-xs text-slate-200 md:grid-cols-2" data-testid="admin-execution-readiness-remediation-status-grid">
          <p data-testid="admin-execution-readiness-remediation-release-gate-status">release_gate_status: {remediationState?.release_gate_status || "-"}</p>
          <p data-testid="admin-execution-readiness-remediation-preflight-status">preflight_status: {remediationState?.preflight_status || "-"}</p>
          <p data-testid="admin-execution-readiness-remediation-secret-status">secret_readiness_status: {remediationState?.secret_readiness_status || "-"}</p>
          <p data-testid="admin-execution-readiness-remediation-final-decision">final_release_gate_decision: {remediationState?.final_release_gate_decision || "-"}</p>
        </div>

        <div className="mt-2 space-y-1" data-testid="admin-execution-readiness-remediation-reasons-list">
          {(remediationState?.release_gate_reason_codes || []).map((item, index) => (
            <p key={`${item}-${index}`} className="font-mono text-xs text-red-200" data-testid={`admin-execution-readiness-remediation-reason-${index}`}>{item}</p>
          ))}
          {(remediationState?.release_gate_reason_codes || []).length === 0 && (
            <p className="text-xs text-slate-400" data-testid="admin-execution-readiness-remediation-reasons-empty">Aktif reason_code yok.</p>
          )}
        </div>

        <div className="mt-2 space-y-1" data-testid="admin-execution-readiness-remediation-checks-list">
          {(remediationState?.checks || []).map((item, index) => (
            <p key={`${item.check_name}-${index}`} className="text-xs text-slate-300" data-testid={`admin-execution-readiness-remediation-check-${index}`}>
              {item.check_name}: {item.status}
            </p>
          ))}
          {(remediationState?.checks || []).length === 0 && (
            <p className="text-xs text-slate-400" data-testid="admin-execution-readiness-remediation-checks-empty">Check sonucu henüz yok.</p>
          )}
        </div>
      </div>

      <ProdConfigRemediationModal
        open={isRemediationOpen}
        onOpenChange={setIsRemediationOpen}
        remediationState={remediationState}
        onSaved={(nextState) => {
          setRemediationState(nextState);
          load();
        }}
        testIdPrefix="admin-execution-readiness"
      />

      {remediationState?.release_gate_status === "PASS" && (
        <div className="rounded border border-emerald-700 bg-emerald-950/20 p-3 text-sm text-emerald-200" data-testid="admin-execution-readiness-pass-message">
          PASS: Production preflight doğrulandı. Deploy enable yalnızca backend PASS döndüğü için açık.
        </div>
      )}
    </section>
  );
};
