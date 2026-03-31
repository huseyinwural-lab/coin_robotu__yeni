import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";
import { apiClient, buildSessionHeaders, FRONTEND_BACKEND_URL } from "@/lib/api";

const initialForm = {
  name: "",
  template_code: "",
  strategy_type: "trend_following",
  indicator_schema: {
    indicators: ["ema_fast", "ema_slow"],
    timeframe: "15m",
    params: { ema_fast: 20, ema_slow: 50, source: "close" },
  },
  param_schema: {
    ema_fast: { type: "int", default: 20 },
    ema_slow: { type: "int", default: 50 },
    source: { type: "str", default: "close" },
  },
  logic_schema: {
    entry_rules: { long_condition: "ema_fast > ema_slow", threshold: 0.0 },
    exit_rules: { stop_loss_pct: 1.5, take_profit_pct: 3.0, exit_condition: "ema_fast < ema_slow" },
    risk_hints: { position_size_hint_pct: 2.0, max_exposure_hint_pct: 20.0 },
  },
  parameters: { ema_fast: 20, ema_slow: 50, source: "close" },
  backtest_result_ref: "",
  is_active: false,
  reason_note: "",
};

const pretty = (value) => JSON.stringify(value || {}, null, 2);
const promotionFlow = ["DRAFT", "VALIDATED", "BACKTEST_PASSED", "ACTIVE", "DEPRECATED", "ROLLED_BACK"];

