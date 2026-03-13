import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

const directionOptions = ["both", "long", "short"];
const regimeOptions = ["any", "trend", "breakout", "pullback", "reversal"];

export const AdminCanonicalStrategyRegistryPage = () => {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState("");

  const loadRegistry = async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/admin/canonical-strategies/registry", { params: { include_legacy: true } });
      setRows(Array.isArray(data) ? data : []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Canonical registry yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRegistry();
  }, []);

  const registryRows = useMemo(() => rows.filter((item) => !item.is_legacy_candidate), [rows]);
  const legacyRows = useMemo(() => rows.filter((item) => item.is_legacy_candidate), [rows]);

  const updateLocal = (strategyId, patch) => {
    setRows((prev) => prev.map((item) => (item.strategy_id === strategyId ? { ...item, ...patch } : item)));
  };

  const saveRow = async (row) => {
    setSavingId(row.strategy_id);
    try {
      const payload = {
        direction: row.direction,
        market_regime: row.market_regime,
        is_enabled: row.is_enabled,
        priority: Number(row.priority || 100),
        cooldown_policy: row.cooldown_policy,
        weight: Number(row.weight || 1),
        risk_profile: row.risk_profile,
        forced_disable_reason: row.forced_disable_reason || "",
      };
      const { data } = await apiClient.put(`/admin/canonical-strategies/registry/${row.strategy_id}`, payload);
      updateLocal(row.strategy_id, data);
      toast.success(`Kaydedildi: ${row.strategy_id}`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Kayıt güncellenemedi");
    } finally {
      setSavingId("");
    }
  };

  const refreshMetrics = async () => {
    try {
      const { data } = await apiClient.post("/admin/canonical-strategies/registry/refresh-metrics");
      setRows(Array.isArray(data) ? data : []);
      toast.success("Metrikler yenilendi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Metrik yenileme başarısız");
    }
  };

  return (
    <section className="space-y-4" data-testid="admin-canonical-strategy-registry-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="admin-canonical-registry-header">
        <h2 className="text-3xl font-black uppercase tracking-tight text-black" data-testid="admin-canonical-registry-title">Canonical Strategy Registry</h2>
        <p className="mt-2 text-sm text-black/80" data-testid="admin-canonical-registry-description">
          Production path sadece canonical registry üzerinden çalışır. Legacy stratejiler arşivde tutulur.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-2" data-testid="admin-canonical-registry-toolbar">
        <Button type="button" onClick={loadRegistry} data-testid="admin-canonical-registry-refresh-button">Yenile</Button>
        <Button type="button" variant="outline" onClick={refreshMetrics} data-testid="admin-canonical-registry-refresh-metrics-button">Metrik Yenile</Button>
        <p className="text-xs text-slate-300" data-testid="admin-canonical-registry-count-text">
          active={registryRows.length} legacy={legacyRows.length}
        </p>
      </div>

      {loading ? (
        <div className="border border-slate-700 bg-slate-900 p-4 text-sm" data-testid="admin-canonical-registry-loading">Yükleniyor...</div>
      ) : (
        <>
          <div className="overflow-x-auto border border-slate-700" data-testid="admin-canonical-registry-table-wrapper">
            <table className="min-w-[1800px] text-sm" data-testid="admin-canonical-registry-table">
              <thead className="bg-slate-900 text-left">
                <tr>
                  <th className="px-3 py-2">strategy_id</th>
                  <th className="px-3 py-2">family</th>
                  <th className="px-3 py-2">enabled</th>
                  <th className="px-3 py-2">direction</th>
                  <th className="px-3 py-2">regime</th>
                  <th className="px-3 py-2">weight</th>
                  <th className="px-3 py-2">priority</th>
                  <th className="px-3 py-2">cooldown</th>
                  <th className="px-3 py-2">quality(50)</th>
                  <th className="px-3 py-2">false_allow</th>
                  <th className="px-3 py-2">false_reject</th>
                  <th className="px-3 py-2">risk_block</th>
                  <th className="px-3 py-2">forced_disable_reason</th>
                  <th className="px-3 py-2">actions</th>
                </tr>
              </thead>
              <tbody>
                {registryRows.map((row) => (
                  <tr key={row.strategy_id} className="border-t border-slate-800" data-testid={`admin-canonical-registry-row-${row.strategy_id}`}>
                    <td className="px-3 py-2 font-semibold" data-testid={`admin-canonical-registry-strategy-id-${row.strategy_id}`}>{row.strategy_id}</td>
                    <td className="px-3 py-2" data-testid={`admin-canonical-registry-family-${row.strategy_id}`}>{row.strategy_family}</td>
                    <td className="px-3 py-2">
                      <input
                        type="checkbox"
                        checked={Boolean(row.is_enabled)}
                        onChange={(event) => updateLocal(row.strategy_id, { is_enabled: event.target.checked })}
                        data-testid={`admin-canonical-registry-enabled-input-${row.strategy_id}`}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <select
                        value={row.direction}
                        onChange={(event) => updateLocal(row.strategy_id, { direction: event.target.value })}
                        data-testid={`admin-canonical-registry-direction-select-${row.strategy_id}`}
                      >
                        {directionOptions.map((option) => (
                          <option key={option} value={option}>{option}</option>
                        ))}
                      </select>
                    </td>
                    <td className="px-3 py-2">
                      <select
                        value={row.market_regime}
                        onChange={(event) => updateLocal(row.strategy_id, { market_regime: event.target.value })}
                        data-testid={`admin-canonical-registry-regime-select-${row.strategy_id}`}
                      >
                        {regimeOptions.map((option) => (
                          <option key={option} value={option}>{option}</option>
                        ))}
                      </select>
                    </td>
                    <td className="px-3 py-2">
                      <input
                        type="number"
                        step="0.1"
                        min="0"
                        value={row.weight}
                        onChange={(event) => updateLocal(row.strategy_id, { weight: event.target.value })}
                        className="w-20 bg-transparent"
                        data-testid={`admin-canonical-registry-weight-input-${row.strategy_id}`}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <input
                        type="number"
                        value={row.priority}
                        onChange={(event) => updateLocal(row.strategy_id, { priority: event.target.value })}
                        className="w-20 bg-transparent"
                        data-testid={`admin-canonical-registry-priority-input-${row.strategy_id}`}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <input
                        type="text"
                        value={row.cooldown_policy || "symbol:180s"}
                        onChange={(event) => updateLocal(row.strategy_id, { cooldown_policy: event.target.value })}
                        className="w-28 bg-transparent"
                        data-testid={`admin-canonical-registry-cooldown-input-${row.strategy_id}`}
                      />
                    </td>
                    <td className="px-3 py-2" data-testid={`admin-canonical-registry-quality-${row.strategy_id}`}>{row.last_50_signal_quality}</td>
                    <td className="px-3 py-2" data-testid={`admin-canonical-registry-false-allow-${row.strategy_id}`}>{row.false_allow_rate}</td>
                    <td className="px-3 py-2" data-testid={`admin-canonical-registry-false-reject-${row.strategy_id}`}>{row.false_reject_rate}</td>
                    <td className="px-3 py-2" data-testid={`admin-canonical-registry-risk-block-${row.strategy_id}`}>{row.risk_block_reason || "-"}</td>
                    <td className="px-3 py-2">
                      <input
                        type="text"
                        value={row.forced_disable_reason || ""}
                        onChange={(event) => updateLocal(row.strategy_id, { forced_disable_reason: event.target.value })}
                        className="w-52 bg-transparent"
                        data-testid={`admin-canonical-registry-forced-disable-input-${row.strategy_id}`}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <Button
                        size="sm"
                        onClick={() => saveRow(row)}
                        disabled={savingId === row.strategy_id}
                        data-testid={`admin-canonical-registry-save-button-${row.strategy_id}`}
                      >
                        {savingId === row.strategy_id ? "Kaydediliyor" : "Kaydet"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="border border-slate-700 bg-slate-900 p-4" data-testid="admin-canonical-registry-legacy-panel">
            <h3 className="text-sm font-bold uppercase" data-testid="admin-canonical-registry-legacy-title">Legacy Candidates (archive only)</h3>
            <div className="mt-2 grid gap-1" data-testid="admin-canonical-registry-legacy-list">
              {legacyRows.map((row) => (
                <p key={row.strategy_id} className="text-xs" data-testid={`admin-canonical-registry-legacy-item-${row.strategy_id}`}>
                  {row.strategy_id} · in_production_path={String(row.in_production_path)} · reason={row.forced_disable_reason || "legacy"}
                </p>
              ))}
              {legacyRows.length === 0 && <p className="text-xs" data-testid="admin-canonical-registry-legacy-empty">Legacy candidate bulunamadı.</p>}
            </div>
          </div>
        </>
      )}
    </section>
  );
};
