import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { apiClient } from "@/lib/api";

const WEIGHT_TOLERANCE = 0.0001;
const DOUBLE_CONFIRM_PRIMARY = "CONFIRM";
const DOUBLE_CONFIRM_SECONDARY = "STATE CHANGE";

const toNumber = (value) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : NaN;
};

const formatMoney = (value) => {
  const amount = Number.isFinite(Number(value)) ? Number(value) : 0;
  return amount.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

const createDraftFromRow = (item) => ({
  capital_weight: String(item.capital_weight ?? "0"),
  max_capital: String(item.max_capital ?? "0"),
  current_capital: String(item.current_capital ?? "0"),
  state: item.state || "ACTIVE",
  confirm_primary: "",
  confirm_secondary: "",
});

const validateDraft = (draft) => {
  const errors = [];
  const weight = toNumber(draft.capital_weight);
  const maxCapital = toNumber(draft.max_capital);
  const currentCapital = toNumber(draft.current_capital);

  if (!Number.isFinite(weight)) errors.push("Weight sayısal olmalı");
  if (!Number.isFinite(maxCapital)) errors.push("Max capital sayısal olmalı");
  if (!Number.isFinite(currentCapital)) errors.push("Current capital sayısal olmalı");

  if (Number.isFinite(weight) && (weight < 0 || weight > 1)) errors.push("Weight 0 ile 1 arasında olmalı");
  if (Number.isFinite(maxCapital) && maxCapital < 0) errors.push("Max capital negatif olamaz");
  if (Number.isFinite(currentCapital) && currentCapital < 0) errors.push("Current capital negatif olamaz");
  if (Number.isFinite(maxCapital) && Number.isFinite(currentCapital) && currentCapital > maxCapital) {
    errors.push("Current capital max capital değerini aşamaz");
  }

  return {
    errors,
    hasError: errors.length > 0,
  };
};

const stateReasonBadgeClass = (code) => {
  const normalized = String(code || "").toUpperCase();
  if (normalized === "AUTO_DISABLED_BY_DRIFT") return "border border-rose-500/60 bg-rose-950/50 text-rose-200";
  if (normalized === "AUTO_THROTTLED_BY_DRIFT") return "border border-amber-500/60 bg-amber-950/50 text-amber-200";
  return "border border-slate-700 bg-slate-950 text-slate-300";
};

const stateReasonInlineText = (row) => {
  if (row?.is_drift_override) return "Manual change overridden by drift rule";
  if (row?.state_reason_code === "AUTO_DISABLED_BY_DRIFT") return "Drift rule: auto disabled";
  if (row?.state_reason_code === "AUTO_THROTTLED_BY_DRIFT") return "Drift rule: auto throttled";
  return "Manual / stable";
};

export const AdminStrategyAllocationPage = () => {
  const [rows, setRows] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [backendSummary, setBackendSummary] = useState(null);
  const [stateHistory, setStateHistory] = useState([]);
  const [selectedStrategyIds, setSelectedStrategyIds] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [isNormalizing, setIsNormalizing] = useState(false);
  const [isBulkSubmitting, setIsBulkSubmitting] = useState(false);
  const [bulkAutoNormalize, setBulkAutoNormalize] = useState(false);
  const [createPayload, setCreatePayload] = useState({
    strategy_id: "",
    capital_weight: "0",
    max_capital: "0",
    current_capital: "0",
    state: "ACTIVE",
  });
  const [isCreating, setIsCreating] = useState(false);
  const [globalActionError, setGlobalActionError] = useState("");
  const [driftOverrideNotice, setDriftOverrideNotice] = useState("");
  const [lastUpdatedAt, setLastUpdatedAt] = useState("");

  const load = async () => {
    setIsLoading(true);
    setLoadError("");
    setGlobalActionError("");
    try {
      const [rowsResp, summaryResp, historyResp] = await Promise.all([
        apiClient.get("/admin/strategy-allocation"),
        apiClient.get("/admin/strategy-allocation/summary"),
        apiClient.get("/admin/strategy-allocation/state-history", { params: { limit: 40 } }),
      ]);

      const rowsData = rowsResp?.data || [];
      setRows(rowsData);
      setBackendSummary(summaryResp?.data || null);
      setStateHistory(historyResp?.data?.rows || []);
      const initialDrafts = {};
      rowsData.forEach((item) => {
        initialDrafts[item.strategy_id] = {
          ...createDraftFromRow(item),
        };
      });
      setDrafts(initialDrafts);
      setSelectedStrategyIds((prev) => prev.filter((id) => rowsData.some((row) => row.strategy_id === id)));
      setLastUpdatedAt(new Date().toISOString());
    } catch (error) {
      const message = error?.response?.data?.detail || "Strategy allocation verisi yüklenemedi";
      setLoadError(message);
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const stateStats = useMemo(() => {
    const total = rows.length;
    const throttled = rows.filter((item) => item.state === "THROTTLED").length;
    const disabled = rows.filter((item) => item.state === "DISABLED").length;
    return { total, throttled, disabled };
  }, [rows]);

  const draftRows = useMemo(
    () => rows.map((row) => ({ strategy_id: row.strategy_id, ...(drafts[row.strategy_id] || createDraftFromRow(row)) })),
    [drafts, rows],
  );

  const capitalSnapshot = useMemo(() => {
    const totalWeight = draftRows.reduce((acc, row) => acc + (toNumber(row.capital_weight) || 0), 0);
    const totalCapital = draftRows.reduce((acc, row) => acc + (toNumber(row.max_capital) || 0), 0);
    const usedCapital = draftRows.reduce((acc, row) => acc + (toNumber(row.current_capital) || 0), 0);
    const overAllocatedRows = draftRows.filter((row) => {
      const maxCapital = toNumber(row.max_capital);
      const currentCapital = toNumber(row.current_capital);
      return Number.isFinite(maxCapital) && Number.isFinite(currentCapital) && currentCapital > maxCapital;
    });

    return {
      totalWeight: Number(totalWeight.toFixed(6)),
      weightDelta: Number((totalWeight - 1).toFixed(6)),
      totalCapital,
      usedCapital,
      availableCapital: Math.max(totalCapital - usedCapital, 0),
      overAllocatedRows,
    };
  }, [draftRows]);

  const weightIsBalanced = Math.abs(capitalSnapshot.weightDelta) <= WEIGHT_TOLERANCE;
  const hasOverAllocation = capitalSnapshot.overAllocatedRows.length > 0;

  const updateDraft = (strategyId, key, value) => {
    setGlobalActionError("");
    setDrafts((prev) => ({
      ...prev,
      [strategyId]: {
        ...(prev[strategyId] || {}),
        [key]: value,
      },
    }));
  };

  const isStateChanged = (strategyId) => {
    const current = rows.find((item) => item.strategy_id === strategyId);
    const draft = drafts[strategyId] || {};
    return current && String(current.state || "") !== String(draft.state || "");
  };

  const getRowErrors = (strategyId) => {
    const draft = drafts[strategyId] || {};
    const baseValidation = validateDraft(draft);
    const errors = [...baseValidation.errors];

    if (!weightIsBalanced) errors.push("Toplam weight = 1 olmalı");
    if (hasOverAllocation) errors.push("Capital limit aşılıyor");
    if (isStateChanged(strategyId)) {
      if ((draft.confirm_primary || "").toUpperCase().trim() !== DOUBLE_CONFIRM_PRIMARY) {
        errors.push("confirm_primary = CONFIRM olmalı");
      }
      if ((draft.confirm_secondary || "").toUpperCase().trim() !== DOUBLE_CONFIRM_SECONDARY) {
        errors.push("confirm_secondary = STATE CHANGE olmalı");
      }
    }

    return errors;
  };

  const saveStrategy = async (strategyId) => {
    const draft = drafts[strategyId] || {};
    const rowErrors = getRowErrors(strategyId);
    if (rowErrors.length > 0) {
      const firstError = rowErrors[0] || "Form geçersiz";
      toast.error(firstError);
      setGlobalActionError(firstError);
      return;
    }

    try {
      const { data } = await apiClient.put(`/admin/strategy-allocation/${encodeURIComponent(strategyId)}`, {
        capital_weight: Number(draft.capital_weight),
        max_capital: Number(draft.max_capital),
        current_capital: Number(draft.current_capital),
        state: draft.state,
        confirm_primary: draft.confirm_primary || undefined,
        confirm_secondary: draft.confirm_secondary || undefined,
      });
      toast.success(`Allocation güncellendi: ${strategyId}`);
      if (data?.is_drift_override) {
        const notice = `Manual change overridden by drift rule (${data?.state_reason_code || "AUTO"})`;
        setDriftOverrideNotice(notice);
        toast.warning(notice);
      } else {
        setDriftOverrideNotice("");
      }
      await load();
    } catch (error) {
      const message = error?.response?.data?.detail || "Allocation güncellenemedi";
      setGlobalActionError(message);
      toast.error(message);
    }
  };

  const normalizeWeights = async () => {
    setIsNormalizing(true);
    setGlobalActionError("");
    try {
      const { data } = await apiClient.post("/admin/strategy-allocation/normalize");
      toast.success(data?.message || "Weight normalize tamamlandı");
      await load();
    } catch (error) {
      const message = error?.response?.data?.detail || "Normalize işlemi başarısız";
      setGlobalActionError(message);
      toast.error(message);
    } finally {
      setIsNormalizing(false);
    }
  };

  const createStrategy = async () => {
    setIsCreating(true);
    setGlobalActionError("");
    const strategyId = String(createPayload.strategy_id || "").trim();
    if (!strategyId) {
      setIsCreating(false);
      toast.error("strategy_id zorunlu");
      return;
    }

    const validation = validateDraft(createPayload);
    if (validation.hasError) {
      setIsCreating(false);
      toast.error(validation.errors[0] || "Create form geçersiz");
      return;
    }

    try {
      await apiClient.post("/admin/strategy-allocation", {
        strategy_id: strategyId,
        capital_weight: Number(createPayload.capital_weight),
        max_capital: Number(createPayload.max_capital),
        current_capital: Number(createPayload.current_capital),
        state: createPayload.state,
      });
      toast.success(`Strategy eklendi: ${strategyId}`);
      setCreatePayload({ strategy_id: "", capital_weight: "0", max_capital: "0", current_capital: "0", state: "ACTIVE" });
      await load();
    } catch (error) {
      const message = error?.response?.data?.detail || "Strategy eklenemedi";
      setGlobalActionError(message);
      toast.error(message);
    } finally {
      setIsCreating(false);
    }
  };

  const deleteStrategy = async (strategyId) => {
    const ok = window.confirm(`${strategyId} silinsin mi? (auto-normalize açık)`);
    if (!ok) return;

    setGlobalActionError("");
    try {
      await apiClient.delete(`/admin/strategy-allocation/${encodeURIComponent(strategyId)}`, {
        params: { auto_normalize: true },
      });
      toast.success(`Strategy silindi: ${strategyId}`);
      await load();
    } catch (error) {
      const message = error?.response?.data?.detail || "Strategy silinemedi";
      setGlobalActionError(message);
      toast.error(message);
    }
  };

  const toggleThrottle = async (strategyId) => {
    const first = window.confirm(`${strategyId} için throttle toggle başlatılsın mı?`);
    if (!first) return;
    const second = window.confirm("İkinci onay: state değişimi uygulanacak. Devam?");
    if (!second) return;

    try {
      await apiClient.post(`/admin/strategy-allocation/${encodeURIComponent(strategyId)}/throttle-toggle`, {
        confirm_primary: DOUBLE_CONFIRM_PRIMARY,
        confirm_secondary: DOUBLE_CONFIRM_SECONDARY,
      });
      toast.success(`Throttle toggle tamamlandı: ${strategyId}`);
      await load();
    } catch (error) {
      const message = error?.response?.data?.detail || "Throttle toggle başarısız";
      setGlobalActionError(message);
      toast.error(message);
    }
  };

  const toggleSelection = (strategyId) => {
    setSelectedStrategyIds((prev) => {
      if (prev.includes(strategyId)) return prev.filter((id) => id !== strategyId);
      return [...prev, strategyId];
    });
  };

  const applyDrawdownSuggestionsToForm = () => {
    const candidates = backendSummary?.drawdown_candidates || [];
    if (candidates.length === 0) {
      toast.info("Drawdown reduce önerisi bulunmuyor");
      return;
    }

    setDrafts((prev) => {
      const next = { ...prev };
      candidates.forEach((candidate) => {
        const strategyId = candidate.strategy_id;
        if (!next[strategyId]) return;
        next[strategyId] = {
          ...next[strategyId],
          current_capital: String(candidate.suggested_reduced_capital),
        };
      });
      return next;
    });
    toast.success("Drawdown reduce önerileri forma uygulandı (otomatik kaydetme yok)");
  };

  const submitBulkUpdate = async () => {
    if (selectedStrategyIds.length === 0) {
      toast.error("Bulk update için en az bir strategy seçin");
      return;
    }

    const invalid = selectedStrategyIds.find((strategyId) => getRowErrors(strategyId).length > 0);
    if (invalid) {
      const firstError = getRowErrors(invalid)[0] || "Seçili satırlarda validasyon hatası var";
      setGlobalActionError(firstError);
      toast.error(firstError);
      return;
    }

    setIsBulkSubmitting(true);
    setGlobalActionError("");
    try {
      const { data } = await apiClient.post("/admin/strategy-allocation/bulk-update", {
        updates: selectedStrategyIds.map((strategyId) => {
          const draft = drafts[strategyId] || {};
          return {
            strategy_id: strategyId,
            capital_weight: Number(draft.capital_weight),
            max_capital: Number(draft.max_capital),
            current_capital: Number(draft.current_capital),
            state: draft.state,
            confirm_primary: draft.confirm_primary || undefined,
            confirm_secondary: draft.confirm_secondary || undefined,
          };
        }),
        auto_normalize: bulkAutoNormalize,
      });
      toast.success(`Bulk update tamamlandı (${selectedStrategyIds.length} strategy)`);
      const enforcedRows = data?.enforced_reduce_rows || [];
      if (enforcedRows.length > 0) {
        toast.warning(`Critical drawdown auto-reduce uygulandı (${enforcedRows.length} strategy)`);
      }
      await load();
    } catch (error) {
      const message = error?.response?.data?.detail || "Bulk update başarısız";
      setGlobalActionError(message);
      toast.error(message);
    } finally {
      setIsBulkSubmitting(false);
    }
  };

  if (isLoading) {
    return <LoadingSkeleton rows={8} testId="admin-strategy-allocation-loading-skeleton" />;
  }

  if (loadError && rows.length === 0) {
    return (
      <section className="space-y-4" data-testid="admin-strategy-allocation-broken-state">
        <div className="border border-rose-500/40 bg-rose-900/20 p-4" data-testid="admin-strategy-allocation-broken-alert">
          <p className="text-sm font-semibold text-rose-200" data-testid="admin-strategy-allocation-broken-title">Strategy allocation verisi alınamadı</p>
          <p className="mt-1 text-sm text-rose-100" data-testid="admin-strategy-allocation-broken-message">{loadError}</p>
          <Button className="mt-3" onClick={load} data-testid="admin-strategy-allocation-broken-retry-button">Tekrar Dene</Button>
        </div>
      </section>
    );
  }

  return (
    <section className="grid grid-cols-12 gap-4" data-testid="admin-strategy-allocation-page">
      <header className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-allocation-header">
        <div className="flex flex-wrap items-start justify-between gap-3" data-testid="admin-strategy-allocation-header-row">
          <div data-testid="admin-strategy-allocation-header-left">
            <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="admin-strategy-allocation-title">Strategy Allocation Dashboard</h2>
            <p className="mt-2 text-sm text-slate-400" data-testid="admin-strategy-allocation-description">Capital usage, confidence, throttle/disability kontrol paneli.</p>
            <p className="mt-1 text-xs text-slate-500" data-testid="admin-strategy-allocation-last-updated">Son güncelleme: {lastUpdatedAt ? new Date(lastUpdatedAt).toLocaleString() : "-"}</p>
          </div>
          <Button onClick={load} data-testid="admin-strategy-allocation-refresh-button">Yenile</Button>
        </div>
      </header>

      {loadError && (
        <div className="col-span-12 border border-amber-500/40 bg-amber-950/20 p-3 text-sm text-amber-200" data-testid="admin-strategy-allocation-warning-alert">
          Son yenileme sırasında hata oluştu: {loadError}
        </div>
      )}

      {globalActionError && (
        <div className="col-span-12 border border-rose-500/40 bg-rose-950/20 p-3 text-sm text-rose-200" data-testid="admin-strategy-allocation-action-error-alert">
          İşlem hatası: {globalActionError}
        </div>
      )}

      {driftOverrideNotice && (
        <div className="col-span-12 border border-amber-500/40 bg-amber-950/20 p-3 text-sm text-amber-100" data-testid="admin-strategy-allocation-drift-override-banner">
          {driftOverrideNotice}
        </div>
      )}

      <div className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-allocation-safety-layer-panel">
        <div className="flex flex-wrap items-center gap-2" data-testid="admin-strategy-allocation-safety-layer-actions">
          <Button onClick={normalizeWeights} disabled={isNormalizing} data-testid="admin-strategy-allocation-normalize-button">
            {isNormalizing ? "Normalizing..." : "Auto Normalize (Weight=1)"}
          </Button>
          <Button onClick={submitBulkUpdate} disabled={isBulkSubmitting || selectedStrategyIds.length === 0} data-testid="admin-strategy-allocation-bulk-save-button">
            {isBulkSubmitting ? "Bulk kaydediliyor..." : `Seçilenleri Toplu Kaydet (${selectedStrategyIds.length})`}
          </Button>
          <label className="inline-flex items-center gap-2 text-xs text-slate-300" data-testid="admin-strategy-allocation-bulk-auto-normalize-label">
            <input
              type="checkbox"
              checked={bulkAutoNormalize}
              onChange={(event) => setBulkAutoNormalize(event.target.checked)}
              data-testid="admin-strategy-allocation-bulk-auto-normalize-checkbox"
            />
            Bulk sonrası auto-normalize
          </label>
        </div>

        <div className="mt-3 grid gap-3 md:grid-cols-4" data-testid="admin-strategy-allocation-capital-governance-grid">
          <article className="border border-slate-800 bg-slate-950 p-3" data-testid="admin-strategy-allocation-governance-total-weight-card">
            <p className="text-xs text-slate-400">Toplam Weight</p>
            <p className={`text-xl font-semibold ${weightIsBalanced ? "text-emerald-400" : "text-rose-400"}`} data-testid="admin-strategy-allocation-governance-total-weight-value">
              {capitalSnapshot.totalWeight.toFixed(6)}
            </p>
          </article>
          <article className="border border-slate-800 bg-slate-950 p-3" data-testid="admin-strategy-allocation-governance-total-capital-card">
            <p className="text-xs text-slate-400">Total Capital</p>
            <p className="text-xl font-semibold" data-testid="admin-strategy-allocation-governance-total-capital-value">{formatMoney(capitalSnapshot.totalCapital)}</p>
          </article>
          <article className="border border-slate-800 bg-slate-950 p-3" data-testid="admin-strategy-allocation-governance-used-capital-card">
            <p className="text-xs text-slate-400">Used Capital</p>
            <p className="text-xl font-semibold text-amber-400" data-testid="admin-strategy-allocation-governance-used-capital-value">{formatMoney(capitalSnapshot.usedCapital)}</p>
          </article>
          <article className="border border-slate-800 bg-slate-950 p-3" data-testid="admin-strategy-allocation-governance-available-capital-card">
            <p className="text-xs text-slate-400">Available Capital</p>
            <p className="text-xl font-semibold text-cyan-300" data-testid="admin-strategy-allocation-governance-available-capital-value">{formatMoney(capitalSnapshot.availableCapital)}</p>
          </article>
        </div>

        {!weightIsBalanced && (
          <div className="mt-3 border border-rose-500/40 bg-rose-950/20 p-3 text-sm text-rose-200" data-testid="admin-strategy-allocation-weight-warning-alert">
            Toplam weight 1 olmalı. Delta: {capitalSnapshot.weightDelta.toFixed(6)}
          </div>
        )}
        {hasOverAllocation && (
          <div className="mt-3 border border-rose-500/40 bg-rose-950/20 p-3 text-sm text-rose-200" data-testid="admin-strategy-allocation-over-allocation-warning-alert">
            Over-allocation tespit edildi: {capitalSnapshot.overAllocatedRows.map((row) => row.strategy_id).join(", ")}
          </div>
        )}

        {backendSummary && (
          <div className="mt-2 space-y-2" data-testid="admin-strategy-allocation-risk-binding-panel">
            <p className="text-xs text-slate-400" data-testid="admin-strategy-allocation-backend-summary-text">
              Backend snapshot → weight={backendSummary.total_weight} · used={backendSummary.used_capital} · available={backendSummary.available_capital} · over_allocated={backendSummary.over_allocated_count}
            </p>
            <p className="text-xs text-slate-300" data-testid="admin-strategy-allocation-risk-exposure-line">
              Exposure={backendSummary.total_exposure_ratio_pct}% · warning threshold={backendSummary.exposure_warning_threshold_pct}%
            </p>
            {backendSummary.exposure_warning_state === "WARNING" && (
              <div className="border border-amber-500/40 bg-amber-950/20 p-2 text-xs text-amber-100" data-testid="admin-strategy-allocation-risk-exposure-warning">
                Exposure warning: used/total capital oranı {backendSummary.exposure_warning_threshold_pct}% üstünde.
              </div>
            )}

            <div className="rounded border border-slate-800 bg-slate-950 p-2" data-testid="admin-strategy-allocation-drawdown-candidates-panel">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs text-slate-300" data-testid="admin-strategy-allocation-drawdown-candidates-title">
                  Drawdown candidates (threshold {backendSummary.drawdown_threshold_pct}% / enforce {backendSummary.drawdown_enforce_threshold_pct}%)
                </p>
                <Button size="sm" variant="outline" onClick={applyDrawdownSuggestionsToForm} data-testid="admin-strategy-allocation-apply-drawdown-suggestion-button">
                  Önerilen Reduce’u Forma Uygula
                </Button>
              </div>
              <div className="mt-2 space-y-1" data-testid="admin-strategy-allocation-drawdown-candidates-list">
                {(backendSummary.drawdown_candidates || []).length === 0 && (
                  <p className="text-xs text-slate-500" data-testid="admin-strategy-allocation-drawdown-candidates-empty">No data yet</p>
                )}
                {(backendSummary.drawdown_candidates || []).map((candidate, index) => (
                  <p key={`${candidate.strategy_id}-${index}`} className="text-xs text-slate-300" data-testid={`admin-strategy-allocation-drawdown-candidate-${index}`}>
                    {candidate.strategy_id} · drawdown={candidate.drawdown_pct}% · suggested={candidate.suggested_reduced_capital}
                    {candidate.enforced_required ? " · CRITICAL" : " · suggestion"}
                  </p>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-allocation-create-panel">
        <h3 className="text-base font-semibold" data-testid="admin-strategy-allocation-create-title">Strategy Ekle</h3>
        <div className="mt-2 grid gap-2 md:grid-cols-6" data-testid="admin-strategy-allocation-create-grid">
          <Input
            placeholder="strategy_id"
            value={createPayload.strategy_id}
            onChange={(event) => setCreatePayload((prev) => ({ ...prev, strategy_id: event.target.value }))}
            data-testid="admin-strategy-allocation-create-strategy-id-input"
          />
          <Input
            type="number"
            min="0"
            max="1"
            step="0.0001"
            placeholder="weight"
            value={createPayload.capital_weight}
            onChange={(event) => setCreatePayload((prev) => ({ ...prev, capital_weight: event.target.value }))}
            data-testid="admin-strategy-allocation-create-weight-input"
          />
          <Input
            type="number"
            min="0"
            step="0.01"
            placeholder="max capital"
            value={createPayload.max_capital}
            onChange={(event) => setCreatePayload((prev) => ({ ...prev, max_capital: event.target.value }))}
            data-testid="admin-strategy-allocation-create-max-capital-input"
          />
          <Input
            type="number"
            min="0"
            step="0.01"
            placeholder="current capital"
            value={createPayload.current_capital}
            onChange={(event) => setCreatePayload((prev) => ({ ...prev, current_capital: event.target.value }))}
            data-testid="admin-strategy-allocation-create-current-capital-input"
          />
          <select
            className="w-full border border-slate-700 bg-slate-950 px-2 py-1"
            value={createPayload.state}
            onChange={(event) => setCreatePayload((prev) => ({ ...prev, state: event.target.value }))}
            data-testid="admin-strategy-allocation-create-state-select"
          >
            <option value="ACTIVE">ACTIVE</option>
            <option value="THROTTLED">THROTTLED</option>
            <option value="DISABLED">DISABLED</option>
          </select>
          <Button onClick={createStrategy} disabled={isCreating} data-testid="admin-strategy-allocation-create-button">
            {isCreating ? "Ekleniyor..." : "Strategy Ekle"}
          </Button>
        </div>
      </div>

      <div className="col-span-12 grid gap-3 md:grid-cols-3" data-testid="admin-strategy-allocation-summary-grid">
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-strategy-allocation-summary-total">
          <p className="text-xs text-slate-500">Toplam Strategy</p>
          <p className="text-xl font-semibold">{stateStats.total}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-strategy-allocation-summary-throttled">
          <p className="text-xs text-slate-500">THROTTLED</p>
          <p className="text-xl font-semibold text-amber-400">{stateStats.throttled}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-strategy-allocation-summary-disabled">
          <p className="text-xs text-slate-500">DISABLED</p>
          <p className="text-xl font-semibold text-rose-400">{stateStats.disabled}</p>
        </article>
      </div>

      <div className="col-span-12 overflow-x-auto border border-slate-800 bg-slate-900" data-testid="admin-strategy-allocation-table-wrapper">
        <table className="min-w-full text-sm" data-testid="admin-strategy-allocation-table">
          <thead className="bg-slate-800 text-left" data-testid="admin-strategy-allocation-table-head">
            <tr>
              <th className="px-3 py-2">Select</th>
              <th className="px-3 py-2">Strategy</th>
              <th className="px-3 py-2">Weight</th>
              <th className="px-3 py-2">Max Capital</th>
              <th className="px-3 py-2">Current Capital</th>
              <th className="px-3 py-2">State</th>
              <th className="px-3 py-2">Exposure %</th>
              <th className="px-3 py-2">Drawdown %</th>
              <th className="px-3 py-2">Confidence</th>
              <th className="px-3 py-2">Performance</th>
              <th className="px-3 py-2">Signal Decay</th>
              <th className="px-3 py-2">Execution Quality</th>
              <th className="px-3 py-2">Action</th>
            </tr>
          </thead>
          <tbody data-testid="admin-strategy-allocation-table-body">
            {rows.map((item) => {
              const draft = drafts[item.strategy_id] || {};
              const rowErrors = getRowErrors(item.strategy_id);
              const stateChanged = isStateChanged(item.strategy_id);
              return (
                <tr key={item.strategy_id} className="border-t border-slate-800" data-testid={`admin-strategy-allocation-row-${item.strategy_id}`}>
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={selectedStrategyIds.includes(item.strategy_id)}
                      onChange={() => toggleSelection(item.strategy_id)}
                      data-testid={`admin-strategy-allocation-row-select-checkbox-${item.strategy_id}`}
                    />
                  </td>
                  <td className="px-3 py-2" data-testid={`admin-strategy-allocation-strategy-${item.strategy_id}`}>{item.strategy_id}</td>
                  <td className="px-3 py-2"><Input value={draft.capital_weight ?? ""} type="number" min="0" max="1" step="0.0001" onChange={(event) => updateDraft(item.strategy_id, "capital_weight", event.target.value)} data-testid={`admin-strategy-allocation-weight-input-${item.strategy_id}`} /></td>
                  <td className="px-3 py-2"><Input value={draft.max_capital ?? ""} type="number" min="0" step="0.01" onChange={(event) => updateDraft(item.strategy_id, "max_capital", event.target.value)} data-testid={`admin-strategy-allocation-max-capital-input-${item.strategy_id}`} /></td>
                  <td className="px-3 py-2"><Input value={draft.current_capital ?? ""} type="number" min="0" step="0.01" onChange={(event) => updateDraft(item.strategy_id, "current_capital", event.target.value)} data-testid={`admin-strategy-allocation-current-capital-input-${item.strategy_id}`} /></td>
                  <td className="px-3 py-2">
                    <select className="w-full border border-slate-700 bg-slate-950 px-2 py-1" value={draft.state || "ACTIVE"} onChange={(event) => updateDraft(item.strategy_id, "state", event.target.value)} data-testid={`admin-strategy-allocation-state-select-${item.strategy_id}`}>
                      <option value="ACTIVE">ACTIVE</option>
                      <option value="THROTTLED">THROTTLED</option>
                      <option value="DISABLED">DISABLED</option>
                    </select>
                    <div className="mt-1 flex flex-wrap items-center gap-1" data-testid={`admin-strategy-allocation-state-reason-row-${item.strategy_id}`}>
                      <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${stateReasonBadgeClass(item.state_reason_code)}`} data-testid={`admin-strategy-allocation-state-reason-badge-${item.strategy_id}`}>
                        {item.state_reason_code || "MANUAL_STATE"}
                      </span>
                      <span className="text-[10px] text-slate-300" data-testid={`admin-strategy-allocation-state-reason-inline-${item.strategy_id}`}>
                        {stateReasonInlineText(item)}
                      </span>
                      <TooltipProvider delayDuration={0}>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="cursor-help text-[10px] text-cyan-300" data-testid={`admin-strategy-allocation-state-reason-tooltip-trigger-${item.strategy_id}`}>why?</span>
                          </TooltipTrigger>
                          <TooltipContent side="top" className="max-w-[320px]" data-testid={`admin-strategy-allocation-state-reason-tooltip-${item.strategy_id}`}>
                            <p>{item.state_reason_detail || "No reason"}</p>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </div>
                  </td>
                  <td className="px-3 py-2" data-testid={`admin-strategy-allocation-exposure-ratio-${item.strategy_id}`}>{item.exposure_ratio_pct}</td>
                  <td className="px-3 py-2" data-testid={`admin-strategy-allocation-drawdown-pct-${item.strategy_id}`}>{item.drawdown_pct}</td>
                  <td className="px-3 py-2" data-testid={`admin-strategy-allocation-confidence-${item.strategy_id}`}>{item.confidence_score}</td>
                  <td className="px-3 py-2" data-testid={`admin-strategy-allocation-performance-${item.strategy_id}`}>{item.performance_score}</td>
                  <td className="px-3 py-2" data-testid={`admin-strategy-allocation-signal-decay-${item.strategy_id}`}>{item.signal_decay}</td>
                  <td className="px-3 py-2" data-testid={`admin-strategy-allocation-execution-quality-${item.strategy_id}`}>{item.execution_quality_score}</td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-2" data-testid={`admin-strategy-allocation-actions-${item.strategy_id}`}>
                      <Button variant="outline" onClick={() => saveStrategy(item.strategy_id)} disabled={rowErrors.length > 0} data-testid={`admin-strategy-allocation-save-button-${item.strategy_id}`}>Kaydet</Button>
                      <Button variant="outline" onClick={() => toggleThrottle(item.strategy_id)} data-testid={`admin-strategy-allocation-throttle-toggle-button-${item.strategy_id}`}>Throttle Toggle</Button>
                      <Button variant="outline" onClick={() => deleteStrategy(item.strategy_id)} data-testid={`admin-strategy-allocation-delete-button-${item.strategy_id}`}>Sil</Button>
                    </div>
                    {stateChanged && (
                      <div className="mt-2 grid gap-1" data-testid={`admin-strategy-allocation-double-confirm-panel-${item.strategy_id}`}>
                        <Input
                          placeholder="confirm_primary: CONFIRM"
                          value={draft.confirm_primary || ""}
                          onChange={(event) => updateDraft(item.strategy_id, "confirm_primary", event.target.value)}
                          data-testid={`admin-strategy-allocation-confirm-primary-input-${item.strategy_id}`}
                        />
                        <Input
                          placeholder="confirm_secondary: STATE CHANGE"
                          value={draft.confirm_secondary || ""}
                          onChange={(event) => updateDraft(item.strategy_id, "confirm_secondary", event.target.value)}
                          data-testid={`admin-strategy-allocation-confirm-secondary-input-${item.strategy_id}`}
                        />
                      </div>
                    )}
                    {rowErrors.length > 0 && (
                      <p className="mt-1 text-xs text-rose-300" data-testid={`admin-strategy-allocation-row-error-${item.strategy_id}`}>{rowErrors[0]}</p>
                    )}
                  </td>
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr className="border-t border-slate-800" data-testid="admin-strategy-allocation-empty-row">
                <td colSpan={13} className="px-3 py-4 text-center text-sm text-slate-400" data-testid="admin-strategy-allocation-empty-text">Strategy allocation kaydı bulunamadı.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-allocation-state-history-panel">
        <h3 className="text-base font-semibold" data-testid="admin-strategy-allocation-state-history-title">State History Log</h3>
        <div className="mt-2 space-y-1" data-testid="admin-strategy-allocation-state-history-list">
          {stateHistory.length === 0 && (
            <p className="text-sm text-slate-400" data-testid="admin-strategy-allocation-state-history-empty">No data yet</p>
          )}
          {stateHistory.map((item, index) => (
            <div key={`${item.trace_id}-${index}`} className="rounded border border-slate-800 bg-slate-950 p-2 text-xs" data-testid={`admin-strategy-allocation-state-history-item-${index}`}>
              <p data-testid={`admin-strategy-allocation-state-history-item-main-${index}`}>
                [{new Date(item.timestamp).toLocaleString()}] {item.strategy_id} · {item.action_type}
              </p>
              <p data-testid={`admin-strategy-allocation-state-history-item-transition-${index}`}>
                {item.previous_state || "-"} → {item.new_state || "-"} · admin={item.admin_id}
              </p>
              <p data-testid={`admin-strategy-allocation-state-history-item-reason-${index}`}>
                reason={item.reason_code || "-"} · detail={item.reason_detail || "-"}
              </p>
              <p data-testid={`admin-strategy-allocation-state-history-item-trace-${index}`}>trace={item.trace_id}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};
