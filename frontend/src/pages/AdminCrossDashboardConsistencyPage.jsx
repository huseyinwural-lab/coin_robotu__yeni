import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

const endpointCallOptions = {
  "/admin/execution-queue": { params: { status_filter: "all", limit: 200 } },
  "/strategy-domain/admin/risk-orchestrator/analytics": { params: { days: 7 } },
};

const isTypeMatch = (value, expectedType) => {
  if (expectedType === "array") {
    return Array.isArray(value);
  }
  if (expectedType === "object") {
    return typeof value === "object" && value !== null && !Array.isArray(value);
  }
  if (expectedType === "number") {
    return typeof value === "number" && Number.isFinite(value);
  }
  if (expectedType === "boolean") {
    return typeof value === "boolean";
  }
  if (expectedType === "string") {
    return typeof value === "string";
  }
  return true;
};

const validateContract = (payload, contract) => {
  const requiredFields = contract?.required_fields || {};
  const missingFields = [];
  const nullFields = [];
  const fieldMismatches = [];

  Object.entries(requiredFields).forEach(([field, expectedType]) => {
    if (!(field in (payload || {}))) {
      missingFields.push(field);
      return;
    }
    const value = payload[field];
    if (value === null || value === undefined) {
      nullFields.push(field);
      return;
    }
    if (!isTypeMatch(value, expectedType)) {
      fieldMismatches.push(`${field} (expected ${expectedType})`);
    }
  });

  const hasContractError = missingFields.length > 0 || nullFields.length > 0 || fieldMismatches.length > 0;
  return {
    missingFields,
    nullFields,
    fieldMismatches,
    hasContractError,
  };
};

const deriveEmptyState = (payload, emptyRule) => {
  if (!emptyRule || emptyRule.type === "never") {
    return false;
  }
  if (emptyRule.type === "list") {
    return Array.isArray(payload) && payload.length === 0;
  }
  if (emptyRule.type === "field_array") {
    const fieldValue = payload?.[emptyRule.field];
    return Array.isArray(fieldValue) && fieldValue.length === 0;
  }
  return false;
};

