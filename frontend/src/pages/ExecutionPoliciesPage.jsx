import { useEffect, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { ProdConfigRemediationModal } from "@/components/ProdConfigRemediationModal";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

const BUILDER_FIELDS = [
  "exposure",
  "pnl",
  "drawdown",
  "leverage",
  "margin_utilization",
  "volatility",
  "environment",
  "strategy_risk_class",
];
const BUILDER_OPERATORS = [">", "<", ">=", "<=", "=="];
const BUILDER_ACTIONS = ["BLOCK", "WARN", "THROTTLE", "REDUCE_ONLY"];
const BUILDER_SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
const BUILDER_ENVIRONMENTS = ["DEV", "STAGING", "PROD", "TESTNET", "LIVE"];
const ACTIVATION_ENVIRONMENTS = ["dev", "staging", "testnet", "live", "prod"];
const RISK_CLASSES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
const TABS = [
  { id: "builder", label: "Builder" },
  { id: "diff", label: "Diff" },
  { id: "simulation", label: "Simulation" },
  { id: "bulk", label: "Bulk Ops" },
  { id: "overview", label: "Observability" },
];

const DEFAULT_RULE = {
  rule_id: "rule_1",
  action: "BLOCK",
  severity: "HIGH",
  logical_operator: "AND",
  conditions: [
    {
      field: "exposure",
      operator: ">",
      value: "",
    },
  ],
};

export const ExecutionPoliciesPage = () => {
  const [payload, setPayload] = useState(null);
  const [remediationState, setRemediationState] = useState(null);
  const [isRemediationOpen, setIsRemediationOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("builder");

  const [builderPayload, setBuilderPayload] = useState({
    policy_code: "",
    version_label: "builder",
    description: "",
    scope: {
      environment: "DEV",
      strategy: "",
      symbol: "",
    },
    rules: [DEFAULT_RULE],
  });
  const [builderValidation, setBuilderValidation] = useState(null);
  const [isBuilderValidating, setIsBuilderValidating] = useState(false);
  const [isBuilderSaving, setIsBuilderSaving] = useState(false);

  const [selectedVersionId, setSelectedVersionId] = useState("");
  const [versionValidation, setVersionValidation] = useState(null);
  const [versionEnvironment, setVersionEnvironment] = useState("testnet");
  const [overrideHighRisk, setOverrideHighRisk] = useState(false);
  const [overrideReason, setOverrideReason] = useState("");
  const [rollbackReason, setRollbackReason] = useState("");
  const [isVersionActionLoading, setIsVersionActionLoading] = useState(false);
  const [isVersionApproveLoading, setIsVersionApproveLoading] = useState(false);
  const [isVersionRollbackLoading, setIsVersionRollbackLoading] = useState(false);

  const [diffVersionA, setDiffVersionA] = useState("");
  const [diffVersionB, setDiffVersionB] = useState("");
  const [diffResult, setDiffResult] = useState(null);
  const [isDiffLoading, setIsDiffLoading] = useState(false);

  const [simulationVersionId, setSimulationVersionId] = useState("");
  const [simulationEnvironment, setSimulationEnvironment] = useState("testnet");
  const [simulationRiskClass, setSimulationRiskClass] = useState("MEDIUM");
  const [simulationStrategy, setSimulationStrategy] = useState("");
  const [simulationOrderJson, setSimulationOrderJson] = useState(`{
  "exposure": 0,
  "pnl": 0
}`);
  const [simulationMarketJson, setSimulationMarketJson] = useState(`{
  "volatility": 0
}`);
  const [simulationResult, setSimulationResult] = useState(null);
  const [isSimulationRunning, setIsSimulationRunning] = useState(false);

  const [bulkActivateVersions, setBulkActivateVersions] = useState("");
  const [bulkActivateEnvironment, setBulkActivateEnvironment] = useState("testnet");
  const [bulkActivateMode, setBulkActivateMode] = useState("ACTIVE");
  const [bulkActivateOverride, setBulkActivateOverride] = useState(false);
  const [bulkActivateReason, setBulkActivateReason] = useState("");
  const [bulkActivateResult, setBulkActivateResult] = useState(null);
  const [isBulkActivateRunning, setIsBulkActivateRunning] = useState(false);

  const [bulkRollbackItems, setBulkRollbackItems] = useState([
    { policy_code: "", target_version_id: "", reason: "" },
  ]);
  const [bulkRollbackResult, setBulkRollbackResult] = useState(null);
  const [isBulkRollbackRunning, setIsBulkRollbackRunning] = useState(false);

  const [bulkBindingItems, setBulkBindingItems] = useState([
    {
      strategy_id: "",
      bound_policy_set: "",
      risk_class: "MEDIUM",
      execution_mode: "SIMULATION",
      state: "enabled",
      enabled: true,
    },
  ]);
  const [bulkBindingResult, setBulkBindingResult] = useState(null);
  const [isBulkBindingRunning, setIsBulkBindingRunning] = useState(false);

  const load = async () => {
    setIsLoading(true);
    try {
      const [{ data: policyData }, { data: remediationData }] = await Promise.all([
        apiClient.get("/admin/execution-policies"),
        apiClient.get("/admin/system/remediate-config"),
      ]);
      setPayload(policyData);
      setRemediationState(remediationData);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Execution policy verisi alınamadı");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  if (isLoading) {
    return <LoadingSkeleton rows={7} testId="execution-policies-loading-skeleton" />;
  }

  const registry = payload?.registry || {};
  const engineConfig = payload?.engine_config || {};
  const observability = payload?.observability_metrics || {};
  const decisionLog = payload?.policy_decision_log || [];
  const topReasonCodes = observability?.top_reason_codes || [];
  const criticalViolations = observability?.recent_critical_violations || [];
  const policyVersions = payload?.policy_versions || [];
  const strategyHealth = payload?.strategy_health || [];
  const releaseGate = payload?.release_gate || {};
  const remediationRecommendations = payload?.remediation_recommendations || [];
  const environmentOverrides = payload?.environment_overrides || [];
  const safeModeStates = payload?.safe_mode_states || [];
  const severityDistribution = observability?.violation_aggregations?.["24h"]?.severity_distribution || {};
  const violations = payload?.recent_policy_violations || [];

  const versionMap = policyVersions.reduce((acc, item) => {
    acc[item.version_id] = item;
    return acc;
  }, {});

  const selectedVersion = versionMap[selectedVersionId];
  const simulationVersion = versionMap[simulationVersionId];
  const diffVersionAData = versionMap[diffVersionA];
  const diffVersionBData = versionMap[diffVersionB];

  useEffect(() => {
    if (!selectedVersionId) {
      setVersionValidation(null);
      return;
    }
    const loadValidation = async () => {
      try {
        const { data } = await apiClient.post(`/admin/execution-policies/versions/${selectedVersionId}/validate`);
        setVersionValidation(data);
      } catch (error) {
        setVersionValidation(null);
        toast.error(error?.response?.data?.detail || "Version validation alınamadı");
      }
    };
    loadValidation();
  }, [selectedVersionId]);

  const updateBuilderScope = (field, value) => {
    setBuilderPayload((prev) => ({
      ...prev,
      scope: {
        ...prev.scope,
        [field]: value,
      },
    }));
  };

  const updateBuilderRule = (index, patch) => {
    setBuilderPayload((prev) => {
      const nextRules = [...prev.rules];
      nextRules[index] = { ...nextRules[index], ...patch };
      return { ...prev, rules: nextRules };
    });
  };

  const updateBuilderCondition = (ruleIndex, conditionIndex, patch) => {
    setBuilderPayload((prev) => {
      const nextRules = [...prev.rules];
      const nextConditions = [...(nextRules[ruleIndex]?.conditions || [])];
      nextConditions[conditionIndex] = { ...nextConditions[conditionIndex], ...patch };
      nextRules[ruleIndex] = { ...nextRules[ruleIndex], conditions: nextConditions };
      return { ...prev, rules: nextRules };
    });
  };

  const addBuilderRule = () => {
    setBuilderPayload((prev) => ({
      ...prev,
      rules: [
        ...prev.rules,
        {
          rule_id: `rule_${prev.rules.length + 1}`,
          action: "WARN",
          severity: "MEDIUM",
          logical_operator: "AND",
          conditions: [
            {
              field: "exposure",
              operator: ">",
              value: "",
            },
          ],
        },
      ],
    }));
  };

  const removeBuilderRule = (index) => {
    setBuilderPayload((prev) => ({
      ...prev,
      rules: prev.rules.filter((_, idx) => idx !== index),
    }));
  };

  const addBuilderCondition = (ruleIndex) => {
    setBuilderPayload((prev) => {
      const nextRules = [...prev.rules];
      const nextConditions = [...(nextRules[ruleIndex]?.conditions || [])];
      nextConditions.push({ field: "exposure", operator: ">", value: "" });
      nextRules[ruleIndex] = { ...nextRules[ruleIndex], conditions: nextConditions };
      return { ...prev, rules: nextRules };
    });
  };

  const removeBuilderCondition = (ruleIndex, conditionIndex) => {
    setBuilderPayload((prev) => {
      const nextRules = [...prev.rules];
      const nextConditions = [...(nextRules[ruleIndex]?.conditions || [])].filter((_, idx) => idx !== conditionIndex);
      nextRules[ruleIndex] = { ...nextRules[ruleIndex], conditions: nextConditions };
      return { ...prev, rules: nextRules };
    });
  };

  const handleBuilderValidate = async () => {
    setIsBuilderValidating(true);
    try {
      const { data } = await apiClient.post("/admin/execution-policies/validate", builderPayload);
      setBuilderValidation(data);
      toast.success("Validation tamamlandı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Validation başarısız");
    } finally {
      setIsBuilderValidating(false);
    }
  };

  const handleBuilderSave = async () => {
    setIsBuilderSaving(true);
    try {
      const { data } = await apiClient.post("/admin/execution-policies/builder/versions", {
        ...builderPayload,
        change_summary: builderPayload.description || "Builder v1",
      });
      setBuilderValidation({
        errors: data?.validation?.errors || [],
        warnings: data?.validation?.warnings || [],
        risk_level: data?.validation?.risk_level || "LOW",
        human_readable: data?.human_readable,
      });
      toast.success("Policy versiyonu oluşturuldu");
      await load();
    } catch (error) {
      const detail = error?.response?.data?.detail;
      if (detail?.validation) {
        setBuilderValidation(detail.validation);
      }
      toast.error(detail?.error || detail || "Policy kaydedilemedi");
    } finally {
      setIsBuilderSaving(false);
    }
  };

  const handleApproveVersion = async () => {
    if (!selectedVersionId) return;
    setIsVersionApproveLoading(true);
    try {
      await apiClient.post(`/admin/execution-policies/versions/${selectedVersionId}/approve`);
      toast.success("Version approved");
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Approve başarısız");
    } finally {
      setIsVersionApproveLoading(false);
    }
  };

  const handleActivateVersion = async (mode) => {
    if (!selectedVersionId) return;
    setIsVersionActionLoading(true);
    try {
      const payload = {
        environment: versionEnvironment,
        activation_mode: mode,
        override_high_risk: overrideHighRisk,
        override_reason: overrideReason,
      };
      await apiClient.post(`/admin/execution-policies/versions/${selectedVersionId}/activate`, payload);
      toast.success(`Version ${mode} aktive edildi`);
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail?.error || error?.response?.data?.detail || "Activation başarısız");
    } finally {
      setIsVersionActionLoading(false);
    }
  };

  const handleRollbackVersion = async () => {
    if (!selectedVersionId || !selectedVersion?.policy_code) return;
    setIsVersionRollbackLoading(true);
    try {
      await apiClient.post(`/admin/execution-policies/versions/${selectedVersion.policy_code}/rollback`, {
        target_version_id: selectedVersionId,
        reason: rollbackReason || "manual rollback",
      });
      toast.success("Rollback tamamlandı");
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Rollback başarısız");
    } finally {
      setIsVersionRollbackLoading(false);
    }
  };

  const handleDiffLoad = async () => {
    if (!diffVersionA || !diffVersionB) {
      toast.error("Version seçimleri gerekli");
      return;
    }
    if (!diffVersionAData?.policy_code || diffVersionAData.policy_code !== diffVersionBData?.policy_code) {
      toast.error("A/B policy_code eşleşmeli");
      return;
    }
    setIsDiffLoading(true);
    try {
      const { data } = await apiClient.post("/admin/execution-policies/diff", {
        policy_code: diffVersionAData.policy_code,
        version_a: diffVersionA,
        version_b: diffVersionB,
      });
      setDiffResult(data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Diff alınamadı");
    } finally {
      setIsDiffLoading(false);
    }
  };

  const handleSimulationRun = async () => {
    if (!simulationVersionId || !simulationVersion?.policy_code) {
      toast.error("Version seçilmeli");
      return;
    }
    let orderPayload = {};
    let marketPayload = {};
    try {
      orderPayload = simulationOrderJson ? JSON.parse(simulationOrderJson) : {};
      marketPayload = simulationMarketJson ? JSON.parse(simulationMarketJson) : {};
    } catch (error) {
      toast.error("JSON formatı geçersiz");
      return;
    }
    setIsSimulationRunning(true);
    try {
      const { data } = await apiClient.post("/admin/execution-policies/simulate", {
        policy_code: simulationVersion.policy_code,
        version_id: simulationVersionId,
        simulation_input: {
          environment: simulationEnvironment,
          strategy_risk_class: simulationRiskClass,
          strategy: simulationStrategy,
          order: orderPayload,
          market_state: marketPayload,
        },
      });
      setSimulationResult(data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Simulation başarısız");
    } finally {
      setIsSimulationRunning(false);
    }
  };

  const handleBulkActivate = async () => {
    const ids = bulkActivateVersions
      .split("\n")
      .map((item) => item.trim())
      .filter(Boolean);
    if (ids.length === 0) {
      toast.error("Version ID listesi boş");
      return;
    }
    setIsBulkActivateRunning(true);
    try {
      const { data } = await apiClient.post("/admin/execution-policies/bulk/activate", {
        items: ids.map((versionId) => ({
          version_id: versionId,
          environment: bulkActivateEnvironment,
          activation_mode: bulkActivateMode,
          override_high_risk: bulkActivateOverride,
          override_reason: bulkActivateReason,
        })),
      });
      setBulkActivateResult(data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bulk activate başarısız");
    } finally {
      setIsBulkActivateRunning(false);
    }
  };

  const handleBulkRollback = async () => {
    const items = bulkRollbackItems.filter(
      (item) => item.policy_code && item.target_version_id && item.reason
    );
    if (items.length === 0) {
      toast.error("Rollback listesi boş");
      return;
    }
    setIsBulkRollbackRunning(true);
    try {
      const { data } = await apiClient.post("/admin/execution-policies/bulk/rollback", { items });
      setBulkRollbackResult(data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bulk rollback başarısız");
    } finally {
      setIsBulkRollbackRunning(false);
    }
  };

  const handleBulkBinding = async () => {
    const items = bulkBindingItems.filter((item) => item.strategy_id && item.bound_policy_set);
    if (items.length === 0) {
      toast.error("Binding listesi boş");
      return;
    }
    setIsBulkBindingRunning(true);
    try {
      const { data } = await apiClient.post("/admin/execution-policies/bulk/strategy-binding", { items });
      setBulkBindingResult(data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bulk binding başarısız");
    } finally {
      setIsBulkBindingRunning(false);
    }
  };

  const builderErrors = builderValidation?.errors || [];
  const builderWarnings = builderValidation?.warnings || [];
  const builderRiskLevel = builderValidation?.risk_level || "LOW";
  const versionErrors = versionValidation?.errors || [];
  const versionWarnings = versionValidation?.warnings || [];
  const isActivationBlocked = versionErrors.length > 0;
  const isHighRisk = versionValidation?.risk_level === "HIGH" && versionWarnings.length > 0;
  const overrideReady = !isHighRisk || (overrideHighRisk && overrideReason);

  return (
    <section className="space-y-4" data-testid="execution-policies-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-emerald-300" data-testid="execution-policies-title">Execution Policy View</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="execution-policies-description">
          Symbol leverage cap, margin mode policy, TP/SL constraints ve son policy ihlalleri.
        </p>
      </header>

      <div className="flex flex-wrap gap-2" data-testid="execution-policies-tab-list">
        {TABS.map((tab) => (
          <Button
            key={tab.id}
            variant={activeTab === tab.id ? "default" : "outline"}
            className={
              activeTab === tab.id
                ? "bg-emerald-500 text-slate-950 hover:bg-emerald-400"
                : "border-slate-700 text-slate-200 hover:border-emerald-400"
            }
            onClick={() => setActiveTab(tab.id)}
            data-testid={`execution-policies-tab-${tab.id}`}
          >
            {tab.label}
          </Button>
        ))}
      </div>

      {activeTab === "builder" && (
        <div className="space-y-4" data-testid="execution-policies-builder-panel">
          <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="policy-builder-form">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-xs uppercase tracking-widest text-emerald-300" data-testid="policy-builder-title">Policy Builder v1</p>
                <p className="text-xs text-slate-400" data-testid="policy-builder-subtitle">Sınırlı condition seti + strict validation gate.</p>
              </div>
              <div className="flex flex-wrap gap-2" data-testid="policy-builder-actions">
                <Button
                  className="border border-slate-700 bg-transparent text-slate-200 hover:border-emerald-400"
                  onClick={handleBuilderValidate}
                  disabled={isBuilderValidating}
                  data-testid="policy-builder-validate-button"
                >
                  Validate
                </Button>
                <Button
                  className="bg-emerald-500 text-slate-950 hover:bg-emerald-400"
                  onClick={handleBuilderSave}
                  disabled={isBuilderSaving}
                  data-testid="policy-builder-save-button"
                >
                  Create Version
                </Button>
              </div>
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-2" data-testid="policy-builder-meta">
              <div className="space-y-1">
                <label className="text-xs text-slate-400" data-testid="policy-builder-policy-code-label">Policy Code</label>
                <input
                  className="w-full rounded border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                  value={builderPayload.policy_code}
                  onChange={(event) => setBuilderPayload((prev) => ({ ...prev, policy_code: event.target.value }))}
                  placeholder="execution:core:baseline"
                  data-testid="policy-builder-policy-code-input"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-slate-400" data-testid="policy-builder-version-label">Version Label</label>
                <input
                  className="w-full rounded border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                  value={builderPayload.version_label}
                  onChange={(event) => setBuilderPayload((prev) => ({ ...prev, version_label: event.target.value }))}
                  placeholder="builder"
                  data-testid="policy-builder-version-input"
                />
              </div>
              <div className="space-y-1 md:col-span-2">
                <label className="text-xs text-slate-400" data-testid="policy-builder-description-label">Description</label>
                <textarea
                  className="min-h-[80px] w-full rounded border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                  value={builderPayload.description}
                  onChange={(event) => setBuilderPayload((prev) => ({ ...prev, description: event.target.value }))}
                  placeholder="Bu versiyonun değişim özeti"
                  data-testid="policy-builder-description-input"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-slate-400" data-testid="policy-builder-scope-env-label">Scope Environment</label>
                <select
                  className="w-full rounded border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                  value={builderPayload.scope.environment}
                  onChange={(event) => updateBuilderScope("environment", event.target.value)}
                  data-testid="policy-builder-scope-environment"
                >
                  {BUILDER_ENVIRONMENTS.map((env) => (
                    <option key={env} value={env}>{env}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-xs text-slate-400" data-testid="policy-builder-scope-strategy-label">Scope Strategy</label>
                <input
                  className="w-full rounded border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                  value={builderPayload.scope.strategy}
                  onChange={(event) => updateBuilderScope("strategy", event.target.value)}
                  placeholder="core-alpha"
                  data-testid="policy-builder-scope-strategy"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-slate-400" data-testid="policy-builder-scope-symbol-label">Scope Symbol</label>
                <input
                  className="w-full rounded border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                  value={builderPayload.scope.symbol}
                  onChange={(event) => updateBuilderScope("symbol", event.target.value)}
                  placeholder="BTCUSDT"
                  data-testid="policy-builder-scope-symbol"
                />
              </div>
            </div>

            <div className="mt-6 space-y-4" data-testid="policy-builder-rules">
              {builderPayload.rules.map((rule, ruleIndex) => (
                <div key={`${rule.rule_id}-${ruleIndex}`} className="rounded border border-slate-800 bg-slate-950/60 p-3" data-testid={`policy-builder-rule-${ruleIndex}`}>
                  <div className="flex flex-wrap items-center gap-2">
                    <input
                      className="min-w-[140px] flex-1 rounded border border-slate-800 bg-slate-950 px-3 py-1 text-xs text-slate-100"
                      value={rule.rule_id}
                      onChange={(event) => updateBuilderRule(ruleIndex, { rule_id: event.target.value })}
                      placeholder={`rule_${ruleIndex + 1}`}
                      data-testid={`policy-builder-rule-id-${ruleIndex}`}
                    />
                    <select
                      className="rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-100"
                      value={rule.action}
                      onChange={(event) => updateBuilderRule(ruleIndex, { action: event.target.value })}
                      data-testid={`policy-builder-rule-action-${ruleIndex}`}
                    >
                      {BUILDER_ACTIONS.map((action) => (
                        <option key={action} value={action}>{action}</option>
                      ))}
                    </select>
                    <select
                      className="rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-100"
                      value={rule.severity}
                      onChange={(event) => updateBuilderRule(ruleIndex, { severity: event.target.value })}
                      data-testid={`policy-builder-rule-severity-${ruleIndex}`}
                    >
                      {BUILDER_SEVERITIES.map((sev) => (
                        <option key={sev} value={sev}>{sev}</option>
                      ))}
                    </select>
                    <select
                      className="rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-100"
                      value={rule.logical_operator}
                      onChange={(event) => updateBuilderRule(ruleIndex, { logical_operator: event.target.value })}
                      data-testid={`policy-builder-rule-logical-${ruleIndex}`}
                    >
                      <option value="AND">AND</option>
                      <option value="OR">OR</option>
                    </select>
                    <Button
                      className="border border-slate-700 bg-transparent text-xs text-slate-200 hover:border-red-400"
                      onClick={() => removeBuilderRule(ruleIndex)}
                      data-testid={`policy-builder-rule-remove-${ruleIndex}`}
                    >
                      Rule Sil
                    </Button>
                  </div>

                  <div className="mt-3 space-y-2" data-testid={`policy-builder-conditions-${ruleIndex}`}>
                    {rule.conditions.map((condition, conditionIndex) => (
                      <div
                        key={`${ruleIndex}-${conditionIndex}`}
                        className="grid items-center gap-2 md:grid-cols-[1.2fr,0.8fr,1fr,auto]"
                        data-testid={`policy-builder-condition-${ruleIndex}-${conditionIndex}`}
                      >
                        <select
                          className="rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-100"
                          value={condition.field}
                          onChange={(event) => updateBuilderCondition(ruleIndex, conditionIndex, { field: event.target.value })}
                          data-testid={`policy-builder-condition-field-${ruleIndex}-${conditionIndex}`}
                        >
                          {BUILDER_FIELDS.map((field) => (
                            <option key={field} value={field}>{field}</option>
                          ))}
                        </select>
                        <select
                          className="rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-100"
                          value={condition.operator}
                          onChange={(event) => updateBuilderCondition(ruleIndex, conditionIndex, { operator: event.target.value })}
                          data-testid={`policy-builder-condition-operator-${ruleIndex}-${conditionIndex}`}
                        >
                          {BUILDER_OPERATORS.map((op) => (
                            <option key={op} value={op}>{op}</option>
                          ))}
                        </select>
                        <input
                          className="rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-100"
                          value={condition.value}
                          onChange={(event) => updateBuilderCondition(ruleIndex, conditionIndex, { value: event.target.value })}
                          placeholder="value"
                          data-testid={`policy-builder-condition-value-${ruleIndex}-${conditionIndex}`}
                        />
                        <Button
                          className="border border-slate-700 bg-transparent text-xs text-slate-200 hover:border-red-400"
                          onClick={() => removeBuilderCondition(ruleIndex, conditionIndex)}
                          data-testid={`policy-builder-condition-remove-${ruleIndex}-${conditionIndex}`}
                        >
                          Sil
                        </Button>
                      </div>
                    ))}
                    <Button
                      className="border border-slate-700 bg-transparent text-xs text-slate-200 hover:border-emerald-400"
                      onClick={() => addBuilderCondition(ruleIndex)}
                      data-testid={`policy-builder-condition-add-${ruleIndex}`}
                    >
                      Condition Ekle
                    </Button>
                  </div>
                </div>
              ))}
              <Button
                className="border border-slate-700 bg-transparent text-xs text-slate-200 hover:border-emerald-400"
                onClick={addBuilderRule}
                data-testid="policy-builder-add-rule-button"
              >
                Rule Ekle
              </Button>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2" data-testid="policy-builder-side-panel">
            <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="policy-builder-validation-panel">
              <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="policy-builder-validation-title">Validation Output</p>
              <p className="mt-2 text-sm text-slate-200" data-testid="policy-builder-validation-risk-level">risk_level: {builderRiskLevel}</p>
              <div className="mt-2 space-y-1" data-testid="policy-builder-validation-errors">
                {builderErrors.length === 0 && (
                  <p className="text-xs text-slate-500" data-testid="policy-builder-validation-errors-empty">Hata yok.</p>
                )}
                {builderErrors.map((item, idx) => (
                  <p key={`${item}-${idx}`} className="text-xs text-red-300" data-testid={`policy-builder-validation-error-${idx}`}>{item}</p>
                ))}
              </div>
              <div className="mt-2 space-y-1" data-testid="policy-builder-validation-warnings">
                {builderWarnings.length === 0 && (
                  <p className="text-xs text-slate-500" data-testid="policy-builder-validation-warnings-empty">Uyarı yok.</p>
                )}
                {builderWarnings.map((item, idx) => (
                  <p key={`${item}-${idx}`} className="text-xs text-amber-300" data-testid={`policy-builder-validation-warning-${idx}`}>{item}</p>
                ))}
              </div>
            </div>

            <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="policy-builder-json-panel">
              <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="policy-builder-json-title">Read-only JSON</p>
              <pre className="mt-2 max-h-64 overflow-auto text-[11px] text-slate-200" data-testid="policy-builder-json-readonly">{JSON.stringify(builderPayload, null, 2)}</pre>
              <div className="mt-4" data-testid="policy-builder-human-readable">
                <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="policy-builder-human-title">Human Summary</p>
                <p className="mt-2 text-xs text-slate-200" data-testid="policy-builder-human-summary">
                  {builderValidation?.human_readable?.summary || "Validation sonrası özet görünür."}
                </p>
                <p className="text-[11px] text-slate-400" data-testid="policy-builder-human-description">
                  {builderValidation?.human_readable?.description || "-"}
                </p>
              </div>
            </div>
          </div>

          <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="policy-version-actions-panel">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="policy-version-actions-title">Policy Version Actions</p>
                <p className="text-xs text-slate-500" data-testid="policy-version-actions-subtitle">ACTIVE/CANARY gate + override + rollback.</p>
              </div>
              <div className="flex flex-wrap gap-2" data-testid="policy-version-actions-buttons">
                <Button
                  className="border border-slate-700 bg-transparent text-xs text-slate-200 hover:border-emerald-400"
                  onClick={handleApproveVersion}
                  disabled={!selectedVersionId || isVersionApproveLoading}
                  data-testid="policy-version-approve-button"
                >
                  Approve
                </Button>
                <Button
                  className="bg-emerald-500 text-slate-950 hover:bg-emerald-400"
                  onClick={() => handleActivateVersion("ACTIVE")}
                  disabled={!selectedVersionId || isVersionActionLoading || isActivationBlocked || !overrideReady}
                  data-testid="policy-version-activate-button"
                >
                  ACTIVE
                </Button>
                <Button
                  className="bg-slate-100 text-slate-950 hover:bg-slate-200"
                  onClick={() => handleActivateVersion("CANARY")}
                  disabled={!selectedVersionId || isVersionActionLoading || isActivationBlocked || !overrideReady}
                  data-testid="policy-version-canary-button"
                >
                  CANARY
                </Button>
              </div>
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-3" data-testid="policy-version-actions-form">
              <div className="space-y-1">
                <label className="text-xs text-slate-400" data-testid="policy-version-select-label">Version</label>
                <select
                  className="w-full rounded border border-slate-800 bg-slate-950 px-2 py-2 text-xs text-slate-100"
                  value={selectedVersionId}
                  onChange={(event) => setSelectedVersionId(event.target.value)}
                  data-testid="policy-version-select"
                >
                  <option value="">Seçim yapın</option>
                  {policyVersions.map((version) => (
                    <option key={version.version_id} value={version.version_id}>
                      {version.policy_code} · v{version.version_number} ({version.state})
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-xs text-slate-400" data-testid="policy-version-environment-label">Environment</label>
                <select
                  className="w-full rounded border border-slate-800 bg-slate-950 px-2 py-2 text-xs text-slate-100"
                  value={versionEnvironment}
                  onChange={(event) => setVersionEnvironment(event.target.value)}
                  data-testid="policy-version-environment-select"
                >
                  {ACTIVATION_ENVIRONMENTS.map((env) => (
                    <option key={env} value={env}>{env}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-xs text-slate-400" data-testid="policy-version-rollback-reason-label">Rollback Reason</label>
                <input
                  className="w-full rounded border border-slate-800 bg-slate-950 px-2 py-2 text-xs text-slate-100"
                  value={rollbackReason}
                  onChange={(event) => setRollbackReason(event.target.value)}
                  placeholder="reason"
                  data-testid="policy-version-rollback-reason"
                />
              </div>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2" data-testid="policy-version-override-block">
              <label className="flex items-center gap-2 text-xs text-slate-200" data-testid="policy-version-override-toggle">
                <input
                  type="checkbox"
                  checked={overrideHighRisk}
                  onChange={(event) => setOverrideHighRisk(event.target.checked)}
                  data-testid="policy-version-override-checkbox"
                />
                High-risk override
              </label>
              <input
                className="min-w-[240px] flex-1 rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-100"
                value={overrideReason}
                onChange={(event) => setOverrideReason(event.target.value)}
                placeholder="override reason"
                data-testid="policy-version-override-reason"
              />
              <Button
                className="border border-slate-700 bg-transparent text-xs text-slate-200 hover:border-red-400"
                onClick={handleRollbackVersion}
                disabled={!selectedVersionId || !rollbackReason || isVersionRollbackLoading}
                data-testid="policy-version-rollback-button"
              >
                Rollback
              </Button>
            </div>

            <div className="mt-3 rounded border border-slate-800 bg-slate-950/60 p-3" data-testid="policy-version-validation-panel">
              <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="policy-version-validation-title">Validation Gate</p>
              <p className="mt-2 text-xs text-slate-200" data-testid="policy-version-validation-risk-level">risk_level: {versionValidation?.risk_level || "-"}</p>
              <div className="mt-2 space-y-1" data-testid="policy-version-validation-errors">
                {versionErrors.length === 0 && (
                  <p className="text-xs text-slate-500" data-testid="policy-version-validation-errors-empty">Hata yok.</p>
                )}
                {versionErrors.map((item, idx) => (
                  <p key={`${item}-${idx}`} className="text-xs text-red-300" data-testid={`policy-version-validation-error-${idx}`}>{item}</p>
                ))}
              </div>
              <div className="mt-2 space-y-1" data-testid="policy-version-validation-warnings">
                {versionWarnings.length === 0 && (
                  <p className="text-xs text-slate-500" data-testid="policy-version-validation-warnings-empty">Uyarı yok.</p>
                )}
                {versionWarnings.map((item, idx) => (
                  <p key={`${item}-${idx}`} className="text-xs text-amber-300" data-testid={`policy-version-validation-warning-${idx}`}>{item}</p>
                ))}
              </div>
              <p className="mt-2 text-[11px] text-slate-500" data-testid="policy-version-validation-status">
                {isActivationBlocked
                  ? "ACTIVE/CANARY kapalı (errors > 0)"
                  : isHighRisk
                  ? "High-risk override gerekli"
                  : "Activation hazır"}
              </p>
            </div>
          </div>
        </div>
      )}

      {activeTab === "diff" && (
        <div className="space-y-4" data-testid="execution-policies-diff-panel">
          <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="policy-diff-form">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="policy-diff-title">Version Diff</p>
                <p className="text-xs text-slate-500" data-testid="policy-diff-subtitle">Yan yana karşılaştırma + risk etiketi.</p>
              </div>
              <Button
                className="bg-emerald-500 text-slate-950 hover:bg-emerald-400"
                onClick={handleDiffLoad}
                disabled={isDiffLoading}
                data-testid="policy-diff-load-button"
              >
                Diff Yükle
              </Button>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2" data-testid="policy-diff-selectors">
              <select
                className="w-full rounded border border-slate-800 bg-slate-950 px-3 py-2 text-xs text-slate-100"
                value={diffVersionA}
                onChange={(event) => {
                  setDiffVersionA(event.target.value);
                  setDiffResult(null);
                }}
                data-testid="policy-diff-version-a-select"
              >
                <option value="">Version A</option>
                {policyVersions.map((version) => (
                  <option key={version.version_id} value={version.version_id}>
                    {version.policy_code} · v{version.version_number}
                  </option>
                ))}
              </select>
              <select
                className="w-full rounded border border-slate-800 bg-slate-950 px-3 py-2 text-xs text-slate-100"
                value={diffVersionB}
                onChange={(event) => {
                  setDiffVersionB(event.target.value);
                  setDiffResult(null);
                }}
                data-testid="policy-diff-version-b-select"
              >
                <option value="">Version B</option>
                {policyVersions.map((version) => (
                  <option key={version.version_id} value={version.version_id}>
                    {version.policy_code} · v{version.version_number}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {!diffResult && (
            <p className="text-xs text-slate-500" data-testid="policy-diff-empty">Diff yüklemek için versiyon seçin.</p>
          )}

          {diffResult && (
            <div className="grid gap-4 xl:grid-cols-2" data-testid="policy-diff-results">
              <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="policy-diff-before">
                <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="policy-diff-before-title">Before</p>
                <pre className="mt-2 max-h-80 overflow-auto text-xs text-slate-200" data-testid="policy-diff-before-json">
                  {JSON.stringify(diffResult?.version_a?.schema || {}, null, 2)}
                </pre>
              </div>
              <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="policy-diff-after">
                <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="policy-diff-after-title">After</p>
                <pre className="mt-2 max-h-80 overflow-auto text-xs text-slate-200" data-testid="policy-diff-after-json">
                  {JSON.stringify(diffResult?.version_b?.schema || {}, null, 2)}
                </pre>
              </div>
            </div>
          )}

          {diffResult && (
            <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="policy-diff-changes">
              <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="policy-diff-changes-title">Değişim Listesi</p>
              <div className="mt-2 space-y-2">
                {(diffResult?.changes || []).length === 0 && (
                  <p className="text-xs text-slate-500" data-testid="policy-diff-changes-empty">Fark bulunamadı.</p>
                )}
                {(diffResult?.changes || []).map((change, idx) => {
                  const riskColor = change.risk_impact === "🔴"
                    ? "border-red-700/70 bg-red-900/30"
                    : change.risk_impact === "🟢"
                    ? "border-emerald-700/70 bg-emerald-900/30"
                    : "border-amber-600/70 bg-amber-900/30";
                  return (
                    <div
                      key={`${change.rule_id}-${idx}`}
                      className={`rounded border px-3 py-2 text-xs text-slate-200 ${riskColor}`}
                      data-testid={`policy-diff-change-${idx}`}
                    >
                      <p className="text-xs" data-testid={`policy-diff-change-rule-${idx}`}>rule: {change.rule_id}</p>
                      <p className="text-[11px]" data-testid={`policy-diff-change-risk-${idx}`}>risk: {change.risk_impact}</p>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === "simulation" && (
        <div className="space-y-4" data-testid="execution-policies-simulation-panel">
          <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="policy-sim-form">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="policy-sim-title">Policy Simulation</p>
                <p className="text-xs text-slate-500" data-testid="policy-sim-subtitle">Tek order intent · production metrik yazılmaz.</p>
              </div>
              <Button
                className="bg-emerald-500 text-slate-950 hover:bg-emerald-400"
                onClick={handleSimulationRun}
                disabled={isSimulationRunning}
                data-testid="policy-sim-run-button"
              >
                Simulate
              </Button>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-3" data-testid="policy-sim-meta">
              <div className="space-y-1">
                <label className="text-xs text-slate-400" data-testid="policy-sim-version-label">Version</label>
                <select
                  className="w-full rounded border border-slate-800 bg-slate-950 px-2 py-2 text-xs text-slate-100"
                  value={simulationVersionId}
                  onChange={(event) => setSimulationVersionId(event.target.value)}
                  data-testid="policy-sim-version-select"
                >
                  <option value="">Version seçin</option>
                  {policyVersions.map((version) => (
                    <option key={version.version_id} value={version.version_id}>
                      {version.policy_code} · v{version.version_number}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-xs text-slate-400" data-testid="policy-sim-environment-label">Environment</label>
                <select
                  className="w-full rounded border border-slate-800 bg-slate-950 px-2 py-2 text-xs text-slate-100"
                  value={simulationEnvironment}
                  onChange={(event) => setSimulationEnvironment(event.target.value)}
                  data-testid="policy-sim-environment-select"
                >
                  {ACTIVATION_ENVIRONMENTS.map((env) => (
                    <option key={env} value={env}>{env}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-xs text-slate-400" data-testid="policy-sim-risk-class-label">Risk Class</label>
                <select
                  className="w-full rounded border border-slate-800 bg-slate-950 px-2 py-2 text-xs text-slate-100"
                  value={simulationRiskClass}
                  onChange={(event) => setSimulationRiskClass(event.target.value)}
                  data-testid="policy-sim-risk-class-select"
                >
                  {RISK_CLASSES.map((risk) => (
                    <option key={risk} value={risk}>{risk}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2" data-testid="policy-sim-json-inputs">
              <input
                className="w-full rounded border border-slate-800 bg-slate-950 px-3 py-2 text-xs text-slate-100"
                value={simulationStrategy}
                onChange={(event) => setSimulationStrategy(event.target.value)}
                placeholder="strategy_id"
                data-testid="policy-sim-strategy-input"
              />
              <div className="text-[11px] text-slate-500" data-testid="policy-sim-notes">JSON'da exposure, pnl, drawdown, leverage, margin_utilization, volatility girin.</div>
              <textarea
                className="min-h-[140px] w-full rounded border border-slate-800 bg-slate-950 px-3 py-2 text-xs text-slate-100"
                value={simulationOrderJson}
                onChange={(event) => setSimulationOrderJson(event.target.value)}
                data-testid="policy-sim-order-json"
              />
              <textarea
                className="min-h-[140px] w-full rounded border border-slate-800 bg-slate-950 px-3 py-2 text-xs text-slate-100"
                value={simulationMarketJson}
                onChange={(event) => setSimulationMarketJson(event.target.value)}
                data-testid="policy-sim-market-json"
              />
            </div>
          </div>

          <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="policy-sim-result-panel">
            <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="policy-sim-result-title">Simulation Result</p>
            {!simulationResult && (
              <p className="mt-2 text-xs text-slate-500" data-testid="policy-sim-result-empty">Simülasyon çıktısı yok.</p>
            )}
            {simulationResult && (
              <div className="mt-3 space-y-2" data-testid="policy-sim-result-body">
                <p className="text-sm text-slate-200" data-testid="policy-sim-result-decision">decision: {simulationResult?.simulation?.decision}</p>
                <p className="text-xs text-slate-400" data-testid="policy-sim-result-action">action: {simulationResult?.simulation?.action}</p>
                <p className="text-xs text-slate-400" data-testid="policy-sim-result-severity">severity: {simulationResult?.simulation?.severity}</p>
                <div className="mt-2 space-y-1" data-testid="policy-sim-result-triggers">
                  {(simulationResult?.simulation?.triggered_rules || []).length === 0 && (
                    <p className="text-xs text-slate-500" data-testid="policy-sim-result-triggers-empty">Tetiklenen rule yok.</p>
                  )}
                  {(simulationResult?.simulation?.triggered_rules || []).map((item, idx) => (
                    <p key={`${item.rule_id}-${idx}`} className="text-xs text-slate-200" data-testid={`policy-sim-trigger-${idx}`}>
                      {item.rule_id} · {item.action} · {item.severity}
                    </p>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === "bulk" && (
        <div className="space-y-4" data-testid="execution-policies-bulk-panel">
          <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="bulk-activate-panel">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="bulk-activate-title">Bulk Activate</p>
                <p className="text-xs text-slate-500" data-testid="bulk-activate-subtitle">Version ID listesi (satır başı).</p>
              </div>
              <Button
                className="bg-emerald-500 text-slate-950 hover:bg-emerald-400"
                onClick={handleBulkActivate}
                disabled={isBulkActivateRunning}
                data-testid="bulk-activate-run-button"
              >
                Run
              </Button>
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-3" data-testid="bulk-activate-form">
              <textarea
                className="min-h-[120px] w-full rounded border border-slate-800 bg-slate-950 px-3 py-2 text-xs text-slate-100 md:col-span-2"
                value={bulkActivateVersions}
                onChange={(event) => setBulkActivateVersions(event.target.value)}
                placeholder="version_id_1
version_id_2"
                data-testid="bulk-activate-versions-textarea"
              />
              <div className="space-y-2">
                <select
                  className="w-full rounded border border-slate-800 bg-slate-950 px-2 py-2 text-xs text-slate-100"
                  value={bulkActivateEnvironment}
                  onChange={(event) => setBulkActivateEnvironment(event.target.value)}
                  data-testid="bulk-activate-environment-select"
                >
                  {ACTIVATION_ENVIRONMENTS.map((env) => (
                    <option key={env} value={env}>{env}</option>
                  ))}
                </select>
                <select
                  className="w-full rounded border border-slate-800 bg-slate-950 px-2 py-2 text-xs text-slate-100"
                  value={bulkActivateMode}
                  onChange={(event) => setBulkActivateMode(event.target.value)}
                  data-testid="bulk-activate-mode-select"
                >
                  <option value="ACTIVE">ACTIVE</option>
                  <option value="CANARY">CANARY</option>
                </select>
                <label className="flex items-center gap-2 text-xs text-slate-200" data-testid="bulk-activate-override-toggle">
                  <input
                    type="checkbox"
                    checked={bulkActivateOverride}
                    onChange={(event) => setBulkActivateOverride(event.target.checked)}
                    data-testid="bulk-activate-override-checkbox"
                  />
                  High-risk override
                </label>
                <input
                  className="w-full rounded border border-slate-800 bg-slate-950 px-2 py-2 text-xs text-slate-100"
                  value={bulkActivateReason}
                  onChange={(event) => setBulkActivateReason(event.target.value)}
                  placeholder="override reason"
                  data-testid="bulk-activate-override-reason"
                />
              </div>
            </div>
            <div className="mt-3" data-testid="bulk-activate-results">
              {bulkActivateResult?.summary && (
                <p className="text-xs text-slate-300" data-testid="bulk-activate-summary">
                  total={bulkActivateResult.summary.total} · success={bulkActivateResult.summary.success} · failed={bulkActivateResult.summary.failed}
                </p>
              )}
              {(bulkActivateResult?.results || []).map((item, idx) => (
                <p key={`${item.version_id}-${idx}`} className="text-xs text-slate-400" data-testid={`bulk-activate-result-${idx}`}>
                  {item.version_id} · {item.status} {item.error ? `(${item.error})` : ""}
                </p>
              ))}
            </div>
          </div>

          <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="bulk-rollback-panel">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="bulk-rollback-title">Bulk Rollback</p>
                <p className="text-xs text-slate-500" data-testid="bulk-rollback-subtitle">policy_code + target_version_id + reason</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  className="border border-slate-700 bg-transparent text-xs text-slate-200 hover:border-emerald-400"
                  onClick={() => setBulkRollbackItems((prev) => [...prev, { policy_code: "", target_version_id: "", reason: "" }])}
                  data-testid="bulk-rollback-add-row"
                >
                  Add Row
                </Button>
                <Button
                  className="bg-emerald-500 text-slate-950 hover:bg-emerald-400"
                  onClick={handleBulkRollback}
                  disabled={isBulkRollbackRunning}
                  data-testid="bulk-rollback-run-button"
                >
                  Run
                </Button>
              </div>
            </div>
            <div className="mt-3 space-y-2" data-testid="bulk-rollback-rows">
              {bulkRollbackItems.map((row, idx) => (
                <div key={`rollback-${idx}`} className="grid gap-2 md:grid-cols-[1.2fr,1.2fr,1fr,auto]" data-testid={`bulk-rollback-row-${idx}`}>
                  <input
                    className="rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-100"
                    value={row.policy_code}
                    onChange={(event) => {
                      const next = [...bulkRollbackItems];
                      next[idx] = { ...next[idx], policy_code: event.target.value };
                      setBulkRollbackItems(next);
                    }}
                    placeholder="policy_code"
                    data-testid={`bulk-rollback-policy-code-${idx}`}
                  />
                  <input
                    className="rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-100"
                    value={row.target_version_id}
                    onChange={(event) => {
                      const next = [...bulkRollbackItems];
                      next[idx] = { ...next[idx], target_version_id: event.target.value };
                      setBulkRollbackItems(next);
                    }}
                    placeholder="target_version_id"
                    data-testid={`bulk-rollback-version-id-${idx}`}
                  />
                  <input
                    className="rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-100"
                    value={row.reason}
                    onChange={(event) => {
                      const next = [...bulkRollbackItems];
                      next[idx] = { ...next[idx], reason: event.target.value };
                      setBulkRollbackItems(next);
                    }}
                    placeholder="reason"
                    data-testid={`bulk-rollback-reason-${idx}`}
                  />
                  <Button
                    className="border border-slate-700 bg-transparent text-xs text-slate-200 hover:border-red-400"
                    onClick={() => setBulkRollbackItems((prev) => prev.filter((_, rowIdx) => rowIdx !== idx))}
                    data-testid={`bulk-rollback-remove-${idx}`}
                  >
                    Sil
                  </Button>
                </div>
              ))}
            </div>
            <div className="mt-3" data-testid="bulk-rollback-results">
              {bulkRollbackResult?.summary && (
                <p className="text-xs text-slate-300" data-testid="bulk-rollback-summary">
                  total={bulkRollbackResult.summary.total} · success={bulkRollbackResult.summary.success} · failed={bulkRollbackResult.summary.failed}
                </p>
              )}
              {(bulkRollbackResult?.results || []).map((item, idx) => (
                <p key={`${item.policy_code}-${idx}`} className="text-xs text-slate-400" data-testid={`bulk-rollback-result-${idx}`}>
                  {item.policy_code} · {item.status} {item.error ? `(${item.error})` : ""}
                </p>
              ))}
            </div>
          </div>

          <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="bulk-binding-panel">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="bulk-binding-title">Bulk Strategy Binding</p>
                <p className="text-xs text-slate-500" data-testid="bulk-binding-subtitle">strategy_id + bound_policy_set</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  className="border border-slate-700 bg-transparent text-xs text-slate-200 hover:border-emerald-400"
                  onClick={() => setBulkBindingItems((prev) => [
                    ...prev,
                    {
                      strategy_id: "",
                      bound_policy_set: "",
                      risk_class: "MEDIUM",
                      execution_mode: "SIMULATION",
                      state: "enabled",
                      enabled: true,
                    },
                  ])}
                  data-testid="bulk-binding-add-row"
                >
                  Add Row
                </Button>
                <Button
                  className="bg-emerald-500 text-slate-950 hover:bg-emerald-400"
                  onClick={handleBulkBinding}
                  disabled={isBulkBindingRunning}
                  data-testid="bulk-binding-run-button"
                >
                  Run
                </Button>
              </div>
            </div>
            <div className="mt-3 space-y-2" data-testid="bulk-binding-rows">
              {bulkBindingItems.map((row, idx) => (
                <div key={`binding-${idx}`} className="grid gap-2 md:grid-cols-[1.2fr,1.2fr,0.8fr,0.8fr,0.8fr,auto]" data-testid={`bulk-binding-row-${idx}`}>
                  <input
                    className="rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-100"
                    value={row.strategy_id}
                    onChange={(event) => {
                      const next = [...bulkBindingItems];
                      next[idx] = { ...next[idx], strategy_id: event.target.value };
                      setBulkBindingItems(next);
                    }}
                    placeholder="strategy_id"
                    data-testid={`bulk-binding-strategy-id-${idx}`}
                  />
                  <input
                    className="rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-100"
                    value={row.bound_policy_set}
                    onChange={(event) => {
                      const next = [...bulkBindingItems];
                      next[idx] = { ...next[idx], bound_policy_set: event.target.value };
                      setBulkBindingItems(next);
                    }}
                    placeholder="policy_set"
                    data-testid={`bulk-binding-policy-set-${idx}`}
                  />
                  <select
                    className="rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-100"
                    value={row.risk_class}
                    onChange={(event) => {
                      const next = [...bulkBindingItems];
                      next[idx] = { ...next[idx], risk_class: event.target.value };
                      setBulkBindingItems(next);
                    }}
                    data-testid={`bulk-binding-risk-class-${idx}`}
                  >
                    {RISK_CLASSES.map((risk) => (
                      <option key={risk} value={risk}>{risk}</option>
                    ))}
                  </select>
                  <select
                    className="rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-100"
                    value={row.execution_mode}
                    onChange={(event) => {
                      const next = [...bulkBindingItems];
                      next[idx] = { ...next[idx], execution_mode: event.target.value };
                      setBulkBindingItems(next);
                    }}
                    data-testid={`bulk-binding-execution-mode-${idx}`}
                  >
                    <option value="SIMULATION">SIMULATION</option>
                    <option value="REAL">REAL</option>
                  </select>
                  <select
                    className="rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-100"
                    value={row.state}
                    onChange={(event) => {
                      const next = [...bulkBindingItems];
                      next[idx] = { ...next[idx], state: event.target.value };
                      setBulkBindingItems(next);
                    }}
                    data-testid={`bulk-binding-state-${idx}`}
                  >
                    <option value="enabled">enabled</option>
                    <option value="disabled">disabled</option>
                  </select>
                  <label className="flex items-center gap-2 text-xs text-slate-200" data-testid={`bulk-binding-enabled-${idx}`}>
                    <input
                      type="checkbox"
                      checked={row.enabled}
                      onChange={(event) => {
                        const next = [...bulkBindingItems];
                        next[idx] = { ...next[idx], enabled: event.target.checked };
                        setBulkBindingItems(next);
                      }}
                    />
                    enabled
                  </label>
                </div>
              ))}
            </div>
            <div className="mt-3" data-testid="bulk-binding-results">
              {bulkBindingResult?.summary && (
                <p className="text-xs text-slate-300" data-testid="bulk-binding-summary">
                  total={bulkBindingResult.summary.total} · success={bulkBindingResult.summary.success} · failed={bulkBindingResult.summary.failed}
                </p>
              )}
              {(bulkBindingResult?.results || []).map((item, idx) => (
                <p key={`${item.strategy_id}-${idx}`} className="text-xs text-slate-400" data-testid={`bulk-binding-result-${idx}`}>
                  {item.strategy_id} · {item.status} {item.error ? `(${item.error})` : ""}
                </p>
              ))}
            </div>
          </div>
        </div>
      )}

      {activeTab === "overview" && (
        <div className="space-y-4" data-testid="execution-policies-overview-panel">
          <div className="rounded border border-red-700/70 bg-slate-900 p-4" data-testid="execution-policies-remediation-panel">
            <div className="flex flex-wrap items-center justify-between gap-2" data-testid="execution-policies-remediation-header">
              <p className="text-xs uppercase tracking-widest text-red-300" data-testid="execution-policies-remediation-title">System Config · Release Gate Remediation</p>
              <Button
                className="bg-red-600 text-white hover:bg-red-700"
                onClick={() => setIsRemediationOpen(true)}
                data-testid="execution-policies-open-remediation-button"
              >
                Blokajı Çöz
              </Button>
            </div>

            <div className="mt-3 grid gap-2 text-xs text-slate-200 md:grid-cols-2" data-testid="execution-policies-remediation-status-grid">
              <p data-testid="execution-policies-remediation-release-gate-status">release_gate_status: {remediationState?.release_gate_status || "-"}</p>
              <p data-testid="execution-policies-remediation-preflight-status">preflight_status: {remediationState?.preflight_status || "-"}</p>
              <p data-testid="execution-policies-remediation-secret-status">secret_readiness_status: {remediationState?.secret_readiness_status || "-"}</p>
              <p data-testid="execution-policies-remediation-final-decision">final_release_gate_decision: {remediationState?.final_release_gate_decision || "-"}</p>
            </div>

            <div className="mt-2 space-y-1" data-testid="execution-policies-remediation-reasons-list">
              {(remediationState?.release_gate_reason_codes || []).map((item, index) => (
                <p key={`${item}-${index}`} className="font-mono text-xs text-red-200" data-testid={`execution-policies-remediation-reason-${index}`}>{item}</p>
              ))}
              {(remediationState?.release_gate_reason_codes || []).length === 0 && (
                <p className="text-xs text-slate-400" data-testid="execution-policies-remediation-reasons-empty">Aktif reason_code yok.</p>
              )}
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2" data-testid="execution-policies-grid">
            <div className="rounded border border-emerald-900/70 bg-slate-900 p-4" data-testid="execution-policies-observability-card">
              <p className="text-xs uppercase tracking-widest text-emerald-300" data-testid="execution-policies-observability-title">Policy Engine Observability</p>
              <div className="mt-3 grid gap-2 text-xs text-slate-200 md:grid-cols-2" data-testid="execution-policies-observability-metrics">
                <p data-testid="execution-policies-rollout-mode">rollout_mode: {engineConfig?.rollout_mode || "shadow"}</p>
                <p data-testid="execution-policies-log-count">decision_log_count: {observability?.decision_log_count ?? 0}</p>
                <p data-testid="execution-policies-violation-count">violation_count: {observability?.violation_count ?? 0}</p>
                <p data-testid="execution-policies-risk-breach-count">risk_breach_count: {observability?.risk_breach_metrics?.breach_count ?? 0}</p>
                <p data-testid="execution-policies-execution-stage-violation-count">execution_stage_violation_count: {observability?.execution_stage_violation_count ?? 0}</p>
                <p data-testid="execution-policies-post-trade-violation-count">post_trade_violation_count: {observability?.post_trade_violation_count ?? 0}</p>
                <p data-testid="execution-policies-failsafe-hard-block-count">failsafe_hard_block_count: {observability?.failsafe_hard_block_count ?? 0}</p>
                <p data-testid="execution-policies-pretrade-total">pre_trade_total: {observability?.pre_post_ratio?.pre_trade_total ?? 0}</p>
                <p data-testid="execution-policies-posttrade-total">post_trade_total: {observability?.pre_post_ratio?.post_trade_total ?? 0}</p>
              </div>

              <div className="mt-3 space-y-2" data-testid="execution-policies-stage-rates">
                {Object.entries(observability?.stage_decision_rates || {}).length === 0 && (
                  <p className="text-xs text-slate-400" data-testid="execution-policies-stage-rates-empty">Stage karar oranı verisi yok.</p>
                )}
                {Object.entries(observability?.stage_decision_rates || {}).map(([stage, values]) => (
                  <article key={stage} className="rounded border border-slate-800 p-2" data-testid={`execution-policies-stage-rate-${stage}`}>
                    <p className="text-xs uppercase tracking-wider text-slate-300" data-testid={`execution-policies-stage-rate-title-${stage}`}>{stage}</p>
                    <p className="text-[11px] text-slate-400" data-testid={`execution-policies-stage-rate-allow-${stage}`}>allow_rate: {values?.allow_rate ?? 0}</p>
                    <p className="text-[11px] text-slate-400" data-testid={`execution-policies-stage-rate-block-${stage}`}>block_rate: {values?.block_rate ?? 0}</p>
                  </article>
                ))}
              </div>

              <div className="mt-3" data-testid="execution-policies-top-reason-codes">
                <p className="text-xs uppercase tracking-wider text-slate-400" data-testid="execution-policies-top-reason-codes-title">Top Reason Codes</p>
                {topReasonCodes.length === 0 && <p className="text-[11px] text-slate-500" data-testid="execution-policies-top-reason-codes-empty">Veri yok.</p>}
                {topReasonCodes.slice(0, 5).map((item, idx) => (
                  <p key={`${item.reason_code}-${idx}`} className="text-[11px] text-slate-300" data-testid={`execution-policies-top-reason-code-${idx}`}>
                    {item.reason_code}: {item.count}
                  </p>
                ))}
              </div>

              <div className="mt-3" data-testid="execution-policies-severity-distribution">
                <p className="text-xs uppercase tracking-wider text-slate-400" data-testid="execution-policies-severity-distribution-title">Severity Distribution (24h)</p>
                {Object.keys(severityDistribution).length === 0 && <p className="text-[11px] text-slate-500" data-testid="execution-policies-severity-distribution-empty">Veri yok.</p>}
                {Object.entries(severityDistribution).map(([key, value], idx) => (
                  <p key={`${key}-${idx}`} className="text-[11px] text-slate-300" data-testid={`execution-policies-severity-distribution-row-${idx}`}>{key}: {value}</p>
                ))}
              </div>
            </div>

            <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-registry-card">
              <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="execution-policies-registry-title">Registry</p>
              <pre className="mt-3 overflow-x-auto text-xs text-slate-200" data-testid="execution-policies-registry-json">{JSON.stringify(registry, null, 2)}</pre>
            </div>

            <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-violations-card">
              <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="execution-policies-violations-title">Recent Violations</p>
              <div className="mt-3 space-y-3" data-testid="execution-policies-violations-list">
                {violations.length === 0 && <p className="text-sm text-slate-400" data-testid="execution-policies-violations-empty">Policy ihlali kaydı yok.</p>}
                {violations.map((item) => (
                  <article key={`${item.entity_id}-${item.created_at}`} className="rounded border border-slate-800 p-3" data-testid="execution-policies-violation-row">
                    <p className="text-xs text-slate-400" data-testid="execution-policies-violation-entity">intent: {item.entity_id}</p>
                    <p className="mt-1 text-xs text-slate-400" data-testid="execution-policies-violation-time">{new Date(item.created_at).toLocaleString()}</p>
                    <pre className="mt-2 overflow-x-auto text-[11px] text-slate-200" data-testid="execution-policies-violation-details">{JSON.stringify(item.details, null, 2)}</pre>
                  </article>
                ))}
              </div>
            </div>
          </div>

          <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-decision-log-card">
            <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="execution-policies-decision-log-title">Policy Decision Log</p>
            <div className="mt-3 space-y-2" data-testid="execution-policies-decision-log-list">
              {decisionLog.length === 0 && <p className="text-sm text-slate-400" data-testid="execution-policies-decision-log-empty">Policy decision log kaydı yok.</p>}
              {decisionLog.slice(0, 12).map((item, index) => (
                <article key={`${item.id}-${index}`} className="rounded border border-slate-800 p-3" data-testid={`execution-policies-decision-log-row-${index}`}>
                  <p className="text-xs text-slate-300" data-testid={`execution-policies-decision-log-stage-${index}`}>{item.stage} · {item.enforced_action}</p>
                  <p className="text-[11px] text-slate-400" data-testid={`execution-policies-decision-log-reason-${index}`}>reason_code: {item.reason_code || "-"}</p>
                  <p className="text-[11px] text-slate-400" data-testid={`execution-policies-decision-log-time-${index}`}>{item.created_at ? new Date(item.created_at).toLocaleString() : "-"}</p>
                </article>
              ))}
            </div>
          </div>

          <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-critical-violations-card">
            <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="execution-policies-critical-violations-title">Recent Critical Violations</p>
            <div className="mt-3 space-y-2" data-testid="execution-policies-critical-violations-list">
              {criticalViolations.length === 0 && <p className="text-sm text-slate-400" data-testid="execution-policies-critical-violations-empty">Critical violation yok.</p>}
              {criticalViolations.slice(0, 8).map((item, idx) => (
                <article key={`${item.violation_id}-${idx}`} className="rounded border border-slate-800 p-3" data-testid={`execution-policies-critical-violation-row-${idx}`}>
                  <p className="text-xs text-slate-300" data-testid={`execution-policies-critical-violation-reason-${idx}`}>{item.reason_code} · {item.stage}</p>
                  <p className="text-[11px] text-slate-400" data-testid={`execution-policies-critical-violation-rule-${idx}`}>rule: {item.triggered_rule || "-"}</p>
                  <p className="text-[11px] text-slate-500" data-testid={`execution-policies-critical-violation-time-${idx}`}>{item.created_at ? new Date(item.created_at).toLocaleString() : "-"}</p>
                </article>
              ))}
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-3" data-testid="execution-policies-governance-grid">
            <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-policy-versions-card">
              <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="execution-policies-policy-versions-title">Policy Versions</p>
              {policyVersions.length === 0 && <p className="mt-2 text-sm text-slate-400" data-testid="execution-policies-policy-versions-empty">Version kaydı yok.</p>}
              <div className="mt-2 space-y-2" data-testid="execution-policies-policy-versions-list">
                {policyVersions.slice(0, 10).map((item, idx) => (
                  <article key={`${item.version_id}-${idx}`} className="rounded border border-slate-800 p-2" data-testid={`execution-policies-policy-version-row-${idx}`}>
                    <p className="text-xs text-slate-200" data-testid={`execution-policies-policy-version-code-${idx}`}>{item.policy_code}</p>
                    <p className="text-[11px] text-slate-400" data-testid={`execution-policies-policy-version-state-${idx}`}>{item.state} · {item.approval_status}</p>
                  </article>
                ))}
              </div>
            </div>

            <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-strategy-health-card">
              <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="execution-policies-strategy-health-title">Strategy Health</p>
              {strategyHealth.length === 0 && <p className="mt-2 text-sm text-slate-400" data-testid="execution-policies-strategy-health-empty">Strategy health verisi yok.</p>}
              <div className="mt-2 space-y-2" data-testid="execution-policies-strategy-health-list">
                {strategyHealth.slice(0, 10).map((item, idx) => (
                  <article key={`${item.strategy_id}-${idx}`} className="rounded border border-slate-800 p-2" data-testid={`execution-policies-strategy-health-row-${idx}`}>
                    <p className="text-xs text-slate-200" data-testid={`execution-policies-strategy-health-id-${idx}`}>{item.strategy_id}</p>
                    <p className="text-[11px] text-slate-400" data-testid={`execution-policies-strategy-health-state-${idx}`}>{item.state} · risk={item.risk_class}</p>
                    <p className="text-[11px] text-slate-500" data-testid={`execution-policies-strategy-health-violations-${idx}`}>violations={item.violation_count}</p>
                  </article>
                ))}
              </div>
            </div>

            <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-release-gate-card">
              <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="execution-policies-release-gate-title">Release Gate</p>
              <p className="mt-2 text-sm text-slate-200" data-testid="execution-policies-release-gate-status">status: {releaseGate?.status || "UNKNOWN"}</p>
              <p className="text-[11px] text-slate-400" data-testid="execution-policies-release-gate-summary">critical: {releaseGate?.summary?.critical_violation_count ?? 0} · failsafe: {releaseGate?.summary?.failsafe_hard_block_count ?? 0}</p>
              <div className="mt-2" data-testid="execution-policies-release-gate-recommendations">
                <p className="text-[11px] uppercase tracking-wider text-slate-400" data-testid="execution-policies-release-gate-recommendations-title">Recommended Actions</p>
                {(releaseGate?.recommended_actions || []).slice(0, 5).map((item, idx) => (
                  <p key={`${idx}-${item}`} className="text-[11px] text-slate-300" data-testid={`execution-policies-release-gate-recommendation-${idx}`}>- {item}</p>
                ))}
              </div>
            </div>
          </div>

          <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-remediation-card">
            <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="execution-policies-remediation-title">Remediation Recommendations</p>
            {remediationRecommendations.length === 0 && <p className="mt-2 text-sm text-slate-400" data-testid="execution-policies-remediation-empty">Öneri yok.</p>}
            <div className="mt-2 space-y-2" data-testid="execution-policies-remediation-list">
              {remediationRecommendations.slice(0, 10).map((item, idx) => (
                <article key={`${item.recommendation_id}-${idx}`} className="rounded border border-slate-800 p-2" data-testid={`execution-policies-remediation-row-${idx}`}>
                  <p className="text-xs text-slate-200" data-testid={`execution-policies-remediation-type-${idx}`}>{item.recommendation_type} · {item.status}</p>
                  <p className="text-[11px] text-slate-400" data-testid={`execution-policies-remediation-reason-${idx}`}>{item.reason_code || "-"}</p>
                  <p className="text-[11px] text-slate-500" data-testid={`execution-policies-remediation-summary-${idx}`}>{item.summary}</p>
                </article>
              ))}
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2" data-testid="execution-policies-environment-safe-mode-grid">
            <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-environment-overrides-card">
              <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="execution-policies-environment-overrides-title">Environment Overrides</p>
              {environmentOverrides.length === 0 && <p className="mt-2 text-sm text-slate-400" data-testid="execution-policies-environment-overrides-empty">Override tanımı yok.</p>}
              <div className="mt-2 space-y-2" data-testid="execution-policies-environment-overrides-list">
                {environmentOverrides.slice(0, 10).map((item, idx) => (
                  <article key={`${item.override_id}-${idx}`} className="rounded border border-slate-800 p-2" data-testid={`execution-policies-environment-override-row-${idx}`}>
                    <p className="text-xs text-slate-200" data-testid={`execution-policies-environment-override-env-${idx}`}>{item.environment} · {item.scope_type}</p>
                    <p className="text-[11px] text-slate-400" data-testid={`execution-policies-environment-override-scope-${idx}`}>{item.scope_value} · priority={item.priority}</p>
                  </article>
                ))}
              </div>
            </div>

            <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-safe-mode-card">
              <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="execution-policies-safe-mode-title">Safe Mode Visibility</p>
              {safeModeStates.length === 0 && <p className="mt-2 text-sm text-slate-400" data-testid="execution-policies-safe-mode-empty">Safe mode kaydı yok.</p>}
              <div className="mt-2 space-y-2" data-testid="execution-policies-safe-mode-list">
                {safeModeStates.slice(0, 10).map((item, idx) => (
                  <article key={`${item.safe_mode_id}-${idx}`} className="rounded border border-slate-800 p-2" data-testid={`execution-policies-safe-mode-row-${idx}`}>
                    <p className="text-xs text-slate-200" data-testid={`execution-policies-safe-mode-state-${idx}`}>{item.environment} · {item.scope_type} · {item.is_active ? "ACTIVE" : "INACTIVE"}</p>
                    <p className="text-[11px] text-slate-400" data-testid={`execution-policies-safe-mode-reason-${idx}`}>{item.trigger_reason}</p>
                    <p className="text-[11px] text-slate-500" data-testid={`execution-policies-safe-mode-time-${idx}`}>{item.activated_at ? new Date(item.activated_at).toLocaleString() : "-"}</p>
                  </article>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      <ProdConfigRemediationModal
        open={isRemediationOpen}
        onOpenChange={setIsRemediationOpen}
        remediationState={remediationState}
        onSaved={(nextState) => setRemediationState(nextState)}
        testIdPrefix="execution-policies"
      />
    </section>
  );
};
