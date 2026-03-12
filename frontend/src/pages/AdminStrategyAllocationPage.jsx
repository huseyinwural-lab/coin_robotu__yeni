import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

export const AdminStrategyAllocationPage = () => {
  const [rows, setRows] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [lastUpdatedAt, setLastUpdatedAt] = useState("");

  const load = async () => {
    setIsLoading(true);
    setLoadError("");
    try {
      const { data } = await apiClient.get("/admin/strategy-allocation");
      setRows(data || []);
      const initialDrafts = {};
      (data || []).forEach((item) => {
        initialDrafts[item.strategy_id] = {
          capital_weight: item.capital_weight,
          max_capital: item.max_capital,
          current_capital: item.current_capital,
          state: item.state,
        };
      });
      setDrafts(initialDrafts);
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

  const summary = useMemo(() => {
    const total = rows.length;
    const throttled = rows.filter((item) => item.state === "THROTTLED").length;
    const disabled = rows.filter((item) => item.state === "DISABLED").length;
    return { total, throttled, disabled };
  }, [rows]);

  const updateDraft = (strategyId, key, value) => {
    setDrafts((prev) => ({
      ...prev,
      [strategyId]: {
        ...(prev[strategyId] || {}),
        [key]: value,
      },
    }));
  };

  const saveStrategy = async (strategyId) => {
    const payload = drafts[strategyId] || {};
    try {
      await apiClient.put(`/admin/strategy-allocation/${encodeURIComponent(strategyId)}`, {
        capital_weight: Number(payload.capital_weight),
        max_capital: Number(payload.max_capital),
        current_capital: Number(payload.current_capital),
        state: payload.state,
      });
      toast.success(`Allocation güncellendi: ${strategyId}`);
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Allocation güncellenemedi");
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

      <div className="col-span-12 grid gap-3 md:grid-cols-3" data-testid="admin-strategy-allocation-summary-grid">
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-strategy-allocation-summary-total">
          <p className="text-xs text-slate-500">Toplam Strategy</p>
          <p className="text-xl font-semibold">{summary.total}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-strategy-allocation-summary-throttled">
          <p className="text-xs text-slate-500">THROTTLED</p>
          <p className="text-xl font-semibold text-amber-400">{summary.throttled}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-strategy-allocation-summary-disabled">
          <p className="text-xs text-slate-500">DISABLED</p>
          <p className="text-xl font-semibold text-rose-400">{summary.disabled}</p>
        </article>
      </div>

      <div className="col-span-12 overflow-x-auto border border-slate-800 bg-slate-900" data-testid="admin-strategy-allocation-table-wrapper">
        <table className="min-w-full text-sm" data-testid="admin-strategy-allocation-table">
          <thead className="bg-slate-800 text-left" data-testid="admin-strategy-allocation-table-head">
            <tr>
              <th className="px-3 py-2">Strategy</th>
              <th className="px-3 py-2">Weight</th>
              <th className="px-3 py-2">Max Capital</th>
              <th className="px-3 py-2">Current Capital</th>
              <th className="px-3 py-2">State</th>
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
              return (
                <tr key={item.strategy_id} className="border-t border-slate-800" data-testid={`admin-strategy-allocation-row-${item.strategy_id}`}>
                  <td className="px-3 py-2" data-testid={`admin-strategy-allocation-strategy-${item.strategy_id}`}>{item.strategy_id}</td>
                  <td className="px-3 py-2"><Input value={draft.capital_weight ?? ""} type="number" onChange={(event) => updateDraft(item.strategy_id, "capital_weight", event.target.value)} data-testid={`admin-strategy-allocation-weight-input-${item.strategy_id}`} /></td>
                  <td className="px-3 py-2"><Input value={draft.max_capital ?? ""} type="number" onChange={(event) => updateDraft(item.strategy_id, "max_capital", event.target.value)} data-testid={`admin-strategy-allocation-max-capital-input-${item.strategy_id}`} /></td>
                  <td className="px-3 py-2"><Input value={draft.current_capital ?? ""} type="number" onChange={(event) => updateDraft(item.strategy_id, "current_capital", event.target.value)} data-testid={`admin-strategy-allocation-current-capital-input-${item.strategy_id}`} /></td>
                  <td className="px-3 py-2">
                    <select className="w-full border border-slate-700 bg-slate-950 px-2 py-1" value={draft.state || "ACTIVE"} onChange={(event) => updateDraft(item.strategy_id, "state", event.target.value)} data-testid={`admin-strategy-allocation-state-select-${item.strategy_id}`}>
                      <option value="ACTIVE">ACTIVE</option>
                      <option value="THROTTLED">THROTTLED</option>
                      <option value="DISABLED">DISABLED</option>
                    </select>
                  </td>
                  <td className="px-3 py-2" data-testid={`admin-strategy-allocation-confidence-${item.strategy_id}`}>{item.confidence_score}</td>
                  <td className="px-3 py-2" data-testid={`admin-strategy-allocation-performance-${item.strategy_id}`}>{item.performance_score}</td>
                  <td className="px-3 py-2" data-testid={`admin-strategy-allocation-signal-decay-${item.strategy_id}`}>{item.signal_decay}</td>
                  <td className="px-3 py-2" data-testid={`admin-strategy-allocation-execution-quality-${item.strategy_id}`}>{item.execution_quality_score}</td>
                  <td className="px-3 py-2">
                    <Button variant="outline" onClick={() => saveStrategy(item.strategy_id)} data-testid={`admin-strategy-allocation-save-button-${item.strategy_id}`}>Kaydet</Button>
                  </td>
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr className="border-t border-slate-800" data-testid="admin-strategy-allocation-empty-row">
                <td colSpan={10} className="px-3 py-4 text-center text-sm text-slate-400" data-testid="admin-strategy-allocation-empty-text">Strategy allocation kaydı bulunamadı.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
};
