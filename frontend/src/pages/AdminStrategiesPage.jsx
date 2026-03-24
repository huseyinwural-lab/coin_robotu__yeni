import { useCallback, useEffect, useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

const strategySeed = { name: "", code: "", description: "", owner_name: "", category: "general", tags_text: "" };

const versionSeed = {
  config_schema_version: "1.0",
  config_json: '{"momentum_threshold":0.1,"base_size":0.001,"volatility_guard":0.5}',
};

const kernelContextSeed = (versionId = "", versionHash = "") => ({
  context_id: `ctx-${Date.now()}`,
  account_id: "acct-demo",
  timestamp_utc: new Date().toISOString(),
  symbol: "BTCUSDT",
  timeframe: "1m",
  market_snapshot: { last_price: 100000, bid: 99990, ask: 100010 },
  market_snapshot_hash: "snapshot-hash-v1",
  position_state: { side: "flat", qty: 0 },
  risk_state: { blocked: false },
  account_state_projection: { equity: 1000, free_margin: 900, daily_loss_pct: 1.2, daily_loss_usd: 12 },
  strategy_version_id: versionId,
  strategy_version_hash: versionHash,
  input_features: { momentum: 0.12, volatility: 0.2, base_size: 0.001 },
  correlation_id: `corr-${Date.now()}`,
});

const buildRegimeContext = (versionId = "", versionHash = "", variant = "allowed") => {
  const base = kernelContextSeed(versionId, versionHash);
  if (variant === "allowed") {
    return {
      ...base,
      input_features: { momentum: 0.2, volatility: 0.18, base_size: 0.001 },
      market_snapshot: { last_price: 100000, bid: 99995, ask: 100005 },
    };
  }
  return {
    ...base,
    input_features: { momentum: 0.01, volatility: 0.92, base_size: 0.001 },
    market_snapshot: { last_price: 100000, bid: 96000, ask: 104000 },
  };
};

const roleFilterPresets = {
  desk: {
    status_filter: "active",
    lifecycle_state: "production",
    validation_status: "PASS",
    sort_by: "updated_at",
    sort_order: "desc",
    active_only: true,
    production_only: true,
  },
  ops: {
    status_filter: "active",
    lifecycle_state: "dry_run_passed",
    validation_status: "PASS",
    sort_by: "updated_at",
    sort_order: "desc",
    active_only: false,
    production_only: false,
  },
  admin: {
    status_filter: "",
    lifecycle_state: "",
    validation_status: "",
    sort_by: "updated_at",
    sort_order: "desc",
    active_only: false,
    production_only: false,
  },
};

export const AdminStrategiesPage = () => {
  const [loading, setLoading] = useState(true);
  const [strategies, setStrategies] = useState([]);
  const [selectedStrategyId, setSelectedStrategyId] = useState("");
  const [detail, setDetail] = useState(null);
  const [timelineItems, setTimelineItems] = useState([]);
  const [rollbackChain, setRollbackChain] = useState([]);
  const [diffResult, setDiffResult] = useState(null);
  const [bindingPreview, setBindingPreview] = useState(null);
  const [promotionRequests, setPromotionRequests] = useState([]);
  const [standardDecisionResult, setStandardDecisionResult] = useState(null);
  const [replayResult, setReplayResult] = useState(null);
  const [compareResult, setCompareResult] = useState(null);
  const [compareSelection, setCompareSelection] = useState({ version_a_id: "", version_b_id: "" });
  const [executionPreviewResult, setExecutionPreviewResult] = useState(null);
  const [metricsSummary, setMetricsSummary] = useState(null);
  const [metricsTrend, setMetricsTrend] = useState(null);
  const [driftSummary, setDriftSummary] = useState(null);
  const [falseSignalSummary, setFalseSignalSummary] = useState(null);
  const [promotionReadiness, setPromotionReadiness] = useState(null);
  const [selectedStrategyIds, setSelectedStrategyIds] = useState([]);
  const [savedFilterName, setSavedFilterName] = useState("");
  const [savedFilters, setSavedFilters] = useState({});
  const [filterOptions, setFilterOptions] = useState({ owner_names: [], categories: [], tags: [] });
  const [selectedTagFilters, setSelectedTagFilters] = useState([]);
  const [auditFilters, setAuditFilters] = useState({ eventType: "", user: "", from: "", to: "" });
  const [bulkActionSummary, setBulkActionSummary] = useState(null);
  const [showConfigDiffMode, setShowConfigDiffMode] = useState(false);
  const [showExecutionExplain, setShowExecutionExplain] = useState(false);
  const [listFilters, setListFilters] = useState({
    search: "",
    status_filter: "",
    lifecycle_state: "",
    validation_status: "",
    owner_name: "",
    category: "",
    sort_by: "updated_at",
    sort_order: "desc",
    page: 1,
    page_size: 50,
    active_only: false,
    production_only: false,
  });

  const [strategyForm, setStrategyForm] = useState(strategySeed);
  const [versionForm, setVersionForm] = useState(versionSeed);
  const [decisionResult, setDecisionResult] = useState(null);
  const [kernelContextText, setKernelContextText] = useState(JSON.stringify(kernelContextSeed(), null, 2));
  const [runtimeDispatchResult, setRuntimeDispatchResult] = useState(null);
  const [workerResult, setWorkerResult] = useState(null);
  const [runtimeIntents, setRuntimeIntents] = useState([]);
  const [hotTraces, setHotTraces] = useState([]);
  const [coldTraces, setColdTraces] = useState([]);
  const [regimeBindings, setRegimeBindings] = useState([]);
  const [regimeOverview, setRegimeOverview] = useState(null);
  const [regimeDemoResult, setRegimeDemoResult] = useState(null);
  const [bindingForm, setBindingForm] = useState({
    allowed_regimes: "trend_up,range_low_vol",
    blocked_regimes: "panic_dislocation",
    priority: 100,
    gating_policy_version: "1.0",
  });

  const selectedActiveVersion = useMemo(
    () => detail?.versions?.find((item) => item.version_id === detail?.strategy?.active_version_id) || detail?.versions?.[0],
    [detail],
  );

  const lifecycleMap = useMemo(() => detail?.version_lifecycle_map || {}, [detail]);

  const activeFilterChips = useMemo(() => {
    const chips = [];
    if (listFilters.search) chips.push({ key: "search", label: `search:${listFilters.search}` });
    if (listFilters.owner_name) chips.push({ key: "owner_name", label: `owner:${listFilters.owner_name}` });
    if (listFilters.category) chips.push({ key: "category", label: `category:${listFilters.category}` });
    if (listFilters.status_filter) chips.push({ key: "status_filter", label: `status:${listFilters.status_filter}` });
    if (listFilters.lifecycle_state) chips.push({ key: "lifecycle_state", label: `lifecycle:${listFilters.lifecycle_state}` });
    if (listFilters.validation_status) chips.push({ key: "validation_status", label: `validation:${listFilters.validation_status}` });
    if (listFilters.active_only) chips.push({ key: "active_only", label: "active_only:true" });
    if (listFilters.production_only) chips.push({ key: "production_only", label: "production_only:true" });
    selectedTagFilters.forEach((tag) => chips.push({ key: `tag-${tag}`, label: `tag:${tag}` }));
    return chips;
  }, [listFilters, selectedTagFilters]);

  const filteredTimelineItems = useMemo(() => {
    return (timelineItems || []).filter((item) => {
      const action = String(item.action || "").toLowerCase();
      const actor = String(item.actor_user_id || "").toLowerCase();
      const ts = item.timestamp ? new Date(item.timestamp).getTime() : null;
      const fromTs = auditFilters.from ? new Date(auditFilters.from).getTime() : null;
      const toTs = auditFilters.to ? new Date(auditFilters.to).getTime() : null;
      if (auditFilters.eventType && !action.includes(auditFilters.eventType.toLowerCase())) return false;
      if (auditFilters.user && !actor.includes(auditFilters.user.toLowerCase())) return false;
      if (fromTs && ts && ts < fromTs) return false;
      if (toTs && ts && ts > toTs) return false;
      return true;
    });
  }, [auditFilters, timelineItems]);

  const versionEditorSchema = useMemo(
    () => ({
      required: ["momentum_threshold", "base_size", "volatility_guard"],
      defaults: {
        momentum_threshold: 0.1,
        base_size: 0.001,
        volatility_guard: 0.5,
        neutral_threshold: 0.02,
        allow_short: false,
      },
      hints: {
        momentum_threshold: "number > 0",
        base_size: "number > 0",
        volatility_guard: "number > 0",
        neutral_threshold: "number >= 0 (opsiyonel)",
        allow_short: "boolean (opsiyonel)",
      },
    }),
    [],
  );

  const parsedVersionConfig = useMemo(() => {
    try {
      return { value: JSON.parse(versionForm.config_json || "{}"), parseError: null };
    } catch (error) {
      return { value: null, parseError: error?.message || "JSON parse error" };
    }
  }, [versionForm.config_json]);

  const versionEditorIssues = useMemo(() => {
    const issues = [];
    if (parsedVersionConfig.parseError) {
      return [{ field: "config_json", message: parsedVersionConfig.parseError }];
    }
    const payload = parsedVersionConfig.value || {};
    versionEditorSchema.required.forEach((field) => {
      if (!(field in payload)) {
        issues.push({ field, message: `${field} zorunlu` });
      }
    });
    if ("momentum_threshold" in payload && typeof payload.momentum_threshold !== "number") {
      issues.push({ field: "momentum_threshold", message: "number olmalı" });
    }
    if ("base_size" in payload && (typeof payload.base_size !== "number" || payload.base_size <= 0)) {
      issues.push({ field: "base_size", message: "number > 0 olmalı" });
    }
    if ("volatility_guard" in payload && (typeof payload.volatility_guard !== "number" || payload.volatility_guard <= 0)) {
      issues.push({ field: "volatility_guard", message: "number > 0 olmalı" });
    }
    if ("allow_short" in payload && typeof payload.allow_short !== "boolean") {
      issues.push({ field: "allow_short", message: "boolean olmalı" });
    }
    return issues;
  }, [parsedVersionConfig, versionEditorSchema]);

  const versionConfigDiff = useMemo(() => {
    const currentConfig = selectedActiveVersion?.config_json || {};
    const editedConfig = parsedVersionConfig.value || {};
    const keys = Array.from(new Set([...Object.keys(currentConfig), ...Object.keys(editedConfig)])).sort();
    return keys
      .filter((key) => JSON.stringify(currentConfig[key]) !== JSON.stringify(editedConfig[key]))
      .map((key) => ({ field: key, current: currentConfig[key], edited: editedConfig[key] }));
  }, [parsedVersionConfig.value, selectedActiveVersion]);

  const isVersionConfigValid = !parsedVersionConfig.parseError && versionEditorIssues.length === 0;

  const healthStatusBadge = useMemo(() => {
    const score = Number(metricsSummary?.metrics?.version_health_score || 0);
    if (score >= 75) return "GOOD";
    if (score >= 45) return "WARNING";
    return "BAD";
  }, [metricsSummary]);

  const loadStrategies = useCallback(async () => {
    setLoading(true);
    try {
      const params = {
        ...listFilters,
        active_only: Boolean(listFilters.active_only),
        production_only: Boolean(listFilters.production_only),
      };
      delete params.tag;
      Object.keys(params).forEach((key) => {
        if (params[key] === "" || params[key] === null || params[key] === undefined) {
          delete params[key];
        }
      });
      const { data } = await apiClient.get("/strategy-domain/admin/strategies/ops", { params });
      const items = data?.items || [];
      const filteredItems = selectedTagFilters.length
        ? items.filter((item) => selectedTagFilters.every((tag) => (item.tags || []).includes(tag)))
        : items;
      setStrategies(filteredItems);
      if (filteredItems?.length) {
        const hasSelected = filteredItems.some((item) => item.strategy_id === selectedStrategyId);
        if (!hasSelected) {
          setSelectedStrategyId(filteredItems[0].strategy_id);
        }
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Strategy listesi yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, [listFilters, selectedStrategyId, selectedTagFilters]);

  const loadSavedFilters = useCallback(() => {
    try {
      const raw = window.localStorage.getItem("strategy_control_saved_filters");
      if (!raw) {
        setSavedFilters({});
        return;
      }
      const parsed = JSON.parse(raw);
      setSavedFilters(parsed && typeof parsed === "object" ? parsed : {});
    } catch {
      setSavedFilters({});
    }
  }, []);

  const loadFilterOptions = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/strategy-domain/admin/strategies/filter-options");
      setFilterOptions(data || { owner_names: [], categories: [], tags: [] });
    } catch {
      setFilterOptions({ owner_names: [], categories: [], tags: [] });
    }
  }, []);

  const saveCurrentFilterSet = () => {
    const name = savedFilterName.trim();
    if (!name) {
      toast.error("Filtre set adı girin");
      return;
    }
    const next = { ...savedFilters, [name]: listFilters };
    setSavedFilters(next);
    window.localStorage.setItem("strategy_control_saved_filters", JSON.stringify(next));
    toast.success(`Filtre seti kaydedildi: ${name}`);
  };

  const applySavedFilterSet = (name) => {
    const preset = savedFilters[name];
    if (!preset) return;
    setListFilters((prev) => ({ ...prev, ...preset, page: 1 }));
    toast.success(`Saved filter uygulandı: ${name}`);
  };

  const applyRolePreset = (roleKey) => {
    const preset = roleFilterPresets[roleKey];
    if (!preset) return;
    setListFilters((prev) => ({ ...prev, ...preset, page: 1 }));
    toast.success(`Role preset uygulandı: ${roleKey}`);
  };

  const clearAllFilters = () => {
    setListFilters((prev) => ({
      ...prev,
      search: "",
      status_filter: "",
      lifecycle_state: "",
      validation_status: "",
      owner_name: "",
      category: "",
      sort_by: "updated_at",
      sort_order: "desc",
      active_only: false,
      production_only: false,
      page: 1,
    }));
    setSelectedTagFilters([]);
    toast.success("Tüm filtreler temizlendi");
  };

  const loadDetail = useCallback(async (strategyId) => {
    if (!strategyId) return;
    try {
      const { data } = await apiClient.get(`/strategy-domain/admin/strategies/${strategyId}/control-plane`);
      setDetail(data);
      const activeVersion = data?.versions?.find((item) => item.version_id === data?.strategy?.active_version_id) || data?.versions?.[0];
      if (activeVersion) {
        setKernelContextText(JSON.stringify(kernelContextSeed(activeVersion.version_id, activeVersion.version_hash), null, 2));
        setCompareSelection((prev) => ({
          version_a_id: prev.version_a_id || activeVersion.version_id,
          version_b_id: prev.version_b_id || activeVersion.version_id,
        }));
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
    loadSavedFilters();
  }, [loadSavedFilters]);

  useEffect(() => {
    loadFilterOptions();
  }, [loadFilterOptions]);

  useEffect(() => {
    if (selectedStrategyId) {
      loadDetail(selectedStrategyId);
    }
  }, [loadDetail, selectedStrategyId]);

  const createStrategy = async (event) => {
    event.preventDefault();
    try {
      await apiClient.post("/strategy-domain/admin/strategies", {
        name: strategyForm.name,
        code: strategyForm.code,
        description: strategyForm.description,
        owner_name: strategyForm.owner_name || null,
        category: strategyForm.category || "general",
        tags: (strategyForm.tags_text || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
      });
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
    if (!isVersionConfigValid) {
      toast.error("Config geçersiz: field-level hataları düzeltin");
      return;
    }
    try {
      const configJson = parsedVersionConfig.value || {};
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

  const evaluateKernelStandard = async () => {
    try {
      const payload = JSON.parse(kernelContextText);
      const { data } = await apiClient.post("/strategy-domain/admin/kernel/evaluate-standard", payload);
      setStandardDecisionResult(data);
      toast.success("Standard evaluate tamamlandı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Standard evaluate başarısız");
    }
  };

  const validateVersion = async (versionId) => {
    try {
      await apiClient.post(`/strategy-domain/admin/strategies/${selectedStrategyId}/versions/${versionId}/validate`, { force: false });
      toast.success("Version validation tamamlandı");
      await loadDetail(selectedStrategyId);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Validation başarısız");
    }
  };

  const runDryRun = async (versionId) => {
    try {
      const payload = JSON.parse(kernelContextText);
      await apiClient.post(`/strategy-domain/admin/strategies/${selectedStrategyId}/versions/${versionId}/dry-run`, {
        context_snapshot: payload,
      });
      toast.success("Dry-run tamamlandı");
      await loadDetail(selectedStrategyId);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Dry-run başarısız");
    }
  };

  const rollbackVersion = async (versionId) => {
    try {
      await apiClient.post(`/strategy-domain/admin/strategies/${selectedStrategyId}/rollback`, {
        target_version_id: versionId,
        reason: "manual_ui_rollback",
      });
      toast.success("Rollback tamamlandı");
      await loadDetail(selectedStrategyId);
      await loadStrategies();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Rollback başarısız");
    }
  };

  const setRolloutStage = async (versionId, stage) => {
    try {
      await apiClient.post(`/strategy-domain/admin/strategies/${selectedStrategyId}/versions/${versionId}/stage`, {
        rollout_stage: stage,
      });
      toast.success("Rollout stage güncellendi");
      await loadDetail(selectedStrategyId);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Rollout stage güncellenemedi");
    }
  };

  const runVersionDiff = async () => {
    if (!compareSelection.version_a_id || !compareSelection.version_b_id) {
      toast.error("Diff için iki version seçin");
      return;
    }
    try {
      const { data } = await apiClient.post(`/strategy-domain/admin/strategies/${selectedStrategyId}/versions/diff`, {
        from_version_id: compareSelection.version_a_id,
        to_version_id: compareSelection.version_b_id,
      });
      setDiffResult(data);
      toast.success("Version diff üretildi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Diff üretilemedi");
    }
  };

  const replayLastContext = async () => {
    if (!selectedActiveVersion) {
      toast.error("Aktif version yok");
      return;
    }
    try {
      const payload = JSON.parse(kernelContextText);
      const { data } = await apiClient.post("/strategy-domain/admin/kernel/replay", {
        strategy_version_id: selectedActiveVersion.version_id,
        context_snapshot: payload,
      });
      setReplayResult(data);
      toast.success("Replay tamamlandı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Replay başarısız");
    }
  };

  const compareVersions = async () => {
    if (!compareSelection.version_a_id || !compareSelection.version_b_id) {
      toast.error("Compare için version A/B seçin");
      return;
    }
    try {
      const payload = JSON.parse(kernelContextText);
      const { data } = await apiClient.post("/strategy-domain/admin/kernel/compare", {
        version_a_id: compareSelection.version_a_id,
        version_b_id: compareSelection.version_b_id,
        context_snapshot: payload,
      });
      setCompareResult(data);
      toast.success("Version compare tamamlandı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Compare başarısız");
    }
  };

  const loadTimeline = useCallback(async () => {
    if (!selectedStrategyId) return;
    try {
      const { data } = await apiClient.get(`/strategy-domain/admin/strategies/${selectedStrategyId}/audit-history`, {
        params: { limit: 80 },
      });
      setTimelineItems(data?.items || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Audit timeline yüklenemedi");
    }
  }, [selectedStrategyId]);

  const loadRollbackChain = useCallback(async () => {
    if (!selectedStrategyId) return;
    try {
      const { data } = await apiClient.get(`/strategy-domain/admin/strategies/${selectedStrategyId}/rollback-chain`, {
        params: { limit: 100 },
      });
      setRollbackChain(data?.items || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Rollback chain yüklenemedi");
    }
  }, [selectedStrategyId]);

  const exportAuditHistory = async (formatType) => {
    if (!selectedStrategyId) return;
    try {
      const { data } = await apiClient.get(`/strategy-domain/admin/strategies/${selectedStrategyId}/audit-history/export`, {
        params: { format_type: formatType, limit: 2000 },
      });
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `strategy_audit_export_${selectedStrategyId}_${formatType}.json`;
      a.click();
      window.URL.revokeObjectURL(url);
      toast.success(`Audit export hazır: ${formatType.toUpperCase()}`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Audit export başarısız");
    }
  };

  const loadBindingPreview = useCallback(async () => {
    if (!selectedActiveVersion) {
      setBindingPreview(null);
      return;
    }
    try {
      const { data } = await apiClient.get("/strategy-domain/admin/regime/resolved-binding-preview", {
        params: {
          strategy_version_id: selectedActiveVersion.version_id,
          regime_label: "trend_up",
        },
      });
      setBindingPreview(data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Binding preview yüklenemedi");
    }
  }, [selectedActiveVersion]);

  const loadPromotionRequests = useCallback(async () => {
    if (!selectedStrategyId) return;
    try {
      const { data } = await apiClient.get(`/strategy-domain/admin/strategies/${selectedStrategyId}/promotion-requests`, {
        params: { limit: 40 },
      });
      setPromotionRequests(data?.items || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Promotion request listesi yüklenemedi");
    }
  }, [selectedStrategyId]);

  const requestPromoteToProduction = async (versionId) => {
    try {
      await apiClient.post(`/strategy-domain/admin/strategies/${selectedStrategyId}/promote-request`, {
        strategy_version_id: versionId,
        request_note: "UI promote request",
        require_validation: true,
        require_dry_run: true,
        requested_stage: null,
      });
      toast.success("Promote request oluşturuldu");
      await loadPromotionRequests();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Promote request başarısız");
    }
  };

  const approvePromote = async (requestId) => {
    try {
      await apiClient.post(`/strategy-domain/admin/promotion-requests/${requestId}/approve`, { note: "approved_from_ui" });
      toast.success("Promote onaylandı");
      await Promise.all([loadPromotionRequests(), loadDetail(selectedStrategyId), loadStrategies()]);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Promote onayı başarısız");
    }
  };

  const rejectPromote = async (requestId) => {
    try {
      await apiClient.post(`/strategy-domain/admin/promotion-requests/${requestId}/reject`, { note: "rejected_from_ui" });
      toast.success("Promote request reddedildi");
      await loadPromotionRequests();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Promote reject başarısız");
    }
  };

  const runExecutionPreview = async (versionId) => {
    try {
      const payload = JSON.parse(kernelContextText);
      const { data } = await apiClient.post(
        `/strategy-domain/admin/strategies/${selectedStrategyId}/versions/${versionId}/execution-preview`,
        { context_snapshot: payload },
      );
      setExecutionPreviewResult(data);
      toast.success("Execution preview üretildi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Execution preview başarısız");
    }
  };

  const loadVersionObservability = useCallback(async () => {
    if (!selectedStrategyId || !selectedActiveVersion) return;
    try {
      const [metricsRes, trendRes, driftRes, falseRes, readinessRes] = await Promise.all([
        apiClient.get(`/strategy-domain/admin/strategies/${selectedStrategyId}/versions/${selectedActiveVersion.version_id}/metrics`),
        apiClient.get(`/strategy-domain/admin/strategies/${selectedStrategyId}/versions/${selectedActiveVersion.version_id}/metrics-trend`, {
          params: { points: 80 },
        }),
        apiClient.get(`/strategy-domain/admin/strategies/${selectedStrategyId}/versions/${selectedActiveVersion.version_id}/drift-alerts`),
        apiClient.get(`/strategy-domain/admin/strategies/${selectedStrategyId}/versions/${selectedActiveVersion.version_id}/false-signal-report`),
        apiClient.get(`/strategy-domain/admin/strategies/${selectedStrategyId}/versions/${selectedActiveVersion.version_id}/promotion-readiness`),
      ]);
      setMetricsSummary(metricsRes.data || null);
      setMetricsTrend(trendRes.data || null);
      setDriftSummary(driftRes.data || null);
      setFalseSignalSummary(falseRes.data || null);
      setPromotionReadiness(readinessRes.data || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Observability/readiness yüklenemedi");
    }
  }, [selectedActiveVersion, selectedStrategyId]);

  const bulkArchive = async () => {
    if (selectedStrategyIds.length === 0) {
      toast.error("Bulk işlem için strategy seçin");
      return;
    }
    try {
      const { data } = await apiClient.post("/strategy-domain/admin/strategies/bulk/archive", { strategy_ids: selectedStrategyIds });
      setBulkActionSummary({ action: "archive", payload: data });
      toast.success("Bulk archive tamamlandı");
      setSelectedStrategyIds([]);
      await loadStrategies();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bulk archive başarısız");
    }
  };

  const bulkValidate = async () => {
    if (selectedStrategyIds.length === 0) {
      toast.error("Bulk işlem için strategy seçin");
      return;
    }
    try {
      const { data } = await apiClient.post("/strategy-domain/admin/strategies/bulk/validate", { strategy_ids: selectedStrategyIds });
      setBulkActionSummary({ action: "validate", payload: data });
      toast.success("Bulk validate tamamlandı");
      await Promise.all([loadStrategies(), loadDetail(selectedStrategyId)]);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bulk validate başarısız");
    }
  };

  const bulkDryRun = async () => {
    if (selectedStrategyIds.length === 0) {
      toast.error("Bulk işlem için strategy seçin");
      return;
    }
    try {
      const payload = JSON.parse(kernelContextText);
      const { data } = await apiClient.post("/strategy-domain/admin/strategies/bulk/dry-run", {
        strategy_ids: selectedStrategyIds,
        context_snapshot: payload,
      });
      setBulkActionSummary({ action: "dry-run", payload: data });
      toast.success("Bulk dry-run tamamlandı");
      await Promise.all([loadStrategies(), loadDetail(selectedStrategyId)]);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bulk dry-run başarısız");
    }
  };

  const bulkTag = async () => {
    if (selectedStrategyIds.length === 0) {
      toast.error("Bulk işlem için strategy seçin");
      return;
    }
    try {
      const { data } = await apiClient.post("/strategy-domain/admin/strategies/bulk/tag", {
        strategy_ids: selectedStrategyIds,
        category: strategyForm.category || null,
        tags: (strategyForm.tags_text || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        owner_name: strategyForm.owner_name || null,
      });
      setBulkActionSummary({ action: "tag", payload: data });
      toast.success("Bulk tag/category güncellendi");
      await loadStrategies();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bulk tag başarısız");
    }
  };

  const bulkAuditExport = async () => {
    if (selectedStrategyIds.length === 0) {
      toast.error("Bulk işlem için strategy seçin");
      return;
    }
    try {
      const { data } = await apiClient.post("/strategy-domain/admin/strategies/bulk/audit-snapshot", {
        strategy_ids: selectedStrategyIds,
        format_type: "json",
        limit_per_strategy: 200,
      });
      toast.success(`Bulk audit snapshot hazır (${data?.strategy_count || 0} strategy)`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bulk audit export başarısız");
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

  const loadRegimeData = useCallback(async () => {
    if (!selectedStrategyId) return;
    try {
      const [overviewRes, bindingsRes] = await Promise.all([
        apiClient.get(`/strategy-domain/admin/regime/overview/${selectedStrategyId}`),
        selectedActiveVersion
          ? apiClient.get(`/strategy-domain/admin/regime/bindings/${selectedActiveVersion.version_id}`)
          : Promise.resolve({ data: [] }),
      ]);
      setRegimeOverview(overviewRes.data || null);
      setRegimeBindings(bindingsRes.data || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Regime verisi yüklenemedi");
    }
  }, [selectedStrategyId, selectedActiveVersion]);

  useEffect(() => {
    loadRuntimeViews();
  }, [loadRuntimeViews]);

  useEffect(() => {
    loadRegimeData();
  }, [loadRegimeData]);

  useEffect(() => {
    loadTimeline();
  }, [loadTimeline]);

  useEffect(() => {
    loadRollbackChain();
  }, [loadRollbackChain]);

  useEffect(() => {
    loadBindingPreview();
  }, [loadBindingPreview]);

  useEffect(() => {
    loadPromotionRequests();
  }, [loadPromotionRequests]);

  useEffect(() => {
    loadVersionObservability();
  }, [loadVersionObservability]);

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

  const createRegimeBinding = async () => {
    if (!selectedActiveVersion) {
      toast.error("Aktif strategy version seçilmedi");
      return;
    }
    const normalize = (value) =>
      value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
    try {
      const payload = {
        strategy_version_id: selectedActiveVersion.version_id,
        allowed_regimes: normalize(bindingForm.allowed_regimes || ""),
        blocked_regimes: normalize(bindingForm.blocked_regimes || ""),
        priority: Number(bindingForm.priority || 100),
        gating_policy_version: bindingForm.gating_policy_version || "1.0",
      };
      await apiClient.post("/strategy-domain/admin/regime/bindings", payload);
      toast.success("Regime binding oluşturuldu");
      await loadRegimeData();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Regime binding oluşturulamadı");
    }
  };

  const seedDemoBinding = async () => {
    if (!selectedActiveVersion) {
      toast.error("Aktif strategy version seçilmedi");
      return;
    }
    const payload = {
      strategy_version_id: selectedActiveVersion.version_id,
      allowed_regimes: ["trend_up", "range_low_vol"],
      blocked_regimes: ["panic_dislocation"],
      priority: 100,
      gating_policy_version: "1.0",
    };
    try {
      setBindingForm((prev) => ({
        ...prev,
        allowed_regimes: "trend_up,range_low_vol",
        blocked_regimes: "panic_dislocation",
      }));
      await apiClient.post("/strategy-domain/admin/regime/bindings", payload);
      toast.success("Demo binding eklendi");
      await loadRegimeData();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Demo binding oluşturulamadı");
    }
  };

  const runRegimeDemo = async (variant) => {
    if (!selectedActiveVersion) {
      toast.error("Aktif strategy version seçilmedi");
      return;
    }
    try {
      const contextPayload = buildRegimeContext(
        selectedActiveVersion.version_id,
        selectedActiveVersion.version_hash,
        variant,
      );
      const { data } = await apiClient.post("/strategy-domain/admin/regime/evaluate", contextPayload);
      setRegimeDemoResult({ variant, ...data });
      toast.success("Regime gating demo çalıştı");
      await loadRegimeData();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Regime demo başarısız");
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
          <Input placeholder="owner_name" value={strategyForm.owner_name} onChange={(e) => setStrategyForm((prev) => ({ ...prev, owner_name: e.target.value }))} data-testid="admin-strategy-create-owner-input" />
          <Input placeholder="category" value={strategyForm.category} onChange={(e) => setStrategyForm((prev) => ({ ...prev, category: e.target.value }))} data-testid="admin-strategy-create-category-input" />
          <Input placeholder="tags (comma separated)" value={strategyForm.tags_text} onChange={(e) => setStrategyForm((prev) => ({ ...prev, tags_text: e.target.value }))} data-testid="admin-strategy-create-tags-input" />
          <Button className="bg-orange-500 text-black hover:bg-orange-600" data-testid="admin-strategy-create-submit-button">Create Definition</Button>
        </form>

        <form className="space-y-2 border border-slate-800 bg-slate-900 p-4" onSubmit={createVersion} data-testid="admin-strategy-version-create-form">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-version-title">Create StrategyVersion</p>
          <Input placeholder="config schema version" value={versionForm.config_schema_version} onChange={(e) => setVersionForm((prev) => ({ ...prev, config_schema_version: e.target.value }))} data-testid="admin-strategy-version-schema-input" />
          <div className="grid gap-3 xl:grid-cols-2" data-testid="admin-strategy-version-editor-grid">
            <div className="space-y-2" data-testid="admin-strategy-version-editor-main">
              <div className={`rounded border p-2 text-xs ${isVersionConfigValid ? "border-emerald-600 text-emerald-300" : "border-red-600 text-red-300"}`} data-testid="admin-strategy-version-validation-summary-banner">
                {isVersionConfigValid ? "Validation summary: PASS" : "Validation summary: FAIL"}
              </div>
              <textarea
                className={`h-44 w-full border bg-slate-950 p-2 text-sm ${isVersionConfigValid ? "border-slate-700" : "border-red-500"}`}
                value={versionForm.config_json}
                onChange={(e) => setVersionForm((prev) => ({ ...prev, config_json: e.target.value }))}
                data-testid="admin-strategy-version-config-textarea"
              />
              {versionEditorIssues.length > 0 && (
                <div className="space-y-1 border border-red-700 p-2 text-xs" data-testid="admin-strategy-version-error-list-panel">
                  {versionEditorIssues.map((issue, idx) => (
                    <p key={`${issue.field}-${idx}`} className="text-red-300" data-testid={`admin-strategy-version-error-item-${idx}`}>
                      {issue.field}: {issue.message}
                    </p>
                  ))}
                </div>
              )}
              <div className="flex flex-wrap gap-2" data-testid="admin-strategy-version-editor-actions-row">
                <Button type="button" variant="outline" className="border-slate-500 text-slate-100" onClick={() => setShowConfigDiffMode((prev) => !prev)} data-testid="admin-strategy-version-diff-toggle-button">
                  Diff Mode: {String(showConfigDiffMode)}
                </Button>
              </div>
              {showConfigDiffMode && (
                <div className="space-y-1 border border-slate-700 p-2 text-xs" data-testid="admin-strategy-version-diff-panel">
                  {versionConfigDiff.length === 0 && <p data-testid="admin-strategy-version-diff-empty">Fark bulunamadı.</p>}
                  {versionConfigDiff.slice(0, 20).map((item, idx) => (
                    <p key={`${item.field}-${idx}`} data-testid={`admin-strategy-version-diff-item-${idx}`}>
                      {item.field}: {JSON.stringify(item.current)} → {JSON.stringify(item.edited)}
                    </p>
                  ))}
                </div>
              )}
            </div>

            <div className="space-y-2 border border-slate-700 p-2 text-xs" data-testid="admin-strategy-version-schema-hint-panel">
              <p className="uppercase tracking-wider text-slate-400" data-testid="admin-strategy-version-schema-hint-title">Schema Hints</p>
              <p data-testid="admin-strategy-version-required-fields">required: {versionEditorSchema.required.join(", ")}</p>
              <div className="space-y-1" data-testid="admin-strategy-version-hints-list">
                {Object.entries(versionEditorSchema.hints).map(([field, hint]) => (
                  <p key={field} data-testid={`admin-strategy-version-hint-${field}`}>{field}: {hint}</p>
                ))}
              </div>
              <div className="space-y-1" data-testid="admin-strategy-version-defaults-list">
                {Object.entries(versionEditorSchema.defaults).map(([field, value]) => (
                  <p key={field} data-testid={`admin-strategy-version-default-${field}`}>{field} default: {JSON.stringify(value)}</p>
                ))}
              </div>
            </div>
          </div>
          <Button className="bg-orange-500 text-black hover:bg-orange-600" disabled={!selectedStrategyId || !isVersionConfigValid} data-testid="admin-strategy-version-submit-button">Create Version</Button>
        </form>
      </div>

      <div className="grid gap-4 xl:grid-cols-3" data-testid="admin-strategies-main-grid">
        <div className="border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategies-list-panel">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategies-list-title">Strategy List</p>
          <div className="mt-2 grid gap-2" data-testid="admin-strategies-filter-toolbar">
            <Input
              placeholder="search code/name/owner"
              value={listFilters.search}
              onChange={(e) => setListFilters((prev) => ({ ...prev, search: e.target.value, page: 1 }))}
              data-testid="admin-strategies-filter-search-input"
            />
            <div className="grid grid-cols-2 gap-2">
              <Input
                placeholder="category"
                value={listFilters.category}
                onChange={(e) => setListFilters((prev) => ({ ...prev, category: e.target.value, page: 1 }))}
                data-testid="admin-strategies-filter-category-input"
                list="admin-strategies-category-options"
              />
              <datalist id="admin-strategies-category-options">
                {(filterOptions.categories || []).map((item) => (
                  <option key={item} value={item} />
                ))}
              </datalist>
              <Input
                placeholder="lifecycle_state"
                value={listFilters.lifecycle_state}
                onChange={(e) => setListFilters((prev) => ({ ...prev, lifecycle_state: e.target.value, page: 1 }))}
                data-testid="admin-strategies-filter-lifecycle-input"
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Input
                placeholder="validation_status"
                value={listFilters.validation_status}
                onChange={(e) => setListFilters((prev) => ({ ...prev, validation_status: e.target.value, page: 1 }))}
                data-testid="admin-strategies-filter-validation-input"
              />
              <Input
                placeholder="status"
                value={listFilters.status_filter}
                onChange={(e) => setListFilters((prev) => ({ ...prev, status_filter: e.target.value, page: 1 }))}
                data-testid="admin-strategies-filter-status-input"
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Input
                placeholder="owner filter"
                value={listFilters.owner_name}
                onChange={(e) => setListFilters((prev) => ({ ...prev, owner_name: e.target.value, page: 1 }))}
                data-testid="admin-strategies-filter-owner-input"
                list="admin-strategies-owner-options"
              />
              <datalist id="admin-strategies-owner-options">
                {(filterOptions.owner_names || []).map((item) => (
                  <option key={item} value={item} />
                ))}
              </datalist>
              <Input
                placeholder="tag search"
                value={strategyForm.tags_text}
                onChange={(e) => setStrategyForm((prev) => ({ ...prev, tags_text: e.target.value }))}
                data-testid="admin-strategies-filter-tag-search-input"
              />
            </div>
            <div className="flex flex-wrap gap-2" data-testid="admin-strategies-filter-tag-multiselect">
              {(filterOptions.tags || [])
                .filter((tag) => (strategyForm.tags_text || "") ? tag.includes(strategyForm.tags_text.toLowerCase()) : true)
                .slice(0, 20)
                .map((tag) => {
                  const selected = selectedTagFilters.includes(tag);
                  return (
                    <Button
                      key={tag}
                      type="button"
                      variant="outline"
                      className={selected ? "border-orange-500 text-orange-200" : "border-slate-600 text-slate-200"}
                      onClick={() => {
                        setSelectedTagFilters((prev) =>
                          prev.includes(tag) ? prev.filter((item) => item !== tag) : [...prev, tag],
                        );
                      }}
                      data-testid={`admin-strategies-filter-tag-toggle-${tag}`}
                    >
                      {tag}
                    </Button>
                  );
                })}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Input
                placeholder="sort_by"
                value={listFilters.sort_by}
                onChange={(e) => setListFilters((prev) => ({ ...prev, sort_by: e.target.value }))}
                data-testid="admin-strategies-filter-sort-by-input"
              />
              <Input
                placeholder="sort_order asc/desc"
                value={listFilters.sort_order}
                onChange={(e) => setListFilters((prev) => ({ ...prev, sort_order: e.target.value }))}
                data-testid="admin-strategies-filter-sort-order-input"
              />
            </div>
            <div className="flex flex-wrap gap-2" data-testid="admin-strategies-filter-actions-row">
              <Button variant="outline" className="border-slate-500 text-slate-100" onClick={() => setListFilters((prev) => ({ ...prev, active_only: !prev.active_only }))} data-testid="admin-strategies-filter-active-toggle-button">active_only: {String(Boolean(listFilters.active_only))}</Button>
              <Button variant="outline" className="border-slate-500 text-slate-100" onClick={() => setListFilters((prev) => ({ ...prev, production_only: !prev.production_only }))} data-testid="admin-strategies-filter-production-toggle-button">production_only: {String(Boolean(listFilters.production_only))}</Button>
              <Button variant="outline" className="border-slate-500 text-slate-100" onClick={loadStrategies} data-testid="admin-strategies-filter-apply-button">Apply Filters</Button>
              <Button variant="outline" className="border-sky-500 text-sky-200" onClick={() => applyRolePreset("desk")} data-testid="admin-strategies-role-preset-desk-button">Preset: Desk</Button>
              <Button variant="outline" className="border-sky-500 text-sky-200" onClick={() => applyRolePreset("ops")} data-testid="admin-strategies-role-preset-ops-button">Preset: Ops</Button>
              <Button variant="outline" className="border-sky-500 text-sky-200" onClick={() => applyRolePreset("admin")} data-testid="admin-strategies-role-preset-admin-button">Preset: Admin</Button>
              <Button variant="outline" className="border-red-500 text-red-200" onClick={clearAllFilters} data-testid="admin-strategies-filter-clear-all-button">Clear All</Button>
            </div>
            {activeFilterChips.length > 0 && (
              <div className="flex flex-wrap gap-2" data-testid="admin-strategies-active-filter-chips">
                {activeFilterChips.map((chip) => (
                  <span key={chip.key} className="rounded-full border border-orange-500 px-2 py-1 text-[10px] uppercase tracking-wide text-orange-200" data-testid={`admin-strategies-filter-chip-${chip.key}`}>
                    {chip.label}
                  </span>
                ))}
              </div>
            )}
            <div className="grid grid-cols-2 gap-2" data-testid="admin-strategies-saved-filter-row">
              <Input
                placeholder="saved filter name"
                value={savedFilterName}
                onChange={(e) => setSavedFilterName(e.target.value)}
                data-testid="admin-strategies-saved-filter-name-input"
              />
              <Button variant="outline" className="border-slate-500 text-slate-100" onClick={saveCurrentFilterSet} data-testid="admin-strategies-saved-filter-save-button">Save Current Filter</Button>
            </div>
            {Object.keys(savedFilters).length > 0 && (
              <div className="flex flex-wrap gap-2" data-testid="admin-strategies-saved-filter-buttons">
                {Object.keys(savedFilters).map((key) => (
                  <Button
                    key={key}
                    variant="outline"
                    className="border-slate-500 text-slate-100"
                    onClick={() => applySavedFilterSet(key)}
                    data-testid={`admin-strategies-saved-filter-apply-${key}`}
                  >
                    {key}
                  </Button>
                ))}
              </div>
            )}
            <div className="flex flex-wrap gap-2" data-testid="admin-strategies-bulk-actions-row">
              <Button variant="outline" className="border-red-500 text-red-200" onClick={bulkArchive} data-testid="admin-strategies-bulk-archive-button">Bulk Archive</Button>
              <Button variant="outline" className="border-slate-500 text-slate-100" onClick={bulkValidate} data-testid="admin-strategies-bulk-validate-button">Bulk Validate</Button>
              <Button variant="outline" className="border-slate-500 text-slate-100" onClick={bulkDryRun} data-testid="admin-strategies-bulk-dry-run-button">Bulk Dry-Run</Button>
              <Button variant="outline" className="border-slate-500 text-slate-100" onClick={bulkTag} data-testid="admin-strategies-bulk-tag-button">Bulk Tag/Category</Button>
              <Button variant="outline" className="border-slate-500 text-slate-100" onClick={bulkAuditExport} data-testid="admin-strategies-bulk-audit-export-button">Bulk Audit Snapshot</Button>
            </div>
            {bulkActionSummary && (
              <div className="rounded border border-slate-700 p-2 text-xs" data-testid="admin-strategies-bulk-result-panel">
                <p data-testid="admin-strategies-bulk-result-action">action: {bulkActionSummary.action}</p>
                <p data-testid="admin-strategies-bulk-result-success">success: {bulkActionSummary.payload?.success_count ?? bulkActionSummary.payload?.updated_count ?? 0}</p>
                <p data-testid="admin-strategies-bulk-result-fail">fail: {bulkActionSummary.payload?.failed_count ?? 0}</p>
                {!!(bulkActionSummary.payload?.failed || []).length && (
                  <div className="text-red-300" data-testid="admin-strategies-bulk-result-fail-list">
                    {(bulkActionSummary.payload.failed || []).slice(0, 5).map((item, idx) => (
                      <p key={`${item.strategy_id}-${idx}`}>{item.strategy_id}: {item.error}</p>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
          {loading && <p className="mt-2 text-sm text-slate-400" data-testid="admin-strategies-loading-text">Yükleniyor...</p>}
          <div className="mt-2 flex items-center gap-2 text-xs" data-testid="admin-strategies-select-all-row">
            <input
              type="checkbox"
              checked={strategies.length > 0 && selectedStrategyIds.length === strategies.length}
              onChange={(e) => {
                const checked = e.target.checked;
                setSelectedStrategyIds(checked ? strategies.map((item) => item.strategy_id) : []);
              }}
              data-testid="admin-strategies-select-all-checkbox"
            />
            <span data-testid="admin-strategies-select-all-label">Select all visible</span>
          </div>
          <div className="mt-3 space-y-2" data-testid="admin-strategies-list">
            {strategies.map((item) => (
              <div key={item.strategy_id} className={`w-full border p-2 text-left text-sm ${selectedStrategyId === item.strategy_id ? "border-orange-500 bg-orange-500/10" : "border-slate-700"}`} data-testid={`admin-strategy-select-row-${item.strategy_id}`}>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={selectedStrategyIds.includes(item.strategy_id)}
                    onChange={(e) => {
                      const checked = e.target.checked;
                      setSelectedStrategyIds((prev) => (checked ? [...new Set([...prev, item.strategy_id])] : prev.filter((id) => id !== item.strategy_id)));
                    }}
                    data-testid={`admin-strategy-select-checkbox-${item.strategy_id}`}
                  />
                  <button
                    type="button"
                    onClick={() => setSelectedStrategyId(item.strategy_id)}
                    className="flex-1 text-left"
                    data-testid={`admin-strategy-select-button-${item.strategy_id}`}
                  >
                    <p data-testid={`admin-strategy-item-code-${item.strategy_id}`}>{item.code}</p>
                    <p className="text-xs text-slate-400" data-testid={`admin-strategy-item-status-${item.strategy_id}`}>{item.status}</p>
                    <p className="text-xs text-slate-400" data-testid={`admin-strategy-item-owner-${item.strategy_id}`}>owner: {item.owner_name || "-"}</p>
                    <p className="text-xs text-slate-400" data-testid={`admin-strategy-item-category-${item.strategy_id}`}>category: {item.category || "-"}</p>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-3 border border-slate-800 bg-slate-900 p-4 xl:col-span-2" data-testid="admin-strategy-detail-panel">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-detail-title">Strategy Detail</p>
          {detail?.strategy && (
            <div className="border border-slate-700 p-3" data-testid="admin-strategy-detail-card">
              <p className="text-sm" data-testid="admin-strategy-detail-code">code: {detail.strategy.code}</p>
              <p className="text-sm" data-testid="admin-strategy-detail-status">status: {detail.strategy.status}</p>
              <p className="text-sm" data-testid="admin-strategy-detail-owner">owner: {detail.strategy.owner_name || "-"}</p>
              <p className="text-sm" data-testid="admin-strategy-detail-category">category: {detail.strategy.category || "-"}</p>
              <p className="text-xs text-slate-400" data-testid="admin-strategy-detail-tags">tags: {(detail.strategy.tags || []).join(", ") || "-"}</p>
              <p className="text-sm" data-testid="admin-strategy-detail-active-version">active_version_id: {detail.strategy.active_version_id || "-"}</p>
              <Button variant="outline" className="mt-2 border-red-500 text-red-300" onClick={archiveStrategy} data-testid="admin-strategy-archive-button">Archive Strategy</Button>
            </div>
          )}

          <div className="space-y-2" data-testid="admin-strategy-versions-list">
            {(detail?.versions || []).map((item) => (
              <div key={item.version_id} className="space-y-2 border border-slate-700 p-3" data-testid={`admin-strategy-version-row-${item.version_id}`}>
                <p className="text-sm" data-testid={`admin-strategy-version-number-${item.version_id}`}>v{item.version_number} · schema={item.config_schema_version}</p>
                <p className="text-xs text-slate-400 break-all" data-testid={`admin-strategy-version-hash-${item.version_id}`}>hash: {item.version_hash}</p>
                <div className="flex flex-wrap gap-2 text-xs" data-testid={`admin-strategy-version-lifecycle-badges-${item.version_id}`}>
                  <span className="border border-slate-700 px-2 py-1" data-testid={`admin-strategy-version-lifecycle-state-${item.version_id}`}>
                    state: {lifecycleMap[item.version_id]?.lifecycle_state || "draft"}
                  </span>
                  <span className="border border-slate-700 px-2 py-1" data-testid={`admin-strategy-version-validation-status-${item.version_id}`}>
                    validation: {lifecycleMap[item.version_id]?.validation_status || "pending"}
                  </span>
                  <span className="border border-slate-700 px-2 py-1" data-testid={`admin-strategy-version-dry-run-status-${item.version_id}`}>
                    dry_run: {lifecycleMap[item.version_id]?.dry_run_status || "pending"}
                  </span>
                  <span className="border border-slate-700 px-2 py-1" data-testid={`admin-strategy-version-production-status-${item.version_id}`}>
                    production: {String(Boolean(lifecycleMap[item.version_id]?.is_production))}
                  </span>
                </div>
                <div className="flex flex-wrap gap-2" data-testid={`admin-strategy-version-actions-${item.version_id}`}>
                  <Button variant="outline" className="border-slate-500 text-slate-100" onClick={() => validateVersion(item.version_id)} data-testid={`admin-strategy-version-validate-button-${item.version_id}`}>Validate</Button>
                  <Button variant="outline" className="border-slate-500 text-slate-100" onClick={() => runDryRun(item.version_id)} data-testid={`admin-strategy-version-dry-run-button-${item.version_id}`}>Dry-Run</Button>
                  <Button className="bg-orange-500 text-black hover:bg-orange-600" onClick={() => activateVersion(item.version_id)} data-testid={`admin-strategy-version-activate-button-${item.version_id}`}>Activate</Button>
                  <Button variant="outline" className="border-amber-500 text-amber-200" onClick={() => rollbackVersion(item.version_id)} data-testid={`admin-strategy-version-rollback-button-${item.version_id}`}>Rollback</Button>
                  <Button variant="outline" className="border-emerald-500 text-emerald-200" onClick={() => runExecutionPreview(item.version_id)} data-testid={`admin-strategy-version-execution-preview-button-${item.version_id}`}>Execution Preview</Button>
                  <Button
                    variant="outline"
                    className="border-blue-500 text-blue-200"
                    onClick={() => requestPromoteToProduction(item.version_id)}
                    title={
                      lifecycleMap[item.version_id]?.validation_status !== "PASS"
                        ? "Validation PASS değil"
                        : lifecycleMap[item.version_id]?.compatibility_status !== "PASS"
                          ? "Compatibility PASS değil"
                          : lifecycleMap[item.version_id]?.dry_run_status !== "PASS"
                            ? "Dry-run PASS değil"
                            : "Promote request oluşturulabilir"
                    }
                    disabled={
                      lifecycleMap[item.version_id]?.validation_status !== "PASS" ||
                      lifecycleMap[item.version_id]?.compatibility_status !== "PASS" ||
                      lifecycleMap[item.version_id]?.dry_run_status !== "PASS"
                    }
                    data-testid={`admin-strategy-version-promote-request-button-${item.version_id}`}
                  >
                    Promote Request
                  </Button>
                  <Button variant="outline" className="border-fuchsia-500 text-fuchsia-200" onClick={() => setRolloutStage(item.version_id, "shadow")} data-testid={`admin-strategy-version-shadow-button-${item.version_id}`}>Stage: Shadow</Button>
                  <Button variant="outline" className="border-fuchsia-500 text-fuchsia-200" onClick={() => setRolloutStage(item.version_id, "canary")} data-testid={`admin-strategy-version-canary-button-${item.version_id}`}>Stage: Canary</Button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-kernel-evaluate-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-kernel-evaluate-title">Deterministic Kernel Evaluate</p>
        <textarea className="h-52 w-full border border-slate-700 bg-slate-950 p-2 text-sm" value={kernelContextText} onChange={(e) => setKernelContextText(e.target.value)} data-testid="admin-kernel-context-textarea" />
        <div className="flex flex-wrap gap-2" data-testid="admin-kernel-evaluate-actions">
          <Button className="bg-orange-500 text-black hover:bg-orange-600" onClick={evaluateKernel} data-testid="admin-kernel-evaluate-button">Evaluate Context</Button>
          <Button variant="outline" className="border-orange-500 text-orange-200" onClick={evaluateKernelStandard} data-testid="admin-kernel-evaluate-standard-button">Evaluate Standard</Button>
          <Button variant="outline" className="border-slate-500 text-slate-100" onClick={replayLastContext} data-testid="admin-kernel-replay-button">Replay Last Context</Button>
          <Button variant="outline" className="border-slate-500 text-slate-100" onClick={compareVersions} data-testid="admin-kernel-compare-button">Compare A/B</Button>
        </div>
        <div className="grid gap-2 md:grid-cols-2" data-testid="admin-version-compare-selectors">
          <Input
            placeholder="version_a_id"
            value={compareSelection.version_a_id}
            onChange={(e) => setCompareSelection((prev) => ({ ...prev, version_a_id: e.target.value }))}
            data-testid="admin-version-compare-a-input"
          />
          <Input
            placeholder="version_b_id"
            value={compareSelection.version_b_id}
            onChange={(e) => setCompareSelection((prev) => ({ ...prev, version_b_id: e.target.value }))}
            data-testid="admin-version-compare-b-input"
          />
        </div>
        <div className="flex flex-wrap gap-2" data-testid="admin-version-diff-actions">
          <Button variant="outline" className="border-slate-500 text-slate-100" onClick={runVersionDiff} data-testid="admin-version-diff-run-button">Run Version Diff</Button>
        </div>
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

        {standardDecisionResult && (
          <div className="border border-slate-700 p-3" data-testid="admin-kernel-standard-result-card">
            <p className="text-sm" data-testid="admin-kernel-standard-result">result: {standardDecisionResult.result || standardDecisionResult.PASS_BLOCK}</p>
            <p className="text-sm" data-testid="admin-kernel-standard-score">score: {standardDecisionResult.score ?? standardDecisionResult.SCORE}</p>
            <p className="text-xs text-slate-400 break-all" data-testid="admin-kernel-standard-reasons">
              reason_codes: {(standardDecisionResult.reason_codes || standardDecisionResult.REASON_CODES || []).join(", ")}
            </p>
            <p className="text-xs text-slate-400 break-all" data-testid="admin-kernel-standard-decision-hash">
              decision_hash: {standardDecisionResult.decision_hash || standardDecisionResult.DECISION_HASH}
            </p>
          </div>
        )}

        {replayResult && (
          <div className="border border-slate-700 p-3" data-testid="admin-kernel-replay-result-card">
            <p className="text-sm" data-testid="admin-kernel-replay-deterministic">deterministic: {String(Boolean(replayResult.deterministic))}</p>
            <p className="text-xs text-slate-400 break-all" data-testid="admin-kernel-replay-hash">
              replay_hash: {replayResult?.output?.decision_hash || replayResult?.decision_hash_recheck}
            </p>
          </div>
        )}

        {compareResult && (
          <div className="border border-slate-700 p-3" data-testid="admin-kernel-compare-result-card">
            <p className="text-sm" data-testid="admin-kernel-compare-action-changed">action_changed: {String(Boolean(compareResult?.output_diff?.action_changed))}</p>
            <p className="text-sm" data-testid="admin-kernel-compare-result-changed">result_changed: {String(Boolean(compareResult?.output_diff?.result_changed))}</p>
            <p className="text-sm" data-testid="admin-kernel-compare-score-delta">score_delta: {compareResult?.output_diff?.score_delta}</p>
          </div>
        )}

        {diffResult && (
          <div className="border border-slate-700 p-3" data-testid="admin-version-diff-result-card">
            <p className="text-sm" data-testid="admin-version-diff-count">difference_count: {diffResult?.difference_count}</p>
            <div className="space-y-1 text-xs text-slate-300" data-testid="admin-version-diff-list">
              {(diffResult?.differences || []).slice(0, 10).map((item, idx) => (
                <p key={`${item.field}-${idx}`} data-testid={`admin-version-diff-item-${idx}`}>
                  {item.field}: {JSON.stringify(item.from)} → {JSON.stringify(item.to)}
                </p>
              ))}
            </div>
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

      <div className="grid gap-4 xl:grid-cols-2" data-testid="admin-strategy-explainability-grid">
        <div className="space-y-2 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-execution-preview-panel">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-execution-preview-title">Execution Preview</p>
          {executionPreviewResult ? (
            <div className="space-y-2 text-xs" data-testid="admin-strategy-execution-preview-content">
              <p data-testid="admin-strategy-execution-preview-signal">Signal: {executionPreviewResult?.explainability_trace?.selection?.signal || "-"}</p>
              <p data-testid="admin-strategy-execution-preview-action">Decision/Action: {executionPreviewResult?.explainability_trace?.selection?.selected_action || "-"}</p>
              <p data-testid="admin-strategy-execution-preview-intent">Execution intent: {executionPreviewResult?.execution_intent?.intent_id || "none"}</p>
              <p data-testid="admin-strategy-execution-preview-order">Order preview: {executionPreviewResult?.order_preview?.side || "-"} / notional {executionPreviewResult?.order_preview?.estimated_notional ?? "-"}</p>
              <p data-testid="admin-strategy-execution-preview-capital">Capital impact: {executionPreviewResult?.capital_impact?.allocation_pct ?? "-"}%</p>
              <p data-testid="admin-strategy-execution-preview-risk">Risk checks: {(executionPreviewResult?.risk_checks || []).map((item) => `${item.check}:${item.status}`).join(", ")}</p>
              <p className="text-slate-400" data-testid="admin-strategy-execution-preview-blocked-reasons">Block reason: {(executionPreviewResult?.blocked_reasons || []).join(", ") || "-"}</p>
              <Button type="button" variant="outline" className="border-slate-500 text-slate-100" onClick={() => setShowExecutionExplain((prev) => !prev)} data-testid="admin-strategy-execution-explain-toggle-button">
                Explain: {String(showExecutionExplain)}
              </Button>
              {showExecutionExplain && (
                <div className="space-y-1 border border-slate-700 p-2" data-testid="admin-strategy-execution-explain-trace-panel">
                  <p data-testid="admin-strategy-execution-explain-step-1">1) Signal üretildi: {executionPreviewResult?.explainability_trace?.selection?.signal || "-"}</p>
                  <p data-testid="admin-strategy-execution-explain-step-2">2) Decision alındı: {(executionPreviewResult?.decision || {}).result || "-"}</p>
                  <p data-testid="admin-strategy-execution-explain-step-3">3) Intent map edildi: {executionPreviewResult?.execution_intent?.intent_id || "none"}</p>
                  <p data-testid="admin-strategy-execution-explain-step-4">4) Risk checks çalıştı: {(executionPreviewResult?.risk_checks || []).length}</p>
                  <p data-testid="admin-strategy-execution-explain-step-5">5) Capital impact hesaplandı: {executionPreviewResult?.capital_impact?.allocation_pct ?? "-"}%</p>
                </div>
              )}
            </div>
          ) : (
            <p className="text-xs text-slate-400" data-testid="admin-strategy-execution-preview-empty">Version aksiyonlarından “Execution Preview” çalıştırın.</p>
          )}
        </div>

        <div className="space-y-2 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-promotion-readiness-panel">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-promotion-readiness-title">One-click Promote Checklist</p>
          {promotionReadiness ? (
            <div className="space-y-2 text-xs" data-testid="admin-strategy-promotion-readiness-content">
              {(promotionReadiness.checklist || []).map((item) => (
                <p key={item.key} data-testid={`admin-strategy-promotion-readiness-item-${item.key}`}>
                  {item.key}: {item.status} ({item.pass ? "PASS" : "FAIL"})
                </p>
              ))}
              <p data-testid="admin-strategy-promotion-readiness-ready">ready_for_production: {String(Boolean(promotionReadiness.ready_for_production))}</p>
              {Boolean((promotionReadiness.blockers || []).length) && (
                <div className="text-red-300" data-testid="admin-strategy-promotion-readiness-blockers">
                  {(promotionReadiness.blockers || []).map((item, idx) => (
                    <p key={`${item}-${idx}`}>{item}</p>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <p className="text-xs text-slate-400" data-testid="admin-strategy-promotion-readiness-empty">Readiness verisi yok.</p>
          )}
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2" data-testid="admin-strategy-observability-grid">
        <div className="space-y-2 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-metrics-summary-panel">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-metrics-summary-title">Version Metrics Summary</p>
          <div className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${healthStatusBadge === "GOOD" ? "bg-emerald-500/20 text-emerald-300" : healthStatusBadge === "WARNING" ? "bg-amber-500/20 text-amber-300" : "bg-red-500/20 text-red-300"}`} data-testid="admin-strategy-health-status-badge">
            HEALTH: {healthStatusBadge}
          </div>
          {metricsSummary ? (
            <div className="space-y-1 text-xs" data-testid="admin-strategy-metrics-summary-content">
              <p data-testid="admin-strategy-metrics-hit-rate">hit_rate: {metricsSummary?.metrics?.hit_rate ?? "-"}</p>
              <p data-testid="admin-strategy-metrics-block-rate">block_reject_rate: {metricsSummary?.metrics?.block_reject_rate ?? "-"}</p>
              <p data-testid="admin-strategy-metrics-false-allow">false_allow_rate: {metricsSummary?.metrics?.false_allow_rate ?? "-"}</p>
              <p data-testid="admin-strategy-metrics-false-reject">false_reject_rate: {metricsSummary?.metrics?.false_reject_rate ?? "-"}</p>
              <p data-testid="admin-strategy-metrics-pnl">pnl_contribution: {metricsSummary?.metrics?.pnl_contribution ?? "-"}</p>
              <p data-testid="admin-strategy-metrics-execution-quality">execution_quality: {metricsSummary?.metrics?.execution_quality ?? "-"}</p>
              <p data-testid="admin-strategy-metrics-drift-alerts">drift_alerts: {metricsSummary?.metrics?.drift_alerts ?? "-"}</p>
              <p data-testid="admin-strategy-metrics-slippage-p95">slippage_p95_bps: {metricsSummary?.metrics?.slippage_p95_bps ?? "-"}</p>
              <p data-testid="admin-strategy-metrics-latency-p95">latency_p95_ms: {metricsSummary?.metrics?.latency_p95_ms ?? "-"}</p>
              <p data-testid="admin-strategy-metrics-health-score">version_health_score: {metricsSummary?.metrics?.version_health_score ?? "-"}</p>
            </div>
          ) : (
            <p className="text-xs text-slate-400" data-testid="admin-strategy-metrics-summary-empty">Metrics yok.</p>
          )}
        </div>

        <div className="space-y-2 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-observability-secondary-panel">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-observability-secondary-title">Drift / False Signal Summary</p>
          <p className="text-xs" data-testid="admin-strategy-drift-count">drift_alert_count: {driftSummary?.count ?? 0}</p>
          <p className="text-xs" data-testid="admin-strategy-false-allow-rate">false_allow_rate: {falseSignalSummary?.false_allow_rate ?? "-"}</p>
          <p className="text-xs" data-testid="admin-strategy-false-reject-rate">false_reject_rate: {falseSignalSummary?.false_reject_rate ?? "-"}</p>
          <p className="text-xs" data-testid="admin-strategy-signal-quality">signal_quality_last_50: {falseSignalSummary?.signal_quality_last_50 ?? "-"}</p>
        </div>
      </div>

      <div className="space-y-2 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-trend-chart-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-trend-chart-title">Trend + Anomaly Band</p>
        <div className="h-64 w-full" data-testid="admin-strategy-trend-chart-wrapper">
          {(metricsTrend?.trend_series || []).length > 0 ? (
            <ResponsiveContainer width="100%" height="100%" minWidth={320} minHeight={220}>
              <LineChart data={metricsTrend?.trend_series || []} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="timestamp" hide />
                <YAxis stroke="#94a3b8" />
                <Tooltip
                  contentStyle={{ backgroundColor: "#0f172a", borderColor: "#334155", color: "#e2e8f0" }}
                  labelStyle={{ color: "#cbd5e1" }}
                />
                <Line type="monotone" dataKey="score_delta" stroke="#f97316" dot={false} name="score_delta" />
                <Line type="monotone" dataKey="anomaly_upper" stroke="#22c55e" dot={false} name="anomaly_upper" strokeDasharray="5 5" />
                <Line type="monotone" dataKey="anomaly_lower" stroke="#ef4444" dot={false} name="anomaly_lower" strokeDasharray="5 5" />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-xs text-slate-400" data-testid="admin-strategy-trend-chart-empty">Trend verisi bulunamadı.</p>
          )}
        </div>
      </div>

      <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-regime-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-regime-title">Regime Gating Demo</p>
        <div className="grid gap-4 lg:grid-cols-2" data-testid="admin-regime-top-grid">
          <div className="space-y-2 border border-slate-700 p-3" data-testid="admin-regime-binding-panel">
            <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-regime-binding-title">Binding Editor</p>
            <Input
              placeholder="allowed regimes (comma)"
              value={bindingForm.allowed_regimes}
              onChange={(e) => setBindingForm((prev) => ({ ...prev, allowed_regimes: e.target.value }))}
              data-testid="admin-regime-binding-allowed-input"
            />
            <Input
              placeholder="blocked regimes (comma)"
              value={bindingForm.blocked_regimes}
              onChange={(e) => setBindingForm((prev) => ({ ...prev, blocked_regimes: e.target.value }))}
              data-testid="admin-regime-binding-blocked-input"
            />
            <div className="grid gap-2 md:grid-cols-2" data-testid="admin-regime-binding-meta-grid">
              <Input
                placeholder="priority"
                value={bindingForm.priority}
                onChange={(e) => setBindingForm((prev) => ({ ...prev, priority: e.target.value }))}
                data-testid="admin-regime-binding-priority-input"
              />
              <Input
                placeholder="policy version"
                value={bindingForm.gating_policy_version}
                onChange={(e) => setBindingForm((prev) => ({ ...prev, gating_policy_version: e.target.value }))}
                data-testid="admin-regime-binding-policy-input"
              />
            </div>
            <div className="flex flex-wrap gap-2" data-testid="admin-regime-binding-actions">
              <Button className="bg-orange-500 text-black hover:bg-orange-600" onClick={createRegimeBinding} data-testid="admin-regime-binding-create-button">
                Create Binding
              </Button>
              <Button variant="outline" className="border-slate-600 text-slate-200" onClick={seedDemoBinding} data-testid="admin-regime-binding-seed-button">
                Seed Demo Binding
              </Button>
            </div>
            <div className="space-y-1 text-xs text-slate-300" data-testid="admin-regime-binding-list">
              {regimeBindings.map((item) => (
                <div key={item.binding_id} className="border border-slate-700 p-2" data-testid={`admin-regime-binding-row-${item.binding_id}`}>
                  <p data-testid={`admin-regime-binding-regimes-${item.binding_id}`}>allowed: {(item.allowed_regimes || []).join(", ") || "*"}</p>
                  <p className="text-slate-400" data-testid={`admin-regime-binding-blocked-${item.binding_id}`}>blocked: {(item.blocked_regimes || []).join(", ") || "-"}</p>
                </div>
              ))}
              {regimeBindings.length === 0 && (
                <p className="text-slate-400" data-testid="admin-regime-binding-empty">No bindings yet</p>
              )}
            </div>
          </div>

          <div className="space-y-2 border border-slate-700 p-3" data-testid="admin-regime-demo-panel">
            <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-regime-demo-title">Deterministic Demo</p>
            <div className="flex flex-wrap gap-2" data-testid="admin-regime-demo-actions">
              <Button className="bg-emerald-500 text-black hover:bg-emerald-600" onClick={() => runRegimeDemo("allowed")} data-testid="admin-regime-demo-allowed-button">
                Run Allowed Demo
              </Button>
              <Button variant="outline" className="border-red-500 text-red-200" onClick={() => runRegimeDemo("blocked")} data-testid="admin-regime-demo-blocked-button">
                Run Blocked Demo
              </Button>
            </div>
            {regimeDemoResult && (
              <div className="border border-slate-700 p-2 text-xs" data-testid="admin-regime-demo-result">
                <p data-testid="admin-regime-demo-variant">variant: {regimeDemoResult.variant}</p>
                <p data-testid="admin-regime-demo-label">regime_label: {regimeDemoResult.snapshot?.regime_label}</p>
                <p data-testid="admin-regime-demo-allowed">allowed: {String(regimeDemoResult.allowed)}</p>
                <p className="text-slate-400" data-testid="admin-regime-demo-reason">reason: {regimeDemoResult.reason_code || "-"}</p>
              </div>
            )}
            {!regimeDemoResult && (
              <p className="text-xs text-slate-400" data-testid="admin-regime-demo-empty">Demo sonucu bekleniyor.</p>
            )}
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-2" data-testid="admin-regime-bottom-grid">
          <div className="space-y-2 border border-slate-700 p-3" data-testid="admin-regime-snapshots-panel">
            <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-regime-snapshots-title">Latest Snapshots</p>
            {(regimeOverview?.snapshots || []).map((item) => (
              <div key={item.regime_snapshot_id} className="border border-slate-700 p-2 text-xs" data-testid={`admin-regime-snapshot-row-${item.regime_snapshot_id}`}>
                <p data-testid={`admin-regime-snapshot-label-${item.regime_snapshot_id}`}>{item.regime_label} · {item.symbol}</p>
                <p className="text-slate-400" data-testid={`admin-regime-snapshot-score-${item.regime_snapshot_id}`}>score: {item.regime_score}</p>
              </div>
            ))}
            {(!regimeOverview?.snapshots || regimeOverview.snapshots.length === 0) && (
              <p className="text-xs text-slate-400" data-testid="admin-regime-snapshots-empty">Snapshot yok.</p>
            )}
          </div>
          <div className="space-y-2 border border-slate-700 p-3" data-testid="admin-regime-rejects-panel">
            <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-regime-rejects-title">Reject Distribution</p>
            {regimeOverview?.reject_distribution && Object.keys(regimeOverview.reject_distribution).length === 0 && (
              <p className="text-xs text-slate-400" data-testid="admin-regime-rejects-empty">Reject kaydı yok.</p>
            )}
            {regimeOverview?.reject_distribution &&
              Object.entries(regimeOverview.reject_distribution).map(([key, value]) => (
                <div key={key} className="flex items-center justify-between text-xs" data-testid={`admin-regime-reject-row-${key}`}>
                  <span>{key}</span>
                  <span>{value}</span>
                </div>
              ))}
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2" data-testid="admin-strategy-ops-grid">
        <div className="space-y-2 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-binding-preview-panel">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-binding-preview-title">Resolved Binding Preview</p>
          {bindingPreview ? (
            <div className="space-y-1 text-xs" data-testid="admin-strategy-binding-preview-content">
              <p data-testid="admin-strategy-binding-preview-regime">regime: {bindingPreview.regime_label}</p>
              <p data-testid="admin-strategy-binding-preview-winner">winner_binding_id: {bindingPreview.winner_binding_id || "-"}</p>
              <p data-testid="admin-strategy-binding-preview-priority">winner_priority: {bindingPreview.winner_priority ?? "-"}</p>
              <p data-testid="admin-strategy-binding-preview-conflict">has_conflict: {String(Boolean(bindingPreview.has_conflict))}</p>
            </div>
          ) : (
            <p className="text-xs text-slate-400" data-testid="admin-strategy-binding-preview-empty">Preview verisi yok.</p>
          )}
        </div>

        <div className="space-y-2 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-promotion-panel">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-promotion-title">Promotion Requests</p>
          <div className="space-y-2" data-testid="admin-strategy-promotion-list">
            {promotionRequests.map((item) => (
              <div key={item.request_id} className="border border-slate-700 p-2" data-testid={`admin-strategy-promotion-row-${item.request_id}`}>
                <p className="text-xs" data-testid={`admin-strategy-promotion-version-${item.request_id}`}>version: {item.strategy_version_id}</p>
                <p className="text-xs text-slate-400" data-testid={`admin-strategy-promotion-status-${item.request_id}`}>status: {item.status}</p>
                <p className="text-xs text-slate-400" data-testid={`admin-strategy-promotion-requested-by-${item.request_id}`}>requested_by: {item.requested_by || "-"}</p>
                <p className="text-xs text-slate-400" data-testid={`admin-strategy-promotion-reviewed-at-${item.request_id}`}>reviewed_at: {item.reviewed_at || "-"}</p>
                <div className="mt-2 flex flex-wrap gap-2" data-testid={`admin-strategy-promotion-actions-${item.request_id}`}>
                  <Button variant="outline" className="border-emerald-500 text-emerald-200" onClick={() => approvePromote(item.request_id)} data-testid={`admin-strategy-promotion-approve-${item.request_id}`}>
                    Approve
                  </Button>
                  <Button variant="outline" className="border-red-500 text-red-200" onClick={() => rejectPromote(item.request_id)} data-testid={`admin-strategy-promotion-reject-${item.request_id}`}>
                    Reject
                  </Button>
                </div>
              </div>
            ))}
            {promotionRequests.length === 0 && (
              <p className="text-xs text-slate-400" data-testid="admin-strategy-promotion-empty">Promotion request yok.</p>
            )}
          </div>
        </div>
      </div>

      <div className="space-y-2 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-audit-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-audit-title">Audit / History</p>
        <div className="grid gap-2 md:grid-cols-4" data-testid="admin-strategy-audit-filter-row">
          <Input placeholder="event type" value={auditFilters.eventType} onChange={(e) => setAuditFilters((prev) => ({ ...prev, eventType: e.target.value }))} data-testid="admin-strategy-audit-filter-event-type-input" />
          <Input placeholder="user" value={auditFilters.user} onChange={(e) => setAuditFilters((prev) => ({ ...prev, user: e.target.value }))} data-testid="admin-strategy-audit-filter-user-input" />
          <Input type="datetime-local" value={auditFilters.from} onChange={(e) => setAuditFilters((prev) => ({ ...prev, from: e.target.value }))} data-testid="admin-strategy-audit-filter-from-input" />
          <Input type="datetime-local" value={auditFilters.to} onChange={(e) => setAuditFilters((prev) => ({ ...prev, to: e.target.value }))} data-testid="admin-strategy-audit-filter-to-input" />
        </div>
        <div className="flex flex-wrap gap-2" data-testid="admin-strategy-audit-export-actions">
          <Button variant="outline" className="border-slate-500 text-slate-100" onClick={() => exportAuditHistory("json")} data-testid="admin-strategy-audit-export-json-button">Export JSON</Button>
          <Button variant="outline" className="border-slate-500 text-slate-100" onClick={() => exportAuditHistory("csv")} data-testid="admin-strategy-audit-export-csv-button">Export CSV</Button>
        </div>
        <div className="space-y-2" data-testid="admin-strategy-audit-list">
          {filteredTimelineItems.map((item, idx) => (
            <div key={`${item.audit_id}-${idx}`} className="border border-slate-700 p-2 text-xs" data-testid={`admin-strategy-audit-row-${idx}`}>
              <p data-testid={`admin-strategy-audit-action-${idx}`}>{item.action}</p>
              <p className="text-slate-400" data-testid={`admin-strategy-audit-actor-${idx}`}>{item.actor_role || "-"} · {item.actor_user_id || "-"}</p>
              <p className="text-slate-400" data-testid={`admin-strategy-audit-time-${idx}`}>{item.timestamp}</p>
            </div>
          ))}
          {filteredTimelineItems.length === 0 && (
            <p className="text-xs text-slate-400" data-testid="admin-strategy-audit-empty">Audit kaydı yok.</p>
          )}
        </div>
        <div className="space-y-1 border border-slate-700 p-2 text-xs" data-testid="admin-strategy-rollback-chain-panel">
          <p className="uppercase tracking-wider text-slate-400" data-testid="admin-strategy-rollback-chain-title">Rollback Chain</p>
          {rollbackChain.map((item, idx) => (
            <p key={`${item.strategy_version_id}-${idx}`} data-testid={`admin-strategy-rollback-chain-item-${idx}`}>
              {item.strategy_version_id} ← {item.rolled_back_from_version_id} ({item.lifecycle_state})
            </p>
          ))}
          {rollbackChain.length === 0 && <p data-testid="admin-strategy-rollback-chain-empty">Rollback chain bulunamadı.</p>}
        </div>
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