export const AdminCrossDashboardConsistencyPage = () => {
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [lastUpdatedAt, setLastUpdatedAt] = useState("");
  const [panelRows, setPanelRows] = useState([]);
  const [contractRows, setContractRows] = useState([]);
  const [consistency, setConsistency] = useState(null);
  const [panelFilter, setPanelFilter] = useState("all");
  const [contractFilter, setContractFilter] = useState("all");
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);

  const load = useCallback(async () => {
    setIsLoading(true);
    setLoadError("");
    try {
      const [inventoryRes, consistencyRes] = await Promise.all([
        apiClient.get("/admin/closure/panels"),
        apiClient.get("/admin/closure/consistency"),
      ]);

      const inventory = inventoryRes.data?.panels || [];
      const contracts = inventoryRes.data?.contracts || {};

      const contractChecksByPanel = [];

      for (const panel of inventory) {
        const endpointChecks = await Promise.all(
          (panel.api_endpoints || []).map(async (endpoint) => {
            const contract = contracts[endpoint] || null;
            const requestOptions = endpointCallOptions[endpoint] || {};
            const startedAt = Date.now();
            try {
              const response = await apiClient.get(endpoint, {
                timeout: 15000,
                ...requestOptions,
              });
              const payload = response?.data;
              const contractValidation = validateContract(payload, contract);
              const isEmpty = deriveEmptyState(payload, contract?.empty_rule);
              const runtimeState = contractValidation.hasContractError ? "broken" : isEmpty ? "empty" : "success";
              return {
                panelKey: panel.panel_key,
                panelTitle: panel.title,
                endpoint,
                runtimeState,
                durationMs: Date.now() - startedAt,
                statusCode: response.status,
                timeout: false,
                ...contractValidation,
              };
            } catch (error) {
              const isTimeout = error?.code === "ECONNABORTED";
              return {
                panelKey: panel.panel_key,
                panelTitle: panel.title,
                endpoint,
                runtimeState: "broken",
                durationMs: Date.now() - startedAt,
                statusCode: error?.response?.status || null,
                timeout: isTimeout,
                missingFields: [],
                nullFields: [],
                fieldMismatches: [],
                hasContractError: true,
                errorMessage: error?.response?.data?.detail || error?.message || "endpoint_error",
              };
            }
          })
        );

        const hasBroken = endpointChecks.some((item) => item.runtimeState === "broken");
        const hasSuccess = endpointChecks.some((item) => item.runtimeState === "success");
        const runtimeState = hasBroken ? "broken" : hasSuccess ? "success" : "empty";
        const contractPass = endpointChecks.every((item) => !item.hasContractError);
        const overallPass = Boolean(panel.state_contract_pass) && contractPass && runtimeState !== "broken";

        contractChecksByPanel.push({
          panel: {
            ...panel,
            runtime_state: runtimeState,
            contract_pass: contractPass,
            overall_pass: overallPass,
            endpoint_count: endpointChecks.length,
          },
          endpointChecks,
        });
      }

      setPanelRows(contractChecksByPanel.map((item) => item.panel));
      setContractRows(contractChecksByPanel.flatMap((item) => item.endpointChecks));
      setConsistency(consistencyRes.data || null);
      setLastUpdatedAt(new Date().toISOString());
    } catch (error) {
      const message = error?.response?.data?.detail || "Kapanış matrisi yüklenemedi";
      setLoadError(message);
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!autoRefreshEnabled) {
      return undefined;
    }
    const timer = setInterval(() => {
      load();
    }, 60000);
    return () => clearInterval(timer);
  }, [autoRefreshEnabled, load]);

  const filteredPanels = useMemo(() => {
    if (panelFilter === "all") {
      return panelRows;
    }
    if (panelFilter === "pass") {
      return panelRows.filter((item) => item.overall_pass);
    }
    if (panelFilter === "fail") {
      return panelRows.filter((item) => !item.overall_pass);
    }
    if (panelFilter === "broken") {
      return panelRows.filter((item) => item.runtime_state === "broken");
    }
    return panelRows;
  }, [panelFilter, panelRows]);

  const filteredContracts = useMemo(() => {
    if (contractFilter === "all") {
      return contractRows;
    }
    if (contractFilter === "issues") {
      return contractRows.filter((item) => item.hasContractError);
    }
    if (contractFilter === "timeout") {
      return contractRows.filter((item) => item.timeout);
    }
    if (contractFilter === "ok") {
      return contractRows.filter((item) => !item.hasContractError);
    }
    return contractRows;
  }, [contractFilter, contractRows]);

  const summary = useMemo(() => {
    const totalPanels = panelRows.length;
    const passPanels = panelRows.filter((item) => item.overall_pass).length;
    const brokenPanels = panelRows.filter((item) => item.runtime_state === "broken").length;
    const contractIssues = contractRows.filter((item) => item.hasContractError).length;
    return {
      totalPanels,
      passPanels,
      brokenPanels,
      contractIssues,
      metricMismatches: Number(consistency?.mismatch_count || 0),
    };
  }, [consistency, contractRows, panelRows]);

  if (isLoading) {
    return <LoadingSkeleton rows={10} testId="admin-cross-dashboard-consistency-loading-skeleton" />;
  }

  if (loadError && panelRows.length === 0) {
    return (
      <section className="space-y-4" data-testid="admin-cross-dashboard-consistency-broken-state">
        <div className="border border-rose-500/40 bg-rose-900/20 p-4" data-testid="admin-cross-dashboard-consistency-broken-alert">
          <p className="text-sm font-semibold text-rose-200" data-testid="admin-cross-dashboard-consistency-broken-title">Kapanış verisi alınamadı</p>
          <p className="mt-1 text-sm text-rose-100" data-testid="admin-cross-dashboard-consistency-broken-message">{loadError}</p>
          <Button className="mt-3" onClick={load} data-testid="admin-cross-dashboard-consistency-broken-retry-button">Tekrar Dene</Button>
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-4" data-testid="admin-cross-dashboard-consistency-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="admin-cross-dashboard-consistency-header">
        <div className="flex flex-wrap items-start justify-between gap-3" data-testid="admin-cross-dashboard-consistency-header-row">
          <div data-testid="admin-cross-dashboard-consistency-header-left">
            <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="admin-cross-dashboard-consistency-title">Cross-Dashboard Consistency</h2>
            <p className="mt-2 text-sm text-slate-400" data-testid="admin-cross-dashboard-consistency-description">Faz-1B kapanış matrisi, veri kontratı doğrulaması ve metrik tutarlılık kontrol yüzeyi.</p>
            <p className="mt-1 text-xs text-slate-500" data-testid="admin-cross-dashboard-consistency-last-updated">Son güncelleme: {lastUpdatedAt ? new Date(lastUpdatedAt).toLocaleString() : "-"}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2" data-testid="admin-cross-dashboard-consistency-actions">
            <label className="flex items-center gap-2 text-xs text-slate-400" data-testid="admin-cross-dashboard-consistency-auto-refresh-toggle-wrapper">
              <input
                type="checkbox"
                checked={autoRefreshEnabled}
                onChange={(event) => setAutoRefreshEnabled(event.target.checked)}
                data-testid="admin-cross-dashboard-consistency-auto-refresh-toggle"
              />
              auto refresh (60s)
            </label>
            <Button onClick={load} data-testid="admin-cross-dashboard-consistency-refresh-button">Yenile</Button>
          </div>
        </div>
      </header>

      {loadError && (
        <div className="border border-amber-500/40 bg-amber-950/20 p-3 text-sm text-amber-200" data-testid="admin-cross-dashboard-consistency-warning-alert">
          Son yenileme sırasında hata oluştu: {loadError}
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-5" data-testid="admin-cross-dashboard-consistency-summary-grid">
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-cross-dashboard-consistency-summary-total-panels-card">
          <p className="text-xs text-slate-500">Panel</p>
          <p className="text-xl font-semibold" data-testid="admin-cross-dashboard-consistency-summary-total-panels-value">{summary.totalPanels}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-cross-dashboard-consistency-summary-pass-panels-card">
          <p className="text-xs text-slate-500">Kapanan Panel</p>
          <p className="text-xl font-semibold text-emerald-400" data-testid="admin-cross-dashboard-consistency-summary-pass-panels-value">{summary.passPanels}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-cross-dashboard-consistency-summary-broken-panels-card">
          <p className="text-xs text-slate-500">Broken Panel</p>
          <p className="text-xl font-semibold text-rose-400" data-testid="admin-cross-dashboard-consistency-summary-broken-panels-value">{summary.brokenPanels}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-cross-dashboard-consistency-summary-contract-issues-card">
          <p className="text-xs text-slate-500">Contract Issue</p>
          <p className="text-xl font-semibold text-amber-400" data-testid="admin-cross-dashboard-consistency-summary-contract-issues-value">{summary.contractIssues}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-cross-dashboard-consistency-summary-metric-mismatch-card">
          <p className="text-xs text-slate-500">Metric Mismatch</p>
          <p className="text-xl font-semibold" data-testid="admin-cross-dashboard-consistency-summary-metric-mismatch-value">{summary.metricMismatches}</p>
        </article>
      </div>

      <section className="border border-slate-800 bg-slate-900 p-4" data-testid="admin-cross-dashboard-consistency-matrix-section">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-cross-dashboard-consistency-matrix-header-row">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-cross-dashboard-consistency-matrix-title">Ekran Bazlı Kapanış Matrisi</p>
          <div className="flex items-center gap-2" data-testid="admin-cross-dashboard-consistency-matrix-controls">
            <select value={panelFilter} onChange={(event) => setPanelFilter(event.target.value)} className="h-9 rounded border border-slate-700 bg-slate-950 px-2 text-sm" data-testid="admin-cross-dashboard-consistency-matrix-filter-select">
              <option value="all" data-testid="admin-cross-dashboard-consistency-matrix-filter-all">All</option>
              <option value="pass" data-testid="admin-cross-dashboard-consistency-matrix-filter-pass">Pass</option>
              <option value="fail" data-testid="admin-cross-dashboard-consistency-matrix-filter-fail">Fail</option>
              <option value="broken" data-testid="admin-cross-dashboard-consistency-matrix-filter-broken">Broken</option>
            </select>
            <Button variant="outline" onClick={() => setPanelFilter("all")} data-testid="admin-cross-dashboard-consistency-matrix-filter-reset-button">Reset</Button>
          </div>
        </div>

        <div className="mt-3 overflow-x-auto" data-testid="admin-cross-dashboard-consistency-matrix-table-wrapper">
          <table className="min-w-full text-sm" data-testid="admin-cross-dashboard-consistency-matrix-table">
            <thead className="bg-slate-800 text-left" data-testid="admin-cross-dashboard-consistency-matrix-table-head">
              <tr>
                <th className="px-3 py-2">Panel</th>
                <th className="px-3 py-2">Route</th>
                <th className="px-3 py-2">Runtime</th>
                <th className="px-3 py-2">loading</th>
                <th className="px-3 py-2">empty</th>
                <th className="px-3 py-2">broken</th>
                <th className="px-3 py-2">success</th>
                <th className="px-3 py-2">Contract</th>
                <th className="px-3 py-2">Overall</th>
              </tr>
            </thead>
            <tbody data-testid="admin-cross-dashboard-consistency-matrix-table-body">
              {filteredPanels.map((item) => (
                <tr key={item.panel_key} className="border-t border-slate-800" data-testid={`admin-cross-dashboard-consistency-matrix-row-${item.panel_key}`}>
                  <td className="px-3 py-2" data-testid={`admin-cross-dashboard-consistency-matrix-title-${item.panel_key}`}>{item.title}</td>
                  <td className="px-3 py-2" data-testid={`admin-cross-dashboard-consistency-matrix-route-${item.panel_key}`}>{item.route}</td>
                  <td className="px-3 py-2" data-testid={`admin-cross-dashboard-consistency-matrix-runtime-${item.panel_key}`}>{item.runtime_state}</td>
                  <td className="px-3 py-2" data-testid={`admin-cross-dashboard-consistency-matrix-loading-${item.panel_key}`}>{String(item.state_coverage?.loading)}</td>
                  <td className="px-3 py-2" data-testid={`admin-cross-dashboard-consistency-matrix-empty-${item.panel_key}`}>{String(item.state_coverage?.empty)}</td>
                  <td className="px-3 py-2" data-testid={`admin-cross-dashboard-consistency-matrix-broken-${item.panel_key}`}>{String(item.state_coverage?.broken)}</td>
                  <td className="px-3 py-2" data-testid={`admin-cross-dashboard-consistency-matrix-success-${item.panel_key}`}>{String(item.state_coverage?.success)}</td>
                  <td className="px-3 py-2" data-testid={`admin-cross-dashboard-consistency-matrix-contract-${item.panel_key}`}>{item.contract_pass ? "PASS" : "FAIL"}</td>
                  <td className="px-3 py-2" data-testid={`admin-cross-dashboard-consistency-matrix-overall-${item.panel_key}`}>{item.overall_pass ? "PASS" : "FAIL"}</td>
                </tr>
              ))}
              {filteredPanels.length === 0 && (
                <tr className="border-t border-slate-800" data-testid="admin-cross-dashboard-consistency-matrix-empty-row">
                  <td colSpan={9} className="px-3 py-4 text-center text-sm text-slate-400" data-testid="admin-cross-dashboard-consistency-matrix-empty-text">Filtreye uygun panel bulunamadı.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="border border-slate-800 bg-slate-900 p-4" data-testid="admin-cross-dashboard-consistency-contract-section">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-cross-dashboard-consistency-contract-header-row">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-cross-dashboard-consistency-contract-title">Veri-Kontratı Uyumluluk Tablosu</p>
          <div className="flex items-center gap-2" data-testid="admin-cross-dashboard-consistency-contract-controls">
            <select value={contractFilter} onChange={(event) => setContractFilter(event.target.value)} className="h-9 rounded border border-slate-700 bg-slate-950 px-2 text-sm" data-testid="admin-cross-dashboard-consistency-contract-filter-select">
              <option value="all" data-testid="admin-cross-dashboard-consistency-contract-filter-all">All</option>
              <option value="issues" data-testid="admin-cross-dashboard-consistency-contract-filter-issues">Issues</option>
              <option value="timeout" data-testid="admin-cross-dashboard-consistency-contract-filter-timeout">Timeout</option>
              <option value="ok" data-testid="admin-cross-dashboard-consistency-contract-filter-ok">OK</option>
            </select>
            <Button variant="outline" onClick={() => setContractFilter("all")} data-testid="admin-cross-dashboard-consistency-contract-filter-reset-button">Reset</Button>
          </div>
        </div>

        <div className="mt-3 overflow-x-auto" data-testid="admin-cross-dashboard-consistency-contract-table-wrapper">
          <table className="min-w-full text-sm" data-testid="admin-cross-dashboard-consistency-contract-table">
            <thead className="bg-slate-800 text-left" data-testid="admin-cross-dashboard-consistency-contract-table-head">
              <tr>
                <th className="px-3 py-2">Panel</th>
                <th className="px-3 py-2">Endpoint</th>
                <th className="px-3 py-2">State</th>
                <th className="px-3 py-2">Missing</th>
                <th className="px-3 py-2">Null</th>
                <th className="px-3 py-2">Mismatch</th>
                <th className="px-3 py-2">Duration</th>
              </tr>
            </thead>
            <tbody data-testid="admin-cross-dashboard-consistency-contract-table-body">
              {filteredContracts.map((item, index) => (
                <tr key={`${item.panelKey}-${item.endpoint}-${index}`} className="border-t border-slate-800" data-testid={`admin-cross-dashboard-consistency-contract-row-${index}`}>
                  <td className="px-3 py-2" data-testid={`admin-cross-dashboard-consistency-contract-panel-${index}`}>{item.panelTitle}</td>
                  <td className="px-3 py-2" data-testid={`admin-cross-dashboard-consistency-contract-endpoint-${index}`}>{item.endpoint}</td>
                  <td className="px-3 py-2" data-testid={`admin-cross-dashboard-consistency-contract-state-${index}`}>{item.runtimeState}</td>
                  <td className="px-3 py-2" data-testid={`admin-cross-dashboard-consistency-contract-missing-${index}`}>{item.missingFields?.join(", ") || "-"}</td>
                  <td className="px-3 py-2" data-testid={`admin-cross-dashboard-consistency-contract-null-${index}`}>{item.nullFields?.join(", ") || "-"}</td>
                  <td className="px-3 py-2" data-testid={`admin-cross-dashboard-consistency-contract-mismatch-${index}`}>{item.fieldMismatches?.join(", ") || "-"}</td>
                  <td className="px-3 py-2" data-testid={`admin-cross-dashboard-consistency-contract-duration-${index}`}>{item.durationMs}ms</td>
                </tr>
              ))}
              {filteredContracts.length === 0 && (
                <tr className="border-t border-slate-800" data-testid="admin-cross-dashboard-consistency-contract-empty-row">
                  <td colSpan={7} className="px-3 py-4 text-center text-sm text-slate-400" data-testid="admin-cross-dashboard-consistency-contract-empty-text">Filtreye uygun endpoint kaydı bulunamadı.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="border border-slate-800 bg-slate-900 p-4" data-testid="admin-cross-dashboard-consistency-metric-section">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-cross-dashboard-consistency-metric-title">Cross-Screen Metric Consistency</p>

        {Number(consistency?.mismatch_count || 0) > 0 ? (
          <div className="mt-3 border border-rose-500/40 bg-rose-900/20 p-3 text-sm text-rose-200" data-testid="admin-cross-dashboard-consistency-metric-mismatch-alert">
            Tolerans dışı metrik sapması tespit edildi: {consistency?.mismatch_count}
          </div>
        ) : (
          <div className="mt-3 border border-emerald-500/40 bg-emerald-900/20 p-3 text-sm text-emerald-200" data-testid="admin-cross-dashboard-consistency-metric-pass-alert">
            Tüm çapraz metrik kontrolleri tolerans içinde.
          </div>
        )}

        <div className="mt-3 grid gap-3 md:grid-cols-3 lg:grid-cols-6" data-testid="admin-cross-dashboard-consistency-canonical-grid">
          <article className="border border-slate-800 bg-slate-950 p-3" data-testid="admin-cross-dashboard-consistency-canonical-active-positions-card">
            <p className="text-xs text-slate-500">Active Positions</p>
            <p className="text-xl font-semibold" data-testid="admin-cross-dashboard-consistency-canonical-active-positions-value">{consistency?.canonical_metrics?.active_positions ?? 0}</p>
          </article>
          <article className="border border-slate-800 bg-slate-950 p-3" data-testid="admin-cross-dashboard-consistency-canonical-queued-card">
            <p className="text-xs text-slate-500">Queued</p>
            <p className="text-xl font-semibold" data-testid="admin-cross-dashboard-consistency-canonical-queued-value">{consistency?.canonical_metrics?.queued_executions ?? 0}</p>
          </article>
          <article className="border border-slate-800 bg-slate-950 p-3" data-testid="admin-cross-dashboard-consistency-canonical-pending-card">
            <p className="text-xs text-slate-500">Pending</p>
            <p className="text-xl font-semibold" data-testid="admin-cross-dashboard-consistency-canonical-pending-value">{consistency?.canonical_metrics?.pending_executions ?? 0}</p>
          </article>
          <article className="border border-slate-800 bg-slate-950 p-3" data-testid="admin-cross-dashboard-consistency-canonical-exposure-card">
            <p className="text-xs text-slate-500">Exposure 7d</p>
            <p className="text-xl font-semibold" data-testid="admin-cross-dashboard-consistency-canonical-exposure-value">{consistency?.canonical_metrics?.total_exposure_7d ?? 0}</p>
          </article>
          <article className="border border-slate-800 bg-slate-950 p-3" data-testid="admin-cross-dashboard-consistency-canonical-alerts-card">
            <p className="text-xs text-slate-500">Alerts 24h</p>
            <p className="text-xl font-semibold" data-testid="admin-cross-dashboard-consistency-canonical-alerts-value">{consistency?.canonical_metrics?.risk_alerts_24h ?? 0}</p>
          </article>
          <article className="border border-slate-800 bg-slate-950 p-3" data-testid="admin-cross-dashboard-consistency-canonical-risk-score-card">
            <p className="text-xs text-slate-500">Avg Risk 24h</p>
            <p className="text-xl font-semibold" data-testid="admin-cross-dashboard-consistency-canonical-risk-score-value">{consistency?.canonical_metrics?.avg_risk_score_24h ?? 0}</p>
          </article>
        </div>

        <div className="mt-3 overflow-x-auto" data-testid="admin-cross-dashboard-consistency-metric-table-wrapper">
          <table className="min-w-full text-sm" data-testid="admin-cross-dashboard-consistency-metric-table">
            <thead className="bg-slate-800 text-left" data-testid="admin-cross-dashboard-consistency-metric-table-head">
              <tr>
                <th className="px-3 py-2">Metric</th>
                <th className="px-3 py-2">Canonical</th>
                <th className="px-3 py-2">Panel</th>
                <th className="px-3 py-2">Delta</th>
                <th className="px-3 py-2">Tolerance</th>
                <th className="px-3 py-2">Result</th>
              </tr>
            </thead>
            <tbody data-testid="admin-cross-dashboard-consistency-metric-table-body">
              {(consistency?.checks || []).map((item) => (
                <tr key={item.metric_name} className="border-t border-slate-800" data-testid={`admin-cross-dashboard-consistency-metric-row-${item.metric_name}`}>
                  <td className="px-3 py-2" data-testid={`admin-cross-dashboard-consistency-metric-name-${item.metric_name}`}>{item.metric_name}</td>
                  <td className="px-3 py-2" data-testid={`admin-cross-dashboard-consistency-metric-canonical-${item.metric_name}`}>{item.canonical_value}</td>
                  <td className="px-3 py-2" data-testid={`admin-cross-dashboard-consistency-metric-panel-${item.metric_name}`}>{item.panel_value}</td>
                  <td className="px-3 py-2" data-testid={`admin-cross-dashboard-consistency-metric-delta-${item.metric_name}`}>{item.delta}</td>
                  <td className="px-3 py-2" data-testid={`admin-cross-dashboard-consistency-metric-tolerance-${item.metric_name}`}>{item.tolerance}</td>
                  <td className="px-3 py-2" data-testid={`admin-cross-dashboard-consistency-metric-result-${item.metric_name}`}>{item.in_tolerance ? "PASS" : "FAIL"}</td>
                </tr>
              ))}
              {(consistency?.checks || []).length === 0 && (
                <tr className="border-t border-slate-800" data-testid="admin-cross-dashboard-consistency-metric-empty-row">
                  <td colSpan={6} className="px-3 py-4 text-center text-sm text-slate-400" data-testid="admin-cross-dashboard-consistency-metric-empty-text">Metric consistency kaydı bulunamadı.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
};
