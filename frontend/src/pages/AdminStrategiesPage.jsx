import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

const strategySeed = { name: "", code: "", description: "" };

const versionSeed = {
  config_schema_version: "1.0",
  config_json: '{"momentum_threshold":0.1,"base_size":0.001,"volatility_guard":0.5}',
};

const kernelContextSeed = (versionId = "", versionHash = "") => ({
  context_id: `ctx-${Date.now()}`,
  timestamp_utc: new Date().toISOString(),
  symbol: "BTCUSDT",
  timeframe: "1m",
  market_snapshot: { last_price: 100000, bid: 99990, ask: 100010 },
  market_snapshot_hash: "snapshot-hash-v1",
  position_state: { side: "flat", qty: 0 },
  risk_state: { blocked: false },
  account_state_projection: { equity: 1000, free_margin: 900 },
  strategy_version_id: versionId,
  strategy_version_hash: versionHash,
  input_features: { momentum: 0.12, volatility: 0.2, base_size: 0.001 },
  correlation_id: `corr-${Date.now()}`,
});

export const AdminStrategiesPage = () => {
  const [loading, setLoading] = useState(true);
  const [strategies, setStrategies] = useState([]);
  const [selectedStrategyId, setSelectedStrategyId] = useState("");
  const [detail, setDetail] = useState(null);

  const [strategyForm, setStrategyForm] = useState(strategySeed);
  const [versionForm, setVersionForm] = useState(versionSeed);
  const [decisionResult, setDecisionResult] = useState(null);
  const [kernelContextText, setKernelContextText] = useState(JSON.stringify(kernelContextSeed(), null, 2));
  const [runtimeDispatchResult, setRuntimeDispatchResult] = useState(null);
  const [workerResult, setWorkerResult] = useState(null);
  const [runtimeIntents, setRuntimeIntents] = useState([]);
  const [hotTraces, setHotTraces] = useState([]);
  const [coldTraces, setColdTraces] = useState([]);

  const selectedActiveVersion = useMemo(
    () => detail?.versions?.find((item) => item.version_id === detail?.strategy?.active_version_id) || detail?.versions?.[0],
    [detail],
  );

  const loadStrategies = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/strategy-domain/admin/strategies");
      setStrategies(data || []);
      if (!selectedStrategyId && data?.length) {
        setSelectedStrategyId(data[0].strategy_id);
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Strategy listesi yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, [selectedStrategyId]);

  const loadDetail = useCallback(async (strategyId) => {
    if (!strategyId) return;
    try {
      const { data } = await apiClient.get(`/strategy-domain/admin/strategies/${strategyId}`);
      setDetail(data);
      const activeVersion = data?.versions?.find((item) => item.version_id === data?.strategy?.active_version_id) || data?.versions?.[0];
      if (activeVersion) {
        setKernelContextText(JSON.stringify(kernelContextSeed(activeVersion.version_id, activeVersion.version_hash), null, 2));
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Strategy detayı yüklenemedi");
      setDetail(null);
    }
  }, []);

  useEffect(() => {
    loadStrategies();
  }, [loadStrategies]);

  useEffect(() => {
    if (selectedStrategyId) {
      loadDetail(selectedStrategyId);
    }
  }, [loadDetail, selectedStrategyId]);

  const createStrategy = async (event) => {
    event.preventDefault();
    try {
      await apiClient.post("/strategy-domain/admin/strategies", strategyForm);
      toast.success("Strategy definition oluşturuldu");
      setStrategyForm(strategySeed);
      await loadStrategies();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Strategy oluşturulamadı");
    }
  };

  const createVersion = async (event) => {
    event.preventDefault();
    if (!selectedStrategyId) return;
    try {
      const configJson = JSON.parse(versionForm.config_json);
      await apiClient.post(`/strategy-domain/admin/strategies/${selectedStrategyId}/versions`, {
        config_json: configJson,
        config_schema_version: versionForm.config_schema_version,
      });
      toast.success("Strategy version eklendi");
      await loadDetail(selectedStrategyId);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Version oluşturulamadı (JSON kontrol edin)");
    }
  };

  const activateVersion = async (versionId) => {
    try {
      await apiClient.post(`/strategy-domain/admin/strategies/${selectedStrategyId}/activate/${versionId}`);
      toast.success("Active version güncellendi");
      await loadDetail(selectedStrategyId);
      await loadStrategies();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Aktivasyon başarısız");
    }
  };

  const archiveStrategy = async () => {
    if (!selectedStrategyId) return;
    if (!window.confirm("Strategy archive edilsin mi?")) return;
    try {
      await apiClient.post(`/strategy-domain/admin/strategies/${selectedStrategyId}/archive`);
      toast.success("Strategy archived");
      await loadDetail(selectedStrategyId);
      await loadStrategies();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Archive başarısız");
    }
  };

  const evaluateKernel = async () => {
    try {
      const payload = JSON.parse(kernelContextText);
      const { data } = await apiClient.post("/strategy-domain/admin/kernel/evaluate", payload);
      setDecisionResult(data);
      toast.success("Kernel evaluate tamamlandı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Kernel evaluate başarısız (JSON kontrol edin)");
    }
  };

  const loadRuntimeViews = useCallback(async () => {
    try {
      const [intentsRes, hotRes, coldRes] = await Promise.all([
        apiClient.get("/strategy-domain/admin/runtime/intents"),
        apiClient.get("/strategy-domain/admin/runtime/hot-traces"),
        apiClient.get("/strategy-domain/admin/runtime/cold-traces"),
      ]);
      setRuntimeIntents(intentsRes.data || []);
      setHotTraces(hotRes.data || []);
      setColdTraces(coldRes.data || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Runtime görünümü yüklenemedi");
    }
  }, []);

  useEffect(() => {
    loadRuntimeViews();
  }, [loadRuntimeViews]);

  const dispatchRuntime = async () => {
    if (!selectedStrategyId) {
      toast.error("Önce strategy seçin");
      return;
    }
    try {
      const contextPayload = JSON.parse(kernelContextText);
      const { data } = await apiClient.post("/strategy-domain/admin/runtime/dispatch", {
        strategy_id: selectedStrategyId,
        decision_context: contextPayload,
      });
      setRuntimeDispatchResult(data);
      toast.success("Decision runtime bus’a dispatch edildi");
      await loadRuntimeViews();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Runtime dispatch başarısız");
    }
  };

  const runWorkerOnce = async () => {
    try {
      const { data } = await apiClient.post("/strategy-domain/admin/runtime/worker/run-once");
      setWorkerResult(data);
      toast.success("Worker run-once çalıştı");
      await loadRuntimeViews();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Worker run-once başarısız");
    }
  };

  return (
    <section className="space-y-4" data-testid="admin-strategies-page">
      <header className="border border-orange-700 bg-slate-900 p-4" data-testid="admin-strategies-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-orange-300" data-testid="admin-strategies-title">Strategy Domain Control</h2>
        <p className="mt-2 text-sm text-slate-300" data-testid="admin-strategies-description">
          Append-only StrategyDefinition/StrategyVersion yönetimi + deterministic kernel contract doğrulama yüzeyi.
        </p>
      </header>

      <div className="grid gap-4 xl:grid-cols-2" data-testid="admin-strategies-top-grid">
        <form className="space-y-2 border border-slate-800 bg-slate-900 p-4" onSubmit={createStrategy} data-testid="admin-strategy-create-form">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-create-title">Create StrategyDefinition</p>
          <Input placeholder="name" value={strategyForm.name} onChange={(e) => setStrategyForm((prev) => ({ ...prev, name: e.target.value }))} data-testid="admin-strategy-create-name-input" required />
          <Input placeholder="code (unique)" value={strategyForm.code} onChange={(e) => setStrategyForm((prev) => ({ ...prev, code: e.target.value }))} data-testid="admin-strategy-create-code-input" required />
          <Input placeholder="description" value={strategyForm.description} onChange={(e) => setStrategyForm((prev) => ({ ...prev, description: e.target.value }))} data-testid="admin-strategy-create-description-input" />
          <Button className="bg-orange-500 text-black hover:bg-orange-600" data-testid="admin-strategy-create-submit-button">Create Definition</Button>
        </form>

        <form className="space-y-2 border border-slate-800 bg-slate-900 p-4" onSubmit={createVersion} data-testid="admin-strategy-version-create-form">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-version-title">Create StrategyVersion</p>
          <Input placeholder="config schema version" value={versionForm.config_schema_version} onChange={(e) => setVersionForm((prev) => ({ ...prev, config_schema_version: e.target.value }))} data-testid="admin-strategy-version-schema-input" />
          <textarea className="h-36 w-full border border-slate-700 bg-slate-950 p-2 text-sm" value={versionForm.config_json} onChange={(e) => setVersionForm((prev) => ({ ...prev, config_json: e.target.value }))} data-testid="admin-strategy-version-config-textarea" />
          <Button className="bg-orange-500 text-black hover:bg-orange-600" disabled={!selectedStrategyId} data-testid="admin-strategy-version-submit-button">Create Version</Button>
        </form>
      </div>

      <div className="grid gap-4 xl:grid-cols-3" data-testid="admin-strategies-main-grid">
        <div className="border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategies-list-panel">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategies-list-title">Strategy List</p>
          {loading && <p className="mt-2 text-sm text-slate-400" data-testid="admin-strategies-loading-text">Yükleniyor...</p>}
          <div className="mt-3 space-y-2" data-testid="admin-strategies-list">
            {strategies.map((item) => (
              <button
                type="button"
                key={item.strategy_id}
                onClick={() => setSelectedStrategyId(item.strategy_id)}
                className={`w-full border p-2 text-left text-sm ${selectedStrategyId === item.strategy_id ? "border-orange-500 bg-orange-500/10" : "border-slate-700"}`}
                data-testid={`admin-strategy-select-button-${item.strategy_id}`}
              >
                <p data-testid={`admin-strategy-item-code-${item.strategy_id}`}>{item.code}</p>
                <p className="text-xs text-slate-400" data-testid={`admin-strategy-item-status-${item.strategy_id}`}>{item.status}</p>
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-3 border border-slate-800 bg-slate-900 p-4 xl:col-span-2" data-testid="admin-strategy-detail-panel">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-detail-title">Strategy Detail</p>
          {detail?.strategy && (
            <div className="border border-slate-700 p-3" data-testid="admin-strategy-detail-card">
              <p className="text-sm" data-testid="admin-strategy-detail-code">code: {detail.strategy.code}</p>
              <p className="text-sm" data-testid="admin-strategy-detail-status">status: {detail.strategy.status}</p>
              <p className="text-sm" data-testid="admin-strategy-detail-active-version">active_version_id: {detail.strategy.active_version_id || "-"}</p>
              <Button variant="outline" className="mt-2 border-red-500 text-red-300" onClick={archiveStrategy} data-testid="admin-strategy-archive-button">Archive Strategy</Button>
            </div>
          )}

          <div className="space-y-2" data-testid="admin-strategy-versions-list">
            {(detail?.versions || []).map((item) => (
              <div key={item.version_id} className="border border-slate-700 p-3" data-testid={`admin-strategy-version-row-${item.version_id}`}>
                <p className="text-sm" data-testid={`admin-strategy-version-number-${item.version_id}`}>v{item.version_number} · schema={item.config_schema_version}</p>
                <p className="text-xs text-slate-400 break-all" data-testid={`admin-strategy-version-hash-${item.version_id}`}>hash: {item.version_hash}</p>
                <Button className="mt-2 bg-orange-500 text-black hover:bg-orange-600" onClick={() => activateVersion(item.version_id)} data-testid={`admin-strategy-version-activate-button-${item.version_id}`}>Activate Version</Button>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-kernel-evaluate-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-kernel-evaluate-title">Deterministic Kernel Evaluate</p>
        <textarea className="h-52 w-full border border-slate-700 bg-slate-950 p-2 text-sm" value={kernelContextText} onChange={(e) => setKernelContextText(e.target.value)} data-testid="admin-kernel-context-textarea" />
        <Button className="bg-orange-500 text-black hover:bg-orange-600" onClick={evaluateKernel} data-testid="admin-kernel-evaluate-button">Evaluate Context</Button>
        <div className="flex flex-wrap gap-2" data-testid="admin-runtime-actions-row">
          <Button className="bg-emerald-500 text-black hover:bg-emerald-600" onClick={dispatchRuntime} data-testid="admin-runtime-dispatch-button">Dispatch Runtime</Button>
          <Button variant="outline" className="border-slate-500 text-slate-200" onClick={runWorkerOnce} data-testid="admin-runtime-worker-run-once-button">Worker Run Once</Button>
          <Button variant="outline" className="border-slate-500 text-slate-200" onClick={loadRuntimeViews} data-testid="admin-runtime-refresh-button">Refresh Runtime Views</Button>
        </div>

        {decisionResult && (
          <div className="border border-slate-700 p-3" data-testid="admin-kernel-result-card">
            <p className="text-sm" data-testid="admin-kernel-result-action">action: {decisionResult.action}</p>
            <p className="text-sm" data-testid="admin-kernel-result-confidence">confidence: {decisionResult.confidence}</p>
            <p className="text-sm" data-testid="admin-kernel-result-risk-score">risk_score: {decisionResult.risk_score}</p>
            <p className="text-xs text-slate-400 break-all" data-testid="admin-kernel-result-context-hash">context_hash: {decisionResult.context_hash}</p>
            <p className="text-xs text-slate-400 break-all" data-testid="admin-kernel-result-decision-hash">decision_hash: {decisionResult.decision_hash}</p>
          </div>
        )}

        {runtimeDispatchResult && (
          <div className="border border-slate-700 p-3" data-testid="admin-runtime-dispatch-result-card">
            <p className="text-sm" data-testid="admin-runtime-dispatch-intent-id">intent_id: {runtimeDispatchResult?.execution_intent?.intent_id || "-"}</p>
            <p className="text-sm" data-testid="admin-runtime-dispatch-events-count">emitted_events: {(runtimeDispatchResult?.emitted_events || []).length}</p>
          </div>
        )}

        {workerResult && (
          <div className="border border-slate-700 p-3" data-testid="admin-runtime-worker-result-card">
            <p className="text-sm" data-testid="admin-runtime-worker-result-status">status: {workerResult.status}</p>
            <p className="text-xs text-slate-400" data-testid="admin-runtime-worker-result-event-id">event_id: {workerResult.event_id || "-"}</p>
          </div>
        )}
      </div>

      <div className="grid gap-4 xl:grid-cols-3" data-testid="admin-runtime-views-grid">
        <div className="border border-slate-800 bg-slate-900 p-4" data-testid="admin-runtime-intents-panel">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-runtime-intents-title">Execution Intents</p>
          <div className="mt-3 space-y-2" data-testid="admin-runtime-intents-list">
            {runtimeIntents.map((item) => (
              <div key={item.intent_id} className="border border-slate-700 p-2" data-testid={`admin-runtime-intent-row-${item.intent_id}`}>
                <p className="text-xs" data-testid={`admin-runtime-intent-symbol-${item.intent_id}`}>{item.symbol} · {item.side}</p>
                <p className="text-xs text-slate-400" data-testid={`admin-runtime-intent-hash-${item.intent_id}`}>{item.intent_hash}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="border border-slate-800 bg-slate-900 p-4" data-testid="admin-runtime-hot-panel">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-runtime-hot-title">Hot Trace Store</p>
          <div className="mt-3 space-y-2" data-testid="admin-runtime-hot-list">
            {hotTraces.map((item) => (
              <div key={item.trace_id} className="border border-slate-700 p-2" data-testid={`admin-runtime-hot-row-${item.trace_id}`}>
                <p className="text-xs" data-testid={`admin-runtime-hot-correlation-${item.trace_id}`}>{item.correlation_id}</p>
                <p className="text-xs text-slate-400" data-testid={`admin-runtime-hot-decision-hash-${item.trace_id}`}>{item.decision_hash}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="border border-slate-800 bg-slate-900 p-4" data-testid="admin-runtime-cold-panel">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-runtime-cold-title">Cold Trace Archive</p>
          <div className="mt-3 space-y-2" data-testid="admin-runtime-cold-list">
            {coldTraces.map((item) => (
              <div key={item.archive_id} className="border border-slate-700 p-2" data-testid={`admin-runtime-cold-row-${item.archive_id}`}>
                <p className="text-xs" data-testid={`admin-runtime-cold-terminal-${item.archive_id}`}>{item.terminal_state}</p>
                <p className="text-xs text-slate-400" data-testid={`admin-runtime-cold-intent-hash-${item.archive_id}`}>{item.intent_hash || "-"}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};
