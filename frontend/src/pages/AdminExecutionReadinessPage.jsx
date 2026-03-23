import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { apiClient } from "@/lib/api";

export const AdminExecutionReadinessPage = () => {
  const [gate, setGate] = useState(null);
  const [readiness, setReadiness] = useState(null);
  const [stateReasonCode, setStateReasonCode] = useState("MANUAL_RISK_ACCEPTANCE");
  const [stateReasonText, setStateReasonText] = useState("Pre-deploy kontroller tamamlandı.");
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [overrideReasonCode, setOverrideReasonCode] = useState("INCIDENT_MITIGATION");
  const [overrideReasonText, setOverrideReasonText] = useState("");
  const [overrideTtl, setOverrideTtl] = useState(15);
  const [modeModalOpen, setModeModalOpen] = useState(false);
  const [targetMode, setTargetMode] = useState("LIVE");
  const [modeReason, setModeReason] = useState("Canary doğrulandı, LIVE geçişi başlatılıyor.");
  const [confirmationPhrase, setConfirmationPhrase] = useState("SWITCH TO LIVE");
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  const expectedPhrase = useMemo(() => {
    if (targetMode === "PAPER") return "SWITCH TO PAPER";
    if (targetMode === "MOCK") return "SWITCH TO MOCK";
    return "SWITCH TO LIVE";
  }, [targetMode]);

  const deployBlocked = !gate?.deploy_allowed;

  const load = useCallback(async (refreshChecks = false) => {
    setLoading(true);
    try {
      const [{ data: gateData }, { data: readinessData }] = await Promise.all([
        apiClient.get(`/phase4/admin/production-gate?refresh_checks=${refreshChecks ? "true" : "false"}`),
        apiClient.get("/admin/execution-readiness"),
      ]);
      setGate(gateData);
      setReadiness(readinessData);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Production Gate verisi alınamadı");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(true);
  }, [load]);

  const runAction = useCallback(
    async (runner, successMessage) => {
      setActionLoading(true);
      try {
        const data = await runner();
        if (data) {
          setGate(data);
        }
        toast.success(successMessage);
      } catch (error) {
        const detail = error?.response?.data?.detail;
        const fallback = typeof detail === "string" ? detail : detail?.error || "İşlem başarısız";
        toast.error(fallback);
      } finally {
        setActionLoading(false);
      }
    },
    []
  );

  const handleChecklistToggle = useCallback(
    async (itemKey, checked) => {
      await runAction(async () => {
        const { data } = await apiClient.patch(`/phase4/admin/production-gate/checklist/${itemKey}`, { checked });
        return data;
      }, "Checklist güncellendi");
    },
    [runAction]
  );

  const handleStateUpdate = useCallback(
    async (targetState) => {
      await runAction(async () => {
        const { data } = await apiClient.post("/phase4/admin/production-gate/state", {
          target_state: targetState,
          reason_code: stateReasonCode,
          reason_text: stateReasonText,
        });
        return data;
      }, `${targetState} işlemi tamamlandı`);
    },
    [runAction, stateReasonCode, stateReasonText]
  );

  const handleRerun = useCallback(
    async (checkKey = null) => {
      await runAction(async () => {
        const path = checkKey
          ? `/phase4/admin/production-gate/checks/${checkKey}/rerun`
          : "/phase4/admin/production-gate/checks/rerun";
        const { data } = await apiClient.post(path);
        return data;
      }, checkKey ? `${checkKey} yeniden çalıştırıldı` : "Tüm kontroller yeniden çalıştırıldı");
    },
    [runAction]
  );

  const handleCreateOverride = useCallback(async () => {
    await runAction(async () => {
      const { data } = await apiClient.post("/phase4/admin/production-gate/override", {
        reason_code: overrideReasonCode,
        reason_text: overrideReasonText,
        ttl_minutes: Number(overrideTtl),
      });
      setOverrideOpen(false);
      setOverrideReasonText("");
      return data;
    }, "GO_WITH_OVERRIDE aktif edildi");
  }, [overrideReasonCode, overrideReasonText, overrideTtl, runAction]);

  const handleRevokeOverride = useCallback(async () => {
    if (!gate?.active_override?.override_id) return;
    await runAction(async () => {
      const { data } = await apiClient.post(
        `/phase4/admin/production-gate/override/${gate.active_override.override_id}/revoke`
      );
      return data;
    }, "Override revoke edildi");
  }, [gate?.active_override?.override_id, runAction]);

  const handleModeTransition = useCallback(async () => {
    await runAction(async () => {
      const { data } = await apiClient.post("/phase4/admin/production-gate/mode-transition", {
        target_mode: targetMode,
        reason_text: modeReason,
        confirmation_phrase: confirmationPhrase,
      });
      setModeModalOpen(false);
      await load(false);
      return data?.gate;
    }, `${targetMode} geçiş isteği gönderildi`);
  }, [targetMode, modeReason, confirmationPhrase, runAction, load]);

  const handleExportJson = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/phase4/admin/production-gate/export/raw");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `production-gate-${Date.now()}.json`;
      link.click();
      URL.revokeObjectURL(url);
      toast.success("JSON export hazır");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "JSON export alınamadı");
    }
  }, []);

  return (
    <section className="space-y-6" data-testid="admin-production-gate-page">
      <header className="rounded-xl border border-slate-700 bg-gradient-to-r from-slate-900 via-slate-900 to-slate-800 p-5" data-testid="admin-production-gate-header">
        <div className="flex flex-wrap items-center justify-between gap-3" data-testid="admin-production-gate-header-row">
          <div data-testid="admin-production-gate-header-left">
            <h1 className="text-4xl font-black tracking-tight text-amber-300" data-testid="admin-production-gate-title">Production Gate Control Panel</h1>
            <p className="mt-2 text-sm text-slate-300" data-testid="admin-production-gate-subtitle">Deploy ve LIVE aktivasyonu sadece GO / GO_WITH_OVERRIDE ile açılır.</p>
          </div>
          <div className="flex flex-wrap gap-2" data-testid="admin-production-gate-header-actions">
            <Button variant="outline" onClick={() => load(true)} disabled={loading || actionLoading} data-testid="admin-production-gate-refresh-button">Yenile</Button>
            <Button variant="outline" onClick={handleExportJson} data-testid="admin-production-gate-export-json-button">JSON Export</Button>
            <Button onClick={() => handleRerun()} disabled={actionLoading} data-testid="admin-production-gate-rerun-all-button">Tüm Checkleri Rerun</Button>
          </div>
        </div>
      </header>

      <div className="grid gap-3 md:grid-cols-4" data-testid="admin-production-gate-status-grid">
        <div className="rounded-lg border border-slate-700 bg-slate-900 p-3" data-testid="admin-production-gate-configured-state-card">
          <p className="text-xs text-slate-400">Configured State</p>
          <p className="mt-1 text-lg font-semibold text-white" data-testid="admin-production-gate-configured-state-value">{gate?.configured_state || "-"}</p>
        </div>
        <div className="rounded-lg border border-slate-700 bg-slate-900 p-3" data-testid="admin-production-gate-effective-state-card">
          <p className="text-xs text-slate-400">Effective State</p>
          <p className={`mt-1 text-lg font-semibold ${gate?.effective_state === "GO" ? "text-emerald-300" : gate?.effective_state === "GO_WITH_OVERRIDE" ? "text-amber-300" : "text-red-300"}`} data-testid="admin-production-gate-effective-state-value">
            {gate?.effective_state || "-"}
          </p>
          {gate?.effective_state === "GO_WITH_OVERRIDE" && <p className="mt-1 text-xs text-amber-200" data-testid="admin-production-gate-override-risk-label">RISK OVERRIDE ACTIVE</p>}
        </div>
        <div className="rounded-lg border border-slate-700 bg-slate-900 p-3" data-testid="admin-production-gate-deploy-status-card">
          <p className="text-xs text-slate-400">Deploy / LIVE</p>
          <p className={`mt-1 text-lg font-semibold ${deployBlocked ? "text-red-300" : "text-emerald-300"}`} data-testid="admin-production-gate-deploy-status-value">{deployBlocked ? "BLOCKED" : "ALLOWED"}</p>
          <p className="mt-1 text-xs text-slate-400" data-testid="admin-production-gate-release-contract-value">release_gate_contract: {gate?.release_gate_contract || "UNKNOWN"}</p>
        </div>
        <div className="rounded-lg border border-slate-700 bg-slate-900 p-3" data-testid="admin-production-gate-readiness-card">
          <p className="text-xs text-slate-400">Execution Readiness</p>
          <p className="mt-1 text-lg font-semibold text-white" data-testid="admin-production-gate-readiness-mode">mode: {readiness?.mode || "-"}</p>
          <p className="mt-1 text-sm text-slate-300" data-testid="admin-production-gate-readiness-final">final_status: {readiness?.final_status || "-"}</p>
        </div>
      </div>

      {deployBlocked && (
        <div className="rounded-lg border border-red-700 bg-red-950/20 p-3 text-sm text-red-200" data-testid="admin-production-gate-blocked-banner">
          HARD BLOCK aktif: Deploy/LIVE aksiyonları 403 ile reddedilir. reason_codes: {(gate?.blocked_reason_codes || []).join(", ") || "state_no_go"}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2" data-testid="admin-production-gate-main-grid">
        <div className="space-y-4 rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="admin-production-gate-controls-panel">
          <h2 className="text-base font-semibold text-white" data-testid="admin-production-gate-controls-title">Gate Actions</h2>
          <div className="grid gap-2" data-testid="admin-production-gate-reason-form">
            <label className="text-xs text-slate-300" data-testid="admin-production-gate-reason-code-label">reason_code</label>
            <input className="rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white" value={stateReasonCode} onChange={(event) => setStateReasonCode(event.target.value)} data-testid="admin-production-gate-reason-code-input" />
            <label className="text-xs text-slate-300" data-testid="admin-production-gate-reason-text-label">reason_text</label>
            <textarea className="rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white" rows={3} value={stateReasonText} onChange={(event) => setStateReasonText(event.target.value)} data-testid="admin-production-gate-reason-text-input" />
          </div>
          <div className="flex flex-wrap gap-2" data-testid="admin-production-gate-state-buttons-row">
            <Button onClick={() => handleStateUpdate("GO")} disabled={actionLoading || !gate?.checklist_complete || !gate?.checks_all_pass || gate?.has_stale_or_running} data-testid="admin-production-gate-go-button">GO</Button>
            <Button variant="destructive" onClick={() => handleStateUpdate("NO_GO")} disabled={actionLoading} data-testid="admin-production-gate-no-go-button">NO_GO</Button>
            <Button variant="outline" onClick={() => setOverrideOpen(true)} disabled={actionLoading} data-testid="admin-production-gate-open-override-modal-button">GO_WITH_OVERRIDE</Button>
            <Button variant="outline" onClick={handleRevokeOverride} disabled={actionLoading || !gate?.active_override?.override_id} data-testid="admin-production-gate-revoke-override-button">Override Revoke</Button>
          </div>
          <div className="rounded border border-slate-700 bg-slate-950 p-3 text-xs text-slate-300" data-testid="admin-production-gate-override-summary-card">
            <p data-testid="admin-production-gate-override-id-value">override_id: {gate?.active_override?.override_id || "-"}</p>
            <p data-testid="admin-production-gate-override-reason-value">reason_code: {gate?.active_override?.reason_code || "-"}</p>
            <p data-testid="admin-production-gate-override-expiry-value">expires_at: {gate?.active_override?.expires_at || "-"}</p>
          </div>
        </div>

        <div className="space-y-4 rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="admin-production-gate-mode-panel">
          <h2 className="text-base font-semibold text-white" data-testid="admin-production-gate-mode-panel-title">Mode Transition Guard</h2>
          <p className="text-xs text-slate-300" data-testid="admin-production-gate-mode-panel-description">MOCK/PAPER → LIVE geçişi onay ifadesi + reason + gate state ile korunur.</p>
          <Button onClick={() => setModeModalOpen(true)} disabled={actionLoading} data-testid="admin-production-gate-open-mode-modal-button">Mode Change</Button>
        </div>
      </div>

      <div className="rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="admin-production-gate-checklist-panel">
        <h2 className="text-base font-semibold text-white" data-testid="admin-production-gate-checklist-title">Pre-deploy Checklist</h2>
        <div className="mt-3 grid gap-2" data-testid="admin-production-gate-checklist-items">
          {(gate?.checklist || []).map((item, index) => (
            <label key={item.item_key} className="flex items-center gap-2 rounded border border-slate-700 bg-slate-950 p-2" data-testid={`admin-production-gate-checklist-item-${item.item_key}`}>
              <input type="checkbox" checked={!!item.checked} onChange={(event) => handleChecklistToggle(item.item_key, event.target.checked)} data-testid={`admin-production-gate-checklist-item-toggle-${item.item_key}`} />
              <span className="text-sm text-white" data-testid={`admin-production-gate-checklist-item-title-${item.item_key}`}>{item.title}</span>
              <span className="ml-auto text-xs text-slate-400" data-testid={`admin-production-gate-checklist-item-status-${item.item_key}`}>{item.checked ? "DONE" : "PENDING"}</span>
              <span className="sr-only" data-testid={`admin-production-gate-checklist-item-index-${index}`}>{index}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="admin-production-gate-checks-panel">
        <h2 className="text-base font-semibold text-white" data-testid="admin-production-gate-checks-title">Automated Checks</h2>
        <div className="mt-3 space-y-2" data-testid="admin-production-gate-checks-list">
          {(gate?.checks || []).map((check) => (
            <div key={check.check_key} className="rounded border border-slate-700 bg-slate-950 p-3" data-testid={`admin-production-gate-check-row-${check.check_key}`}>
              <div className="flex flex-wrap items-center gap-2" data-testid={`admin-production-gate-check-row-header-${check.check_key}`}>
                <p className="text-sm font-semibold text-white" data-testid={`admin-production-gate-check-title-${check.check_key}`}>{check.title}</p>
                <p className={`text-xs ${check.status === "PASS" && !check.stale ? "text-emerald-300" : "text-red-300"}`} data-testid={`admin-production-gate-check-status-${check.check_key}`}>{check.status}{check.stale ? " (STALE)" : ""}</p>
                <Button variant="outline" className="ml-auto" onClick={() => handleRerun(check.check_key)} disabled={actionLoading} data-testid={`admin-production-gate-check-rerun-button-${check.check_key}`}>Rerun</Button>
              </div>
              <p className="mt-2 text-xs text-red-200" data-testid={`admin-production-gate-check-fail-reason-${check.check_key}`}>fail_reason: {check.fail_reason || "-"}</p>
              <p className="mt-1 text-xs text-amber-200" data-testid={`admin-production-gate-check-remediation-${check.check_key}`}>remediation: {check.remediation || "-"}</p>
            </div>
          ))}
          {(gate?.checks || []).length === 0 && <p className="text-xs text-slate-400" data-testid="admin-production-gate-checks-empty">Check listesi boş.</p>}
        </div>
      </div>

      <div className="rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="admin-production-gate-audit-panel">
        <h2 className="text-base font-semibold text-white" data-testid="admin-production-gate-audit-title">Audit History</h2>
        <div className="mt-3 space-y-2" data-testid="admin-production-gate-audit-list">
          {(gate?.audit_history || []).map((item, index) => (
            <div key={item.id} className="rounded border border-slate-700 bg-slate-950 p-2 text-xs text-slate-200" data-testid={`admin-production-gate-audit-row-${index}`}>
              <p data-testid={`admin-production-gate-audit-action-${index}`}>{item.action}</p>
              <p data-testid={`admin-production-gate-audit-actor-${index}`}>actor: {item.actor_role} / {item.actor_user_id || "system"}</p>
              <p data-testid={`admin-production-gate-audit-state-${index}`}>transition: {item?.details?.previous_state || "-"} → {item?.details?.next_state || "-"}</p>
              <p data-testid={`admin-production-gate-audit-reason-${index}`}>reason: {item?.details?.reason_code || "-"} / {item?.details?.reason_text || "-"}</p>
            </div>
          ))}
          {(gate?.audit_history || []).length === 0 && <p className="text-xs text-slate-400" data-testid="admin-production-gate-audit-empty">Audit kaydı bulunamadı.</p>}
        </div>
      </div>

      <Dialog open={overrideOpen} onOpenChange={setOverrideOpen}>
        <DialogContent data-testid="admin-production-gate-override-modal">
          <DialogHeader>
            <DialogTitle data-testid="admin-production-gate-override-modal-title">GO_WITH_OVERRIDE</DialogTitle>
            <DialogDescription data-testid="admin-production-gate-override-modal-description">Sadece super_admin, en fazla 30 dakika süreli override açabilir.</DialogDescription>
          </DialogHeader>
          <div className="space-y-2" data-testid="admin-production-gate-override-modal-form">
            <label className="text-xs text-slate-300" data-testid="admin-production-gate-override-reason-code-label">reason_code</label>
            <select className="w-full rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white" value={overrideReasonCode} onChange={(event) => setOverrideReasonCode(event.target.value)} data-testid="admin-production-gate-override-reason-code-select">
              <option value="INCIDENT_MITIGATION">INCIDENT_MITIGATION</option>
              <option value="THIRD_PARTY_DEGRADATION">THIRD_PARTY_DEGRADATION</option>
              <option value="HOTFIX_VALIDATED">HOTFIX_VALIDATED</option>
              <option value="MANUAL_RISK_ACCEPTANCE">MANUAL_RISK_ACCEPTANCE</option>
            </select>
            <label className="text-xs text-slate-300" data-testid="admin-production-gate-override-reason-text-label">reason_text</label>
            <textarea className="w-full rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white" rows={3} value={overrideReasonText} onChange={(event) => setOverrideReasonText(event.target.value)} data-testid="admin-production-gate-override-reason-text-input" />
            <label className="text-xs text-slate-300" data-testid="admin-production-gate-override-ttl-label">ttl_minutes</label>
            <input type="number" min={1} max={30} className="w-full rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white" value={overrideTtl} onChange={(event) => setOverrideTtl(event.target.value)} data-testid="admin-production-gate-override-ttl-input" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOverrideOpen(false)} data-testid="admin-production-gate-override-cancel-button">İptal</Button>
            <Button onClick={handleCreateOverride} disabled={actionLoading} data-testid="admin-production-gate-override-submit-button">Override Aç</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={modeModalOpen} onOpenChange={setModeModalOpen}>
        <DialogContent data-testid="admin-production-gate-mode-modal">
          <DialogHeader>
            <DialogTitle data-testid="admin-production-gate-mode-modal-title">Mode Change Confirmation</DialogTitle>
            <DialogDescription data-testid="admin-production-gate-mode-modal-description">MOCK → LIVE geçişinde Gate hard-block aktifse işlem reddedilir.</DialogDescription>
          </DialogHeader>
          <div className="space-y-2" data-testid="admin-production-gate-mode-modal-form">
            <label className="text-xs text-slate-300" data-testid="admin-production-gate-mode-target-label">target_mode</label>
            <select className="w-full rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white" value={targetMode} onChange={(event) => { setTargetMode(event.target.value); setConfirmationPhrase(event.target.value === "LIVE" ? "SWITCH TO LIVE" : event.target.value === "PAPER" ? "SWITCH TO PAPER" : "SWITCH TO MOCK"); }} data-testid="admin-production-gate-mode-target-select">
              <option value="LIVE">LIVE</option>
              <option value="PAPER">PAPER</option>
              <option value="MOCK">MOCK</option>
            </select>
            <label className="text-xs text-slate-300" data-testid="admin-production-gate-mode-reason-label">reason_text</label>
            <textarea className="w-full rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white" rows={3} value={modeReason} onChange={(event) => setModeReason(event.target.value)} data-testid="admin-production-gate-mode-reason-input" />
            <label className="text-xs text-slate-300" data-testid="admin-production-gate-mode-confirmation-label">confirmation_phrase ({expectedPhrase})</label>
            <input className="w-full rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white" value={confirmationPhrase} onChange={(event) => setConfirmationPhrase(event.target.value)} data-testid="admin-production-gate-mode-confirmation-input" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setModeModalOpen(false)} data-testid="admin-production-gate-mode-cancel-button">İptal</Button>
            <Button onClick={handleModeTransition} disabled={actionLoading} data-testid="admin-production-gate-mode-submit-button">Geçişi Uygula</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
};