const fetchTemplateJson = async (path, { method = "GET", body = null, timeoutMs = 30000 } = {}) => {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  const token = window.localStorage.getItem("token");
  try {
    const response = await fetch(`${FRONTEND_BACKEND_URL}/api${path}`, {
      method,
      headers: {
        ...buildSessionHeaders(),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      credentials: "include",
      cache: "no-store",
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const error = new Error((payload && (payload.detail || payload.message)) || `request_failed_${response.status}`);
      error.response = { status: response.status, data: payload };
      throw error;
    }
    return payload;
  } finally {
    window.clearTimeout(timeoutId);
  }
};

export const StrategyTemplatesPage = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(initialForm);
  const [history, setHistory] = useState([]);
  const [resolved, setResolved] = useState(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  const isAdmin = ["admin", "super_admin", "ops"].includes(user?.role || "");

  const fetchItems = async () => {
    setLoading(true);
    try {
      const data = await fetchTemplateJson("/strategy-templates", { method: "GET" });
      setItems(data || []);
      setSelected((prev) => (prev ? (data || []).find((item) => item.id === prev.id) || null : null));
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Template listesi yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchItems();
  }, []);

  useEffect(() => {
    const loadPanels = async () => {
      if (!selected?.id) return;
      try {
        const [historyRes, resolvedRes] = await Promise.all([
          fetchTemplateJson(`/strategy-templates/${selected.id}/history`, { method: "GET" }),
          fetchTemplateJson(`/strategy-templates/${selected.id}/resolve`, { method: "POST", body: { volatility_regime: "normal", risk_regime: "balanced", market_regime: "neutral" } }),
        ]);
        setHistory(historyRes?.items || []);
        setResolved(resolvedRes || null);
      } catch {
        setHistory([]);
        setResolved(null);
      }
    };
    loadPanels();
  }, [selected]);

  const activeInGroup = useMemo(() => {
    if (!selected?.version_group_id) return null;
    return (items || []).find((item) => item.version_group_id === selected.version_group_id && item.is_active) || null;
  }, [items, selected]);

  const validateForm = () => {
    if (!String(form.name || "").trim()) return "Template adı zorunlu";
    if (!String(form.strategy_type || "").trim()) return "Strategy type zorunlu";
    if (!form.indicator_schema?.timeframe) return "Indicator timeframe zorunlu";
    if (!form.logic_schema?.entry_rules?.long_condition) return "Entry rule zorunlu";
    if (!form.logic_schema?.exit_rules?.exit_condition) return "Exit rule zorunlu";
    return null;
  };

  const toPayload = () => ({
    name: String(form.name || "").trim(),
    template_code: String(form.template_code || "").trim() || undefined,
    strategy_type: String(form.strategy_type || "").trim(),
    indicator_schema: form.indicator_schema,
    param_schema: form.param_schema,
    logic_schema: form.logic_schema,
    parameters: form.parameters,
    backtest_result_ref: String(form.backtest_result_ref || "").trim() || null,
    is_active: Boolean(form.is_active),
    reason_note: String(form.reason_note || "").trim() || "manual_update",
  });

  const submitTemplate = async (event) => {
    event.preventDefault();
    const validationError = validateForm();
    if (validationError) {
      toast.error(validationError);
      return;
    }
    try {
      const payload = toPayload();
      if (editingId) {
        await fetchTemplateJson(`/strategy-templates/${editingId}`, { method: "PUT", body: payload });
        toast.success("Template güncellendi");
      } else {
        await fetchTemplateJson(`/strategy-templates`, { method: "POST", body: payload });
        toast.success("Template oluşturuldu");
      }
      setEditingId(null);
      setForm(initialForm);
      await fetchItems();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Template kaydedilemedi");
    }
  };

  const editTemplate = (item) => {
    setEditingId(item.id);
    setSelected(item);
    setForm({
      name: item.name,
      template_code: item.template_code || "",
      strategy_type: item.strategy_type,
      indicator_schema: item.indicator_schema || {},
      param_schema: item.param_schema || {},
      logic_schema: item.logic_schema || {},
      parameters: item.parameters || {},
      backtest_result_ref: item.backtest_result_ref || "",
      is_active: item.is_active,
      reason_note: "edit_template",
    });
  };

  const actionReason = (fallback) => String(form.reason_note || fallback || "manual_action").trim();

  const runLifecycleAction = async (path, successMessage, fallbackError) => {
    if (!selected?.id) return;
    try {
      const data = await fetchTemplateJson(path, {
        method: "POST",
        body: { reason: actionReason(path.replaceAll("/", "_") || "lifecycle_action") },
      });
      toast.success(successMessage);
      setSelected(data);
      await fetchItems();
    } catch (error) {
      toast.error(error?.response?.data?.detail || fallbackError);
    }
  };

  const cloneVersion = async () => {
    if (!selected?.id) return;
    try {
      const data = await fetchTemplateJson(`/strategy-templates/${selected.id}/clone-version`, { method: "POST", body: { reason: actionReason("clone_version"), name: `${selected.name} clone` } });
      toast.success("Yeni version oluşturuldu");
      setSelected(data);
      await fetchItems();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Clone version başarısız");
    }
  };

  const validateVersion = async () => runLifecycleAction(`/strategy-templates/${selected.id}/validate`, "Template VALIDATED oldu", "Validate başarısız");

  const markBacktestPassed = async () => runLifecycleAction(`/strategy-templates/${selected.id}/mark-backtest-passed`, "Template BACKTEST_PASSED oldu", "Backtest pass işareti başarısız");

  const promoteToActive = async () => runLifecycleAction(`/strategy-templates/${selected.id}/promote-to-active`, "Template ACTIVE oldu", "Promote başarısız");

  const deprecateVersion = async () => runLifecycleAction(`/strategy-templates/${selected.id}/deprecate`, "Template DEPRECATED oldu", "Deprecate başarısız");

  const rollbackVersion = async () => {
    if (!selected?.id) return;
    try {
      const data = await fetchTemplateJson(`/strategy-templates/${selected.id}/rollback`, { method: "POST", body: { reason: actionReason("rollback_version") } });
      toast.success("Rollback tamamlandı");
      setSelected(data);
      await fetchItems();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Rollback başarısız");
    }
  };

  return (
    <section className="space-y-4" data-testid="strategy-templates-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="strategy-templates-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="strategy-templates-title">Strategy Template Lifecycle</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="strategy-templates-description">Versioned, doğrulanabilir ve runtime resolution destekli strategy asset merkezi.</p>
      </header>

      {!isAdmin && (
        <section className="border border-emerald-500/40 bg-emerald-500/10 p-4" data-testid="strategy-templates-user-bridge-panel">
          <p className="text-xs uppercase tracking-widest text-emerald-300">User Bridge Guidance</p>
          <p className="mt-2 text-sm text-emerald-100">Bu ekran read-only. Template sonucu Bot Profiles ve Scanner içinde görünür.</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => navigate("/user/scanner")} data-testid="strategy-template-user-bridge-open-scanner-button">Scanner’a Git</Button>
            <Button variant="outline" onClick={() => navigate("/user/bot-profiles")} data-testid="strategy-template-user-bridge-open-bot-profiles-button">Bot Profiles’a Git</Button>
          </div>
        </section>
      )}

      <div className="grid gap-4 xl:grid-cols-[360px,1fr]" data-testid="strategy-template-layout-grid">
        <aside className="space-y-3" data-testid="strategy-template-list-panel">
          <div className="border border-slate-800 bg-slate-900 p-4">
            <p className="text-xs uppercase tracking-widest text-slate-500">Template List</p>
            {loading && <p className="mt-3 text-sm text-slate-400">loading...</p>}
            <div className="mt-3 space-y-2" data-testid="strategy-template-list-items">
              {(items || []).map((item, idx) => (
                <div key={item.id} className={`block w-full border p-3 text-left ${selected?.id === item.id ? "border-cyan-500 bg-cyan-950/20" : "border-slate-800 bg-slate-900"}`} data-testid={`strategy-template-list-item-${idx}`}>
                  <p className="font-semibold text-slate-100">{item.name}</p>
                  <p className="mt-1 text-xs text-slate-400">{item.template_code} · v{item.version_num}</p>
                  <div className="mt-2 flex flex-wrap gap-2 text-[11px] uppercase tracking-wide">
                    <span className={`rounded px-2 py-1 ${item.is_active ? "bg-emerald-800 text-emerald-200" : "bg-slate-700 text-slate-200"}`}>{item.lifecycle_state}</span>
                    {item.is_active && <span className="rounded bg-cyan-800 px-2 py-1 text-cyan-100">ACTIVE</span>}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Button type="button" variant="outline" onClick={() => setSelected(item)} data-testid={`strategy-template-select-item-${idx}`}>Select</Button>
                    <Button type="button" variant="outline" onClick={(event) => { event.stopPropagation(); navigate(`/user/strategies/${item.id}`); }} data-testid={`strategy-template-open-detail-${idx}`}>Open detail</Button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="border border-slate-800 bg-slate-900 p-4" data-testid="strategy-template-history-panel">
            <p className="text-xs uppercase tracking-widest text-slate-500">Version History</p>
            <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-[11px] text-slate-300" data-testid="strategy-template-history-json">{pretty(history)}</pre>
          </div>

          <div className="border border-slate-800 bg-slate-900 p-4" data-testid="strategy-template-resolve-preview-panel">
            <p className="text-xs uppercase tracking-widest text-slate-500">Resolve Preview</p>
            <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-[11px] text-slate-300" data-testid="strategy-template-resolve-preview-json">{pretty(resolved)}</pre>
          </div>

          <div className="border border-slate-800 bg-slate-900 p-4" data-testid="strategy-template-promotion-flow-panel">
            <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-template-promotion-flow-title">Promotion Flow</p>
            <div className="mt-3 flex flex-wrap gap-2" data-testid="strategy-template-promotion-flow-list">
              {promotionFlow.map((state, idx) => {
                const isCurrent = selected?.lifecycle_state === state;
                const isPassed = promotionFlow.indexOf(selected?.lifecycle_state || "") > idx;
                return (
                  <span
                    key={state}
                    className={`rounded px-2 py-1 text-[11px] uppercase tracking-wide ${isCurrent ? "bg-cyan-700 text-white" : isPassed ? "bg-emerald-800 text-emerald-100" : "bg-slate-800 text-slate-300"}`}
                    data-testid={`strategy-template-promotion-flow-state-${state.toLowerCase()}`}
                  >
                    {state}
                  </span>
                );
              })}
            </div>
          </div>
        </aside>

        <section className="space-y-4" data-testid="strategy-template-editor-panel">
          <form onSubmit={submitTemplate} className="grid gap-4 border border-slate-800 bg-slate-900 p-4" data-testid="strategy-template-form">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <p className="mb-2 text-xs uppercase tracking-widest text-slate-500">Basic</p>
                <Input placeholder="Template adı" value={form.name} onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))} data-testid="strategy-form-name-input" required />
                <Input className="mt-2" placeholder="Template code" value={form.template_code} onChange={(event) => setForm((prev) => ({ ...prev, template_code: event.target.value }))} data-testid="strategy-form-code-input" />
                <Input className="mt-2" placeholder="Strategy type" value={form.strategy_type} onChange={(event) => setForm((prev) => ({ ...prev, strategy_type: event.target.value }))} data-testid="strategy-form-type-input" required />
                <Input className="mt-2" placeholder="Backtest result ref" value={form.backtest_result_ref} onChange={(event) => setForm((prev) => ({ ...prev, backtest_result_ref: event.target.value }))} data-testid="strategy-form-backtest-ref-input" />
              </div>
              <div>
                <p className="mb-2 text-xs uppercase tracking-widest text-slate-500">Indicator Settings</p>
                <Input placeholder="Indicators (csv)" value={(form.indicator_schema?.indicators || []).join(",")} onChange={(event) => setForm((prev) => ({ ...prev, indicator_schema: { ...(prev.indicator_schema || {}), indicators: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) } }))} data-testid="strategy-form-indicators-input" />
                <Input className="mt-2" placeholder="Timeframe" value={form.indicator_schema?.timeframe || ""} onChange={(event) => setForm((prev) => ({ ...prev, indicator_schema: { ...(prev.indicator_schema || {}), timeframe: event.target.value } }))} data-testid="strategy-form-timeframe-input" />
                <Input className="mt-2" placeholder="EMA fast" type="number" value={form.parameters?.ema_fast ?? 20} onChange={(event) => setForm((prev) => ({ ...prev, parameters: { ...(prev.parameters || {}), ema_fast: Number(event.target.value) }, param_schema: { ...(prev.param_schema || {}), ema_fast: { type: 'int', default: Number(event.target.value) } } }))} data-testid="strategy-form-ema-fast-input" />
                <Input className="mt-2" placeholder="EMA slow" type="number" value={form.parameters?.ema_slow ?? 50} onChange={(event) => setForm((prev) => ({ ...prev, parameters: { ...(prev.parameters || {}), ema_slow: Number(event.target.value) }, param_schema: { ...(prev.param_schema || {}), ema_slow: { type: 'int', default: Number(event.target.value) } } }))} data-testid="strategy-form-ema-slow-input" />
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <p className="mb-2 text-xs uppercase tracking-widest text-slate-500">Entry Rules</p>
                <Input placeholder="Long condition" value={form.logic_schema?.entry_rules?.long_condition || ""} onChange={(event) => setForm((prev) => ({ ...prev, logic_schema: { ...(prev.logic_schema || {}), entry_rules: { ...(prev.logic_schema?.entry_rules || {}), long_condition: event.target.value } } }))} data-testid="strategy-form-entry-condition-input" />
                <Input className="mt-2" placeholder="Threshold" type="number" value={form.logic_schema?.entry_rules?.threshold ?? 0} onChange={(event) => setForm((prev) => ({ ...prev, logic_schema: { ...(prev.logic_schema || {}), entry_rules: { ...(prev.logic_schema?.entry_rules || {}), threshold: Number(event.target.value) } } }))} data-testid="strategy-form-entry-threshold-input" />
              </div>
              <div>
                <p className="mb-2 text-xs uppercase tracking-widest text-slate-500">Exit Rules</p>
                <Input placeholder="Stop loss %" type="number" value={form.logic_schema?.exit_rules?.stop_loss_pct ?? 1.5} onChange={(event) => setForm((prev) => ({ ...prev, logic_schema: { ...(prev.logic_schema || {}), exit_rules: { ...(prev.logic_schema?.exit_rules || {}), stop_loss_pct: Number(event.target.value) } } }))} data-testid="strategy-form-stop-loss-input" />
                <Input className="mt-2" placeholder="Take profit %" type="number" value={form.logic_schema?.exit_rules?.take_profit_pct ?? 3} onChange={(event) => setForm((prev) => ({ ...prev, logic_schema: { ...(prev.logic_schema || {}), exit_rules: { ...(prev.logic_schema?.exit_rules || {}), take_profit_pct: Number(event.target.value) } } }))} data-testid="strategy-form-take-profit-input" />
                <Input className="mt-2" placeholder="Exit condition" value={form.logic_schema?.exit_rules?.exit_condition || ""} onChange={(event) => setForm((prev) => ({ ...prev, logic_schema: { ...(prev.logic_schema || {}), exit_rules: { ...(prev.logic_schema?.exit_rules || {}), exit_condition: event.target.value } } }))} data-testid="strategy-form-exit-condition-input" />
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <p className="mb-2 text-xs uppercase tracking-widest text-slate-500">Risk Hints</p>
                <Input placeholder="Position sizing hint %" type="number" value={form.logic_schema?.risk_hints?.position_size_hint_pct ?? 2} onChange={(event) => setForm((prev) => ({ ...prev, logic_schema: { ...(prev.logic_schema || {}), risk_hints: { ...(prev.logic_schema?.risk_hints || {}), position_size_hint_pct: Number(event.target.value) } } }))} data-testid="strategy-form-position-size-hint-input" />
                <Input className="mt-2" placeholder="Max exposure hint %" type="number" value={form.logic_schema?.risk_hints?.max_exposure_hint_pct ?? 20} onChange={(event) => setForm((prev) => ({ ...prev, logic_schema: { ...(prev.logic_schema || {}), risk_hints: { ...(prev.logic_schema?.risk_hints || {}), max_exposure_hint_pct: Number(event.target.value) } } }))} data-testid="strategy-form-max-exposure-hint-input" />
              </div>
              <div>
                <p className="mb-2 text-xs uppercase tracking-widest text-slate-500">Reason Note</p>
                <Input placeholder="reason note" value={form.reason_note} onChange={(event) => setForm((prev) => ({ ...prev, reason_note: event.target.value }))} data-testid="strategy-form-reason-input" />
                <label className="mt-3 flex items-center gap-2 text-sm text-slate-300" data-testid="strategy-form-active-checkbox-wrapper">
                  <input type="checkbox" checked={form.is_active} onChange={(event) => setForm((prev) => ({ ...prev, is_active: event.target.checked }))} data-testid="strategy-form-active-checkbox" />
                  active flag (draft save dışında activate aksiyonu önerilir)
                </label>
              </div>
            </div>

            <div className="rounded border border-slate-800 bg-slate-950 p-3" data-testid="strategy-form-advanced-panel">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs uppercase tracking-widest text-slate-500">Advanced</p>
                <Button type="button" variant="outline" onClick={() => setAdvancedOpen((prev) => !prev)} data-testid="strategy-form-advanced-toggle">{advancedOpen ? 'Hide JSON' : 'Show JSON'}</Button>
              </div>
              {advancedOpen && <pre className="mt-3 overflow-x-auto text-xs text-slate-300" data-testid="strategy-form-advanced-json">{pretty({ indicator_schema: form.indicator_schema, param_schema: form.param_schema, logic_schema: form.logic_schema, parameters: form.parameters })}</pre>}
            </div>

            {isAdmin && (
              <div className="flex flex-wrap gap-2" data-testid="strategy-form-actions-row">
                <Button type="submit" className="bg-blue-500 text-white hover:bg-blue-600" data-testid="strategy-form-submit-button">{editingId ? 'Güncelle' : 'Template Oluştur'}</Button>
                {editingId && <Button type="button" variant="outline" onClick={() => { setEditingId(null); setForm(initialForm); }} data-testid="strategy-form-cancel-edit-button">İptal</Button>}
                <Button type="button" variant="outline" onClick={cloneVersion} disabled={!selected?.id} data-testid="strategy-form-clone-version-button">Clone Version</Button>
                <Button type="button" variant="outline" onClick={validateVersion} disabled={!selected?.id} data-testid="strategy-form-validate-button">Validate</Button>
                <Button type="button" variant="outline" onClick={markBacktestPassed} disabled={!selected?.id} data-testid="strategy-form-backtest-passed-button">Mark Backtest Passed</Button>
                <Button type="button" variant="outline" onClick={promoteToActive} disabled={!selected?.id} data-testid="strategy-form-promote-active-button">Promote Active</Button>
                <Button type="button" variant="outline" onClick={deprecateVersion} disabled={!selected?.id} data-testid="strategy-form-deprecate-button">Deprecate</Button>
                <Button type="button" variant="outline" onClick={rollbackVersion} disabled={!selected?.id} data-testid="strategy-form-rollback-button">Rollback</Button>
              </div>
            )}
          </form>
        </section>
      </div>
    </section>
  );
};
