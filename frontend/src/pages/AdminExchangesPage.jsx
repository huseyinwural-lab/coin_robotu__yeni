import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

const exchangeSeedForm = {
  exchange_code: "",
  exchange_name: "",
  status: "active",
  spot: true,
  futures: true,
  supports_testnet: true,
  supports_live: false,
  health_status: "healthy",
  rate_limit_status: "ok",
  adapter_version: "v1",
};

const capabilitySeedForm = {
  exchange_code: "binance",
  market_type: "spot",
  supports_spot: true,
  supports_futures: false,
  supports_test_order: true,
  supports_quote_qty: true,
  supports_reduce_only: false,
  supports_leverage: false,
  supports_margin_mode: false,
  supports_hedge_mode: false,
};

const allowedMarketSeedForm = {
  exchange_code: "binance",
  market_type: "spot",
  environment: "testnet",
  enabled: true,
};

const assignmentSeedForm = {
  user_id: "",
  exchange_code: "binance",
  spot_allowed: true,
  futures_allowed: true,
  testnet_allowed: true,
  live_allowed: false,
};

const executionCredentialSeedForm = {
  bybit_api_key: "",
  bybit_secret: "",
  bybit_testnet_api_key: "",
  bybit_testnet_secret: "",
  bybit_live_api_key: "",
  bybit_live_secret: "",
  okx_api_key: "",
  okx_secret: "",
  okx_passphrase: "",
};

const routingPreviewSeedForm = {
  user_id: "",
  strategy_id: "",
  symbol: "BTCUSDT",
  market_type: "spot",
  environment: "testnet",
  order_side: "BUY",
  order_size_usd: 100,
};

const boolLabel = (value) => (value ? "true" : "false");

export const AdminExchangesPage = () => {
  const [loading, setLoading] = useState(true);
  const [exchanges, setExchanges] = useState([]);
  const [capabilities, setCapabilities] = useState([]);
  const [allowedMarkets, setAllowedMarkets] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [approvedUsers, setApprovedUsers] = useState([]);
  const [healthSummary, setHealthSummary] = useState(null);
  const [executionCredentials, setExecutionCredentials] = useState(null);
  const [executionValidation, setExecutionValidation] = useState(null);
  const [controlPlaneSanity, setControlPlaneSanity] = useState(null);
  const [capabilityDiscovery, setCapabilityDiscovery] = useState(null);
  const [marketPolicyLayer, setMarketPolicyLayer] = useState(null);
  const [routingPreview, setRoutingPreview] = useState(null);
  const [operationalHealth, setOperationalHealth] = useState(null);
  const [auditTimeline, setAuditTimeline] = useState([]);

  const [exchangeDrafts, setExchangeDrafts] = useState({});
  const [capabilityDrafts, setCapabilityDrafts] = useState({});

  const [exchangeForm, setExchangeForm] = useState(exchangeSeedForm);
  const [capabilityForm, setCapabilityForm] = useState(capabilitySeedForm);
  const [allowedMarketForm, setAllowedMarketForm] = useState(allowedMarketSeedForm);
  const [assignmentForm, setAssignmentForm] = useState(assignmentSeedForm);
  const [executionCredentialForm, setExecutionCredentialForm] = useState(executionCredentialSeedForm);
  const [routingPreviewForm, setRoutingPreviewForm] = useState(routingPreviewSeedForm);

  const exchangeCodes = useMemo(() => exchanges.map((item) => item.exchange_code), [exchanges]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [
        exchangesRes,
        capabilitiesRes,
        allowedMarketsRes,
        assignmentsRes,
        usersRes,
        healthRes,
        credentialsRes,
      ] = await Promise.all([
        apiClient.get("/venues/admin/exchanges"),
        apiClient.get("/venues/admin/capabilities"),
        apiClient.get("/venues/admin/allowed-markets"),
        apiClient.get("/venues/admin/user-assignments"),
        apiClient.get("/auth/admin/user-approval-requests?status=approved"),
        apiClient.get("/venues/admin/health-summary"),
        apiClient.get("/venues/admin/execution-credentials"),
      ]);

      const nextExchanges = exchangesRes.data || [];
      const nextCapabilities = capabilitiesRes.data || [];

      setExchanges(nextExchanges);
      setCapabilities(nextCapabilities);
      setAllowedMarkets(allowedMarketsRes.data || []);
      setAssignments(assignmentsRes.data || []);
      setApprovedUsers(usersRes.data || []);
      setHealthSummary(healthRes.data || null);
      setExecutionCredentials(credentialsRes.data || null);
      await Promise.all([loadMarketPolicyLayer(), loadOperationalHealth(), loadAuditTimeline()]);

      setExchangeDrafts(
        Object.fromEntries(
          nextExchanges.map((row) => [
            row.exchange_code,
            {
              status: row.status,
              health_status: row.health_status,
              rate_limit_status: row.rate_limit_status,
              adapter_version: row.adapter_version,
            },
          ]),
        ),
      );

      setCapabilityDrafts(
        Object.fromEntries(
          nextCapabilities.map((row) => [
            row.id,
            {
              supports_test_order: row.supports_test_order,
              supports_quote_qty: row.supports_quote_qty,
              supports_reduce_only: row.supports_reduce_only,
              supports_leverage: row.supports_leverage,
              supports_margin_mode: row.supports_margin_mode,
              supports_hedge_mode: row.supports_hedge_mode,
            },
          ]),
        ),
      );
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Venue yönetim verileri yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const updateExchangeDraft = (exchangeCode, key, value) => {
    setExchangeDrafts((prev) => ({ ...prev, [exchangeCode]: { ...(prev[exchangeCode] || {}), [key]: value } }));
  };

  const updateCapabilityDraft = (id, key, value) => {
    setCapabilityDrafts((prev) => ({ ...prev, [id]: { ...(prev[id] || {}), [key]: value } }));
  };

  const createExchange = async (event) => {
    event.preventDefault();
    try {
      await apiClient.post("/venues/admin/exchanges", {
        exchange_code: exchangeForm.exchange_code,
        exchange_name: exchangeForm.exchange_name,
        status: exchangeForm.status,
        supported_market_types: [exchangeForm.spot ? "spot" : "", exchangeForm.futures ? "futures" : ""].filter(Boolean),
        supports_testnet: exchangeForm.supports_testnet,
        supports_live: exchangeForm.supports_live,
        health_status: exchangeForm.health_status,
        rate_limit_status: exchangeForm.rate_limit_status,
        adapter_version: exchangeForm.adapter_version,
      });
      toast.success("Exchange kaydı eklendi");
      setExchangeForm(exchangeSeedForm);
      await loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Exchange oluşturulamadı");
    }
  };

  const updateExchange = async (exchangeCode) => {
    try {
      await apiClient.patch(`/venues/admin/exchanges/${exchangeCode}`, exchangeDrafts[exchangeCode]);
      toast.success("Exchange güncellendi");
      await loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Exchange güncellenemedi");
    }
  };

  const deleteExchange = async (exchangeCode) => {
    if (!window.confirm(`${exchangeCode} silinsin mi?`)) {
      return;
    }
    try {
      await apiClient.delete(`/venues/admin/exchanges/${exchangeCode}`);
      toast.success("Exchange silindi");
      await loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Exchange silinemedi");
    }
  };

  const createCapability = async (event) => {
    event.preventDefault();
    try {
      await apiClient.post("/venues/admin/capabilities", capabilityForm);
      toast.success("Capability eklendi");
      setCapabilityForm({ ...capabilitySeedForm, exchange_code: exchangeCodes[0] || "binance" });
      await loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Capability oluşturulamadı");
    }
  };

  const updateCapability = async (id) => {
    try {
      await apiClient.put(`/venues/admin/capabilities/${id}`, capabilityDrafts[id]);
      toast.success("Capability güncellendi");
      await loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Capability güncellenemedi");
    }
  };

  const deleteCapability = async (id) => {
    if (!window.confirm("Capability kaydı silinsin mi?")) {
      return;
    }
    try {
      await apiClient.delete(`/venues/admin/capabilities/${id}`);
      toast.success("Capability silindi");
      await loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Capability silinemedi");
    }
  };

  const createAllowedMarket = async (event) => {
    event.preventDefault();
    try {
      await apiClient.post("/venues/admin/allowed-markets", allowedMarketForm);
      toast.success("Allowed market eklendi");
      setAllowedMarketForm({ ...allowedMarketSeedForm, exchange_code: exchangeCodes[0] || "binance" });
      await loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Allowed market oluşturulamadı");
    }
  };

  const toggleAllowedMarket = async (row) => {
    try {
      await apiClient.put(`/venues/admin/allowed-markets/${row.id}`, { enabled: !row.enabled });
      toast.success("Allowed market güncellendi");
      await loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Allowed market güncellenemedi");
    }
  };

  const deleteAllowedMarket = async (id) => {
    if (!window.confirm("Allowed market kaydı silinsin mi?")) {
      return;
    }
    try {
      await apiClient.delete(`/venues/admin/allowed-markets/${id}`);
      toast.success("Allowed market silindi");
      await loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Allowed market silinemedi");
    }
  };

  const upsertAssignment = async (event) => {
    event.preventDefault();
    try {
      await apiClient.put("/venues/admin/user-assignments", assignmentForm);
      toast.success("User assignment kaydedildi");
      setAssignmentForm((prev) => ({ ...assignmentSeedForm, exchange_code: prev.exchange_code || exchangeCodes[0] || "binance" }));
      await loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "User assignment kaydedilemedi");
    }
  };

  const deleteAssignment = async (id) => {
    if (!window.confirm("Assignment kaydı silinsin mi?")) {
      return;
    }
    try {
      await apiClient.delete(`/venues/admin/user-assignments/${id}`);
      toast.success("User assignment silindi");
      await loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "User assignment silinemedi");
    }
  };

  const saveExecutionCredentials = async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(
      Object.entries(executionCredentialForm).filter(([, value]) => String(value || "").trim().length > 0),
    );
    if (Object.keys(payload).length === 0) {
      toast.warning("Kaydetmek için en az bir credential alanı girin");
      return;
    }
    try {
      const response = await apiClient.patch("/venues/admin/execution-credentials", payload);
      setExecutionCredentials(response.data || null);
      setExecutionCredentialForm(executionCredentialSeedForm);
      toast.success("Exchange execution credential ayarları kaydedildi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Credential ayarları kaydedilemedi");
    }
  };

  const runExecutionValidation = async () => {
    try {
      const response = await apiClient.post("/venues/admin/execution-validation");
      setExecutionValidation(response.data || null);
      toast.success("Execution activation doğrulaması tamamlandı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Execution validation çalıştırılamadı");
    }
  };

  const runControlPlaneSanityCheck = async () => {
    try {
      const { data } = await apiClient.post("/venues/admin/control-plane-sanity-check");
      setControlPlaneSanity(data || null);
      toast.success(`Sanity check tamamlandı: ${data?.net_status || "UNKNOWN"}`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Control plane sanity check başarısız");
    }
  };

  const runCapabilityDiscovery = async () => {
    try {
      const payload = {
        ...capabilityForm,
        symbols: String(capabilityForm.symbols || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
      };
      const { data } = await apiClient.post("/venues/admin/capability-discovery", payload);
      setCapabilityDiscovery(data || null);
      toast.success("Capability discovery tamamlandı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Capability discovery başarısız");
    }
  };

  const loadMarketPolicyLayer = async () => {
    try {
      const { data } = await apiClient.get("/venues/admin/market-policy-layer");
      setMarketPolicyLayer(data || null);
    } catch {
      setMarketPolicyLayer(null);
    }
  };

  const runRoutingPreviewV2 = async () => {
    try {
      const { data } = await apiClient.post("/venues/admin/routing-preview-v2", routingPreviewForm);
      setRoutingPreview(data || null);
      toast.success(`Routing preview: ${data?.net_status || "UNKNOWN"}`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Routing preview başarısız");
    }
  };

  const loadOperationalHealth = async () => {
    try {
      const { data } = await apiClient.get("/venues/admin/operational-health");
      setOperationalHealth(data || null);
    } catch {
      setOperationalHealth(null);
    }
  };

  const loadAuditTimeline = async () => {
    try {
      const { data } = await apiClient.get("/venues/admin/audit-timeline", { params: { limit: 50 } });
      setAuditTimeline(data?.items || []);
    } catch {
      setAuditTimeline([]);
    }
  };


  return (
    <section className="space-y-4" data-testid="admin-exchanges-page">
      <header className="border border-orange-700 bg-slate-900 p-4" data-testid="admin-exchanges-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-orange-300" data-testid="admin-exchanges-title">Venue Registry & Assignments</h2>
        <p className="mt-2 text-sm text-slate-300" data-testid="admin-exchanges-description">
          Exchange registry, capability matrix, allowed market policy ve kullanıcı assignment yönetimi.
        </p>
      </header>

      <div className="grid gap-3 md:grid-cols-3" data-testid="admin-exchange-health-grid">
        <div className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-exchange-health-status-card">
          <p className="text-xs uppercase tracking-wider text-slate-400" data-testid="admin-exchange-health-title">Exchange Health</p>
          {(Object.entries(healthSummary?.exchange_health || {})).map(([key, value]) => (
            <p key={key} className="mt-1 text-sm" data-testid={`admin-exchange-health-item-${key}`}>{key}: {value}</p>
          ))}
        </div>
        <div className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-exchange-market-availability-card">
          <p className="text-xs uppercase tracking-wider text-slate-400" data-testid="admin-exchange-market-availability-title">Market Availability</p>
          {(Object.entries(healthSummary?.market_availability || {})).slice(0, 6).map(([key, value]) => (
            <p key={key} className="mt-1 text-sm" data-testid={`admin-exchange-market-availability-item-${key.replaceAll(":", "-")}`}>{key}: {boolLabel(value)}</p>
          ))}
        </div>
        <div className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-exchange-capability-mismatch-card">
          <p className="text-xs uppercase tracking-wider text-slate-400" data-testid="admin-exchange-capability-mismatch-title">Capability Mismatch</p>
          {(healthSummary?.capability_mismatch || []).length === 0 && (
            <p className="mt-1 text-sm text-emerald-300" data-testid="admin-exchange-capability-mismatch-empty">Mismatch yok</p>
          )}
          {(healthSummary?.capability_mismatch || []).map((item) => (
            <p key={item} className="mt-1 text-sm text-yellow-300" data-testid={`admin-exchange-capability-mismatch-item-${item.replace(":", "-")}`}>{item}</p>
          ))}
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2" data-testid="admin-execution-settings-grid">
        <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-execution-credential-panel">
          <p className="text-xs uppercase tracking-wider text-slate-400" data-testid="admin-execution-credential-title">Admin → Exchange Settings (Execution Activation)</p>
          <form className="grid gap-2 md:grid-cols-2" onSubmit={saveExecutionCredentials} data-testid="admin-execution-credential-form">
            <Input
              type="password"
              autoComplete="new-password"
              value={executionCredentialForm.bybit_api_key}
              onChange={(event) => setExecutionCredentialForm((prev) => ({ ...prev, bybit_api_key: event.target.value }))}
              placeholder="bybit_api_key"
              data-testid="admin-execution-bybit-api-key-input"
            />
            <Input
              type="password"
              autoComplete="new-password"
              value={executionCredentialForm.bybit_secret}
              onChange={(event) => setExecutionCredentialForm((prev) => ({ ...prev, bybit_secret: event.target.value }))}
              placeholder="bybit_secret"
              data-testid="admin-execution-bybit-secret-input"
            />
            <Input
              type="password"
              autoComplete="new-password"
              value={executionCredentialForm.bybit_testnet_api_key}
              onChange={(event) => setExecutionCredentialForm((prev) => ({ ...prev, bybit_testnet_api_key: event.target.value }))}
              placeholder="bybit_testnet_api_key"
              data-testid="admin-execution-bybit-testnet-api-key-input"
            />
            <Input
              type="password"
              autoComplete="new-password"
              value={executionCredentialForm.bybit_testnet_secret}
              onChange={(event) => setExecutionCredentialForm((prev) => ({ ...prev, bybit_testnet_secret: event.target.value }))}
              placeholder="bybit_testnet_secret"
              data-testid="admin-execution-bybit-testnet-secret-input"
            />
            <Input
              type="password"
              autoComplete="new-password"
              value={executionCredentialForm.bybit_live_api_key}
              onChange={(event) => setExecutionCredentialForm((prev) => ({ ...prev, bybit_live_api_key: event.target.value }))}
              placeholder="bybit_live_api_key"
              data-testid="admin-execution-bybit-live-api-key-input"
            />
            <Input
              type="password"
              autoComplete="new-password"
              value={executionCredentialForm.bybit_live_secret}
              onChange={(event) => setExecutionCredentialForm((prev) => ({ ...prev, bybit_live_secret: event.target.value }))}
              placeholder="bybit_live_secret"
              data-testid="admin-execution-bybit-live-secret-input"
            />
            <Input
              type="password"
              autoComplete="new-password"
              value={executionCredentialForm.okx_api_key}
              onChange={(event) => setExecutionCredentialForm((prev) => ({ ...prev, okx_api_key: event.target.value }))}
              placeholder="okx_api_key"
              data-testid="admin-execution-okx-api-key-input"
            />
            <Input
              type="password"
              autoComplete="new-password"
              value={executionCredentialForm.okx_secret}
              onChange={(event) => setExecutionCredentialForm((prev) => ({ ...prev, okx_secret: event.target.value }))}
              placeholder="okx_secret"
              data-testid="admin-execution-okx-secret-input"
            />
            <Input
              type="password"
              autoComplete="new-password"
              value={executionCredentialForm.okx_passphrase}
              onChange={(event) => setExecutionCredentialForm((prev) => ({ ...prev, okx_passphrase: event.target.value }))}
              placeholder="okx_passphrase"
              data-testid="admin-execution-okx-passphrase-input"
            />
            <div className="flex items-center gap-2 md:col-span-2" data-testid="admin-execution-credential-actions-row">
              <Button data-testid="admin-execution-credential-config-update-button">Credential Kaydet</Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => setExecutionCredentialForm(executionCredentialSeedForm)}
                data-testid="admin-execution-credential-reset-button"
              >
                Formu Temizle
              </Button>
            </div>
          </form>

          <div className="rounded border border-slate-700 p-3 text-sm" data-testid="admin-execution-credential-summary">
            <p data-testid="admin-execution-has-bybit-credentials">has_bybit_credentials: {boolLabel(Boolean(executionCredentials?.has_bybit_credentials))}</p>
            <p data-testid="admin-execution-has-bybit-testnet-credentials">has_bybit_testnet_credentials: {boolLabel(Boolean(executionCredentials?.has_bybit_testnet_credentials))}</p>
            <p data-testid="admin-execution-has-bybit-live-credentials">has_bybit_live_credentials: {boolLabel(Boolean(executionCredentials?.has_bybit_live_credentials))}</p>
            <p data-testid="admin-execution-has-okx-credentials">has_okx_credentials: {boolLabel(Boolean(executionCredentials?.has_okx_credentials))}</p>
            <p data-testid="admin-execution-masked-bybit-key">bybit_api_key: {executionCredentials?.masked?.bybit_api_key || "missing"}</p>
            <p data-testid="admin-execution-masked-bybit-secret">bybit_secret: {executionCredentials?.masked?.bybit_secret || "missing"}</p>
            <p data-testid="admin-execution-masked-bybit-testnet-key">bybit_testnet_api_key: {executionCredentials?.masked?.bybit_testnet_api_key || "missing"}</p>
            <p data-testid="admin-execution-masked-bybit-testnet-secret">bybit_testnet_secret: {executionCredentials?.masked?.bybit_testnet_secret || "missing"}</p>
            <p data-testid="admin-execution-masked-bybit-live-key">bybit_live_api_key: {executionCredentials?.masked?.bybit_live_api_key || "missing"}</p>
            <p data-testid="admin-execution-masked-bybit-live-secret">bybit_live_secret: {executionCredentials?.masked?.bybit_live_secret || "missing"}</p>
            <p data-testid="admin-execution-masked-okx-key">okx_api_key: {executionCredentials?.masked?.okx_api_key || "missing"}</p>
            <p data-testid="admin-execution-masked-okx-secret">okx_secret: {executionCredentials?.masked?.okx_secret || "missing"}</p>
            <p data-testid="admin-execution-masked-okx-passphrase">okx_passphrase: {executionCredentials?.masked?.okx_passphrase || "missing"}</p>
          </div>
        </div>

        <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-execution-validation-panel">
          <p className="text-xs uppercase tracking-wider text-slate-400" data-testid="admin-execution-validation-title">Execution Activation Validation</p>
          <Button type="button" onClick={runExecutionValidation} data-testid="admin-execution-validation-apply-button">Validation Çalıştır</Button>
          <div className="space-y-2 rounded border border-slate-700 p-3 text-sm" data-testid="admin-execution-validation-results">
            <p data-testid="admin-execution-validation-net-status">net_status: {executionValidation?.net_status || "n/a"}</p>
            <p data-testid="admin-execution-validation-adapter-smoke">adapter_smoke_test: {executionValidation?.validation?.adapter_smoke_test || "n/a"}</p>
            <p data-testid="admin-execution-validation-bybit-ready">bybit_testnet_live_ready: {executionValidation?.validation?.bybit_testnet_live_ready || "n/a"}</p>
            <p data-testid="admin-execution-validation-precision">precision_validation: {executionValidation?.validation?.precision_validation || "n/a"}</p>
            <p data-testid="admin-execution-validation-lot-size">lot_size_validation: {executionValidation?.validation?.lot_size_validation || "n/a"}</p>
            <p data-testid="admin-execution-validation-submit">order_submit_test: {executionValidation?.validation?.order_submit_test || "n/a"}</p>
            <p data-testid="admin-execution-validation-cancel">cancel_test: {executionValidation?.validation?.cancel_test || "n/a"}</p>
            <p data-testid="admin-execution-validation-retry">retry_behavior: {executionValidation?.validation?.retry_behavior || "n/a"}</p>
            <div className="space-y-1 text-xs" data-testid="admin-execution-validation-checks">
              {(executionValidation?.checks || []).map((item, index) => (
                <p key={`${item.check}-${index}`} data-testid={`admin-execution-validation-check-${index}`}>
                  {item.name || item.check}: {item.status} ({item.reason_code}) / severity: {item.severity || "n/a"}
                </p>
              ))}
            </div>
          </div>
          <p className="text-xs text-slate-400" data-testid="admin-execution-validation-note">
            Not: Execution validation gerçek endpoint sonuçlarıyla PASS/WARN/BLOCK döndürür.
          </p>
        </div>

        <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-control-plane-sanity-panel">
          <p className="text-xs uppercase tracking-wider text-slate-400" data-testid="admin-control-plane-sanity-title">Venue Control Plane Sanity Check</p>
          <Button type="button" onClick={runControlPlaneSanityCheck} data-testid="admin-control-plane-sanity-run-button">Sanity Check Çalıştır</Button>
          <div className="space-y-2 rounded border border-slate-700 p-3 text-sm" data-testid="admin-control-plane-sanity-results">
            <p data-testid="admin-control-plane-sanity-net-status">net_status: {controlPlaneSanity?.net_status || "n/a"}</p>
            <p data-testid="admin-control-plane-sanity-reason-codes">reason_codes: {(controlPlaneSanity?.reason_codes || []).join(", ") || "-"}</p>
            <p data-testid="admin-control-plane-sanity-remediation">remediation: {(controlPlaneSanity?.remediation_suggestions || []).join(" | ") || "-"}</p>
            <div className="space-y-1 text-xs" data-testid="admin-control-plane-sanity-checks-list">
              {(controlPlaneSanity?.checks || []).map((item, index) => (
                <p key={`${item.check}-${index}`} data-testid={`admin-control-plane-sanity-check-${index}`}>
                  {item.name || item.check}: {item.status} ({item.reason_code || "ok"}) / severity: {item.severity || "n/a"}
                </p>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2" data-testid="admin-exchanges-main-grid">
        <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-exchange-registry-panel">
          <p className="text-xs uppercase tracking-wider text-slate-400" data-testid="admin-exchange-registry-title">Exchange Registry CRUD</p>
          <form className="grid gap-2 md:grid-cols-2" onSubmit={createExchange} data-testid="admin-exchange-create-form">
            <Input value={exchangeForm.exchange_code} onChange={(event) => setExchangeForm((prev) => ({ ...prev, exchange_code: event.target.value }))} placeholder="exchange_code" data-testid="admin-exchange-create-code-input" required />
            <Input value={exchangeForm.exchange_name} onChange={(event) => setExchangeForm((prev) => ({ ...prev, exchange_name: event.target.value }))} placeholder="exchange_name" data-testid="admin-exchange-create-name-input" required />
            <label className="flex items-center gap-2 text-sm" data-testid="admin-exchange-create-spot-row"><input type="checkbox" checked={exchangeForm.spot} onChange={(event) => setExchangeForm((prev) => ({ ...prev, spot: event.target.checked }))} data-testid="admin-exchange-create-spot-checkbox" />spot</label>
            <label className="flex items-center gap-2 text-sm" data-testid="admin-exchange-create-futures-row"><input type="checkbox" checked={exchangeForm.futures} onChange={(event) => setExchangeForm((prev) => ({ ...prev, futures: event.target.checked }))} data-testid="admin-exchange-create-futures-checkbox" />futures</label>
            <label className="flex items-center gap-2 text-sm" data-testid="admin-exchange-create-testnet-row"><input type="checkbox" checked={exchangeForm.supports_testnet} onChange={(event) => setExchangeForm((prev) => ({ ...prev, supports_testnet: event.target.checked }))} data-testid="admin-exchange-create-testnet-checkbox" />supports_testnet</label>
            <label className="flex items-center gap-2 text-sm" data-testid="admin-exchange-create-live-row"><input type="checkbox" checked={exchangeForm.supports_live} onChange={(event) => setExchangeForm((prev) => ({ ...prev, supports_live: event.target.checked }))} data-testid="admin-exchange-create-live-checkbox" />supports_live</label>
            <Button className="md:col-span-2 bg-orange-500 text-black hover:bg-orange-600" data-testid="admin-exchange-create-submit-button">Exchange Ekle</Button>
          </form>

          {loading && <p className="text-sm text-slate-400" data-testid="admin-exchange-registry-loading">Yükleniyor...</p>}
          <div className="space-y-3" data-testid="admin-exchange-registry-list">
            {exchanges.map((row) => (
              <div key={row.id} className="border border-slate-700 p-3" data-testid={`admin-exchange-row-${row.exchange_code}`}>
                <p className="text-sm font-semibold" data-testid={`admin-exchange-row-title-${row.exchange_code}`}>{row.exchange_code} · {row.exchange_name}</p>
                <p className="text-xs text-slate-400" data-testid={`admin-exchange-row-markets-${row.exchange_code}`}>{(row.supported_market_types || []).join(", ") || "-"}</p>
                <div className="mt-2 grid gap-2 md:grid-cols-2">
                  <select value={exchangeDrafts[row.exchange_code]?.status || "active"} onChange={(event) => updateExchangeDraft(row.exchange_code, "status", event.target.value)} className="border border-slate-600 bg-slate-950 px-2 py-2 text-sm" data-testid={`admin-exchange-status-select-${row.exchange_code}`}>
                    <option value="active">active</option>
                    <option value="maintenance">maintenance</option>
                    <option value="disabled">disabled</option>
                  </select>
                  <select value={exchangeDrafts[row.exchange_code]?.health_status || "healthy"} onChange={(event) => updateExchangeDraft(row.exchange_code, "health_status", event.target.value)} className="border border-slate-600 bg-slate-950 px-2 py-2 text-sm" data-testid={`admin-exchange-health-select-${row.exchange_code}`}>
                    <option value="healthy">healthy</option>
                    <option value="degraded">degraded</option>
                    <option value="down">down</option>
                  </select>
                  <select value={exchangeDrafts[row.exchange_code]?.rate_limit_status || "ok"} onChange={(event) => updateExchangeDraft(row.exchange_code, "rate_limit_status", event.target.value)} className="border border-slate-600 bg-slate-950 px-2 py-2 text-sm" data-testid={`admin-exchange-rate-limit-select-${row.exchange_code}`}>
                    <option value="ok">ok</option>
                    <option value="warning">warning</option>
                    <option value="throttled">throttled</option>
                  </select>
                  <Input value={exchangeDrafts[row.exchange_code]?.adapter_version || "v1"} onChange={(event) => updateExchangeDraft(row.exchange_code, "adapter_version", event.target.value)} data-testid={`admin-exchange-adapter-version-input-${row.exchange_code}`} />
                </div>
                <div className="mt-2 flex gap-2">
                  <Button className="bg-orange-500 text-black hover:bg-orange-600" onClick={() => updateExchange(row.exchange_code)} data-testid={`admin-exchange-save-button-${row.exchange_code}`}>Kaydet</Button>
                  <Button variant="outline" className="border-red-500 text-red-300" onClick={() => deleteExchange(row.exchange_code)} data-testid={`admin-exchange-delete-button-${row.exchange_code}`}>Sil</Button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-capability-panel">
          <p className="text-xs uppercase tracking-wider text-slate-400" data-testid="admin-capability-title">Capability CRUD</p>
          <form className="grid gap-2 md:grid-cols-2" onSubmit={createCapability} data-testid="admin-capability-create-form">
            <select value={capabilityForm.exchange_code} onChange={(event) => setCapabilityForm((prev) => ({ ...prev, exchange_code: event.target.value }))} className="border border-slate-600 bg-slate-950 px-2 py-2 text-sm" data-testid="admin-capability-create-exchange-select">
              {(exchangeCodes.length ? exchangeCodes : ["binance"]).map((code) => <option key={code} value={code}>{code}</option>)}
            </select>
            <select value={capabilityForm.market_type} onChange={(event) => setCapabilityForm((prev) => ({ ...prev, market_type: event.target.value }))} className="border border-slate-600 bg-slate-950 px-2 py-2 text-sm" data-testid="admin-capability-create-market-type-select">
              <option value="spot">spot</option>
              <option value="futures">futures</option>
            </select>
            {[
              "supports_spot",
              "supports_futures",
              "supports_test_order",
              "supports_quote_qty",
              "supports_reduce_only",
              "supports_leverage",
              "supports_margin_mode",
              "supports_hedge_mode",
            ].map((key) => (
              <label key={key} className="flex items-center gap-2 text-sm" data-testid={`admin-capability-create-row-${key}`}>
                <input type="checkbox" checked={Boolean(capabilityForm[key])} onChange={(event) => setCapabilityForm((prev) => ({ ...prev, [key]: event.target.checked }))} data-testid={`admin-capability-create-checkbox-${key}`} />{key}
              </label>
            ))}
            <Button className="md:col-span-2 bg-orange-500 text-black hover:bg-orange-600" data-testid="admin-capability-create-submit-button">Capability Ekle</Button>
          </form>

          <div className="space-y-3" data-testid="admin-capability-list">
            {capabilities.map((row) => (
              <div key={row.id} className="border border-slate-700 p-3" data-testid={`admin-capability-row-${row.id}`}>
                <p className="text-sm font-semibold" data-testid={`admin-capability-row-title-${row.id}`}>{row.exchange_code}:{row.market_type}</p>
                <div className="mt-2 grid gap-2 md:grid-cols-2">
                  {["supports_test_order", "supports_quote_qty", "supports_reduce_only", "supports_leverage", "supports_margin_mode", "supports_hedge_mode"].map((key) => (
                    <label key={key} className="flex items-center gap-2 text-sm" data-testid={`admin-capability-edit-row-${row.id}-${key}`}>
                      <input
                        type="checkbox"
                        checked={Boolean(capabilityDrafts[row.id]?.[key])}
                        onChange={(event) => updateCapabilityDraft(row.id, key, event.target.checked)}
                        data-testid={`admin-capability-edit-checkbox-${row.id}-${key}`}
                      />
                      {key}
                    </label>
                  ))}
                </div>
                <div className="mt-2 flex gap-2">
                  <Button className="bg-orange-500 text-black hover:bg-orange-600" onClick={() => updateCapability(row.id)} data-testid={`admin-capability-save-button-${row.id}`}>Kaydet</Button>
                  <Button variant="outline" className="border-red-500 text-red-300" onClick={() => deleteCapability(row.id)} data-testid={`admin-capability-delete-button-${row.id}`}>Sil</Button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2" data-testid="admin-allowed-assignment-grid">
        <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-allowed-market-panel">
          <p className="text-xs uppercase tracking-wider text-slate-400" data-testid="admin-allowed-market-title">Allowed Markets CRUD</p>
          <form className="grid gap-2 md:grid-cols-2" onSubmit={createAllowedMarket} data-testid="admin-allowed-market-create-form">
            <select value={allowedMarketForm.exchange_code} onChange={(event) => setAllowedMarketForm((prev) => ({ ...prev, exchange_code: event.target.value }))} className="border border-slate-600 bg-slate-950 px-2 py-2 text-sm" data-testid="admin-allowed-market-create-exchange-select">
              {(exchangeCodes.length ? exchangeCodes : ["binance"]).map((code) => <option key={code} value={code}>{code}</option>)}
            </select>
            <select value={allowedMarketForm.market_type} onChange={(event) => setAllowedMarketForm((prev) => ({ ...prev, market_type: event.target.value }))} className="border border-slate-600 bg-slate-950 px-2 py-2 text-sm" data-testid="admin-allowed-market-create-market-type-select">
              <option value="spot">spot</option>
              <option value="futures">futures</option>
            </select>
            <select value={allowedMarketForm.environment} onChange={(event) => setAllowedMarketForm((prev) => ({ ...prev, environment: event.target.value }))} className="border border-slate-600 bg-slate-950 px-2 py-2 text-sm" data-testid="admin-allowed-market-create-environment-select">
              <option value="testnet">testnet</option>
              <option value="live">live</option>
            </select>
            <label className="flex items-center gap-2 text-sm" data-testid="admin-allowed-market-create-enabled-row">
              <input type="checkbox" checked={allowedMarketForm.enabled} onChange={(event) => setAllowedMarketForm((prev) => ({ ...prev, enabled: event.target.checked }))} data-testid="admin-allowed-market-create-enabled-checkbox" />enabled
            </label>
            <Button className="md:col-span-2 bg-orange-500 text-black hover:bg-orange-600" data-testid="admin-allowed-market-create-submit-button">Allowed Market Ekle</Button>
          </form>

          <div className="space-y-3" data-testid="admin-allowed-market-list">
            {allowedMarkets.map((row) => (
              <div key={row.id} className="border border-slate-700 p-3" data-testid={`admin-allowed-market-row-${row.id}`}>
                <p className="text-sm" data-testid={`admin-allowed-market-name-${row.id}`}>{row.exchange_code}:{row.market_type}:{row.environment}</p>
                <p className="text-xs text-slate-400" data-testid={`admin-allowed-market-enabled-${row.id}`}>enabled={boolLabel(row.enabled)}</p>
                <div className="mt-2 flex gap-2">
                  <Button className="bg-orange-500 text-black hover:bg-orange-600" onClick={() => toggleAllowedMarket(row)} data-testid={`admin-allowed-market-toggle-button-${row.id}`}>{row.enabled ? "Disable" : "Enable"}</Button>
                  <Button variant="outline" className="border-red-500 text-red-300" onClick={() => deleteAllowedMarket(row.id)} data-testid={`admin-allowed-market-delete-button-${row.id}`}>Sil</Button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-user-assignment-panel">
          <p className="text-xs uppercase tracking-wider text-slate-400" data-testid="admin-user-assignment-title">User Assignment Matrix</p>
          <form className="grid gap-2 md:grid-cols-2" onSubmit={upsertAssignment} data-testid="admin-user-assignment-form">
            <select value={assignmentForm.user_id} onChange={(event) => setAssignmentForm((prev) => ({ ...prev, user_id: event.target.value }))} className="border border-slate-600 bg-slate-950 px-2 py-2 text-sm" data-testid="admin-user-assignment-user-select" required>
              <option value="">Kullanıcı seç</option>
              {approvedUsers.map((user) => (
                <option key={user.id} value={user.id}>{user.email}</option>
              ))}
            </select>
            <select value={assignmentForm.exchange_code} onChange={(event) => setAssignmentForm((prev) => ({ ...prev, exchange_code: event.target.value }))} className="border border-slate-600 bg-slate-950 px-2 py-2 text-sm" data-testid="admin-user-assignment-exchange-select">
              {(exchangeCodes.length ? exchangeCodes : ["binance"]).map((code) => <option key={code} value={code}>{code}</option>)}
            </select>
            {[
              ["spot_allowed", "spot_allowed"],
              ["futures_allowed", "futures_allowed"],
              ["testnet_allowed", "testnet_allowed"],
              ["live_allowed", "live_allowed"],
            ].map(([key, label]) => (
              <label key={key} className="flex items-center gap-2 text-sm" data-testid={`admin-user-assignment-${key}-row`}>
                <input type="checkbox" checked={Boolean(assignmentForm[key])} onChange={(event) => setAssignmentForm((prev) => ({ ...prev, [key]: event.target.checked }))} data-testid={`admin-user-assignment-${key}-checkbox`} />{label}
              </label>
            ))}
            <Button className="md:col-span-2 bg-orange-500 text-black hover:bg-orange-600" data-testid="admin-user-assignment-save-button">Assignment Kaydet</Button>
          </form>

          <div className="space-y-3" data-testid="admin-user-assignment-list">
            {assignments.map((row) => (
              <div key={row.id} className="border border-slate-700 p-3" data-testid={`admin-user-assignment-row-${row.id}`}>
                <p className="text-sm" data-testid={`admin-user-assignment-user-${row.id}`}>user_id: {row.user_id}</p>
                <p className="text-xs text-slate-400" data-testid={`admin-user-assignment-venue-${row.id}`}>{row.exchange_code} · spot={boolLabel(row.spot_allowed)} futures={boolLabel(row.futures_allowed)} testnet={boolLabel(row.testnet_allowed)} live={boolLabel(row.live_allowed)}</p>
                <div className="mt-2 flex gap-2">
                  <Button variant="outline" className="border-red-500 text-red-300" onClick={() => deleteAssignment(row.id)} data-testid={`admin-user-assignment-delete-button-${row.id}`}>Sil</Button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-capability-discovery-panel">
          <p className="text-xs uppercase tracking-wider text-slate-400" data-testid="admin-capability-discovery-title">Capability Discovery</p>
          <div className="grid gap-2 md:grid-cols-4" data-testid="admin-capability-discovery-form-grid">
            <Input value={capabilityForm.exchange_code} onChange={(e) => setCapabilityForm((p) => ({ ...p, exchange_code: e.target.value }))} data-testid="admin-capability-discovery-exchange-input" />
            <Input value={capabilityForm.market_type} onChange={(e) => setCapabilityForm((p) => ({ ...p, market_type: e.target.value }))} data-testid="admin-capability-discovery-market-input" />
            <Input value={capabilityForm.environment} onChange={(e) => setCapabilityForm((p) => ({ ...p, environment: e.target.value }))} data-testid="admin-capability-discovery-environment-input" />
            <Input value={capabilityForm.symbols} onChange={(e) => setCapabilityForm((p) => ({ ...p, symbols: e.target.value }))} data-testid="admin-capability-discovery-symbols-input" />
          </div>
          <Button type="button" onClick={runCapabilityDiscovery} data-testid="admin-capability-discovery-run-button">Discovery Çalıştır</Button>
          <p className="text-xs text-slate-300" data-testid="admin-capability-discovery-result">symbols: {(capabilityDiscovery?.capability?.symbol_capabilities || []).length}</p>
        </div>

        <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-routing-preview-v2-panel">
          <p className="text-xs uppercase tracking-wider text-slate-400" data-testid="admin-routing-preview-v2-title">Routing Preview v2</p>
          <div className="grid gap-2 md:grid-cols-3" data-testid="admin-routing-preview-v2-form-grid">
            <Input placeholder="user_id" value={routingPreviewForm.user_id} onChange={(e) => setRoutingPreviewForm((p) => ({ ...p, user_id: e.target.value }))} data-testid="admin-routing-preview-v2-user-input" />
            <Input placeholder="strategy_id" value={routingPreviewForm.strategy_id} onChange={(e) => setRoutingPreviewForm((p) => ({ ...p, strategy_id: e.target.value }))} data-testid="admin-routing-preview-v2-strategy-input" />
            <Input placeholder="symbol" value={routingPreviewForm.symbol} onChange={(e) => setRoutingPreviewForm((p) => ({ ...p, symbol: e.target.value }))} data-testid="admin-routing-preview-v2-symbol-input" />
          </div>
          <Button type="button" onClick={runRoutingPreviewV2} data-testid="admin-routing-preview-v2-run-button">Preview Çalıştır</Button>
          <p className="text-xs text-slate-300" data-testid="admin-routing-preview-v2-result">status: {routingPreview?.net_status || 'n/a'} · route: {routingPreview?.resolved_execution_path?.source || '-'}</p>
        </div>

        <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-operational-health-panel">
          <p className="text-xs uppercase tracking-wider text-slate-400" data-testid="admin-operational-health-title">Operational Health</p>
          <Button type="button" onClick={loadOperationalHealth} data-testid="admin-operational-health-refresh-button">Health Yenile</Button>
          <p className="text-xs text-slate-300" data-testid="admin-operational-health-net-status">net_status: {operationalHealth?.net_status || 'n/a'}</p>
          <p className="text-xs text-slate-300" data-testid="admin-operational-health-reasons">reason_codes: {(operationalHealth?.reason_codes || []).join(', ') || '-'}</p>
        </div>

        <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-audit-timeline-panel">
          <p className="text-xs uppercase tracking-wider text-slate-400" data-testid="admin-audit-timeline-title">Replayable Audit Timeline</p>
          <Button type="button" onClick={loadAuditTimeline} data-testid="admin-audit-timeline-refresh-button">Timeline Yenile</Button>
          <div className="space-y-1 text-xs text-slate-300" data-testid="admin-audit-timeline-list">
            {(auditTimeline || []).slice(0, 5).map((item, index) => (
              <p key={`${item.id}-${index}`} data-testid={`admin-audit-timeline-item-${index}`}>{item.action} · {item.entity_type} · {item.created_at}</p>
            ))}
          </div>
        </div>

      </div>
    </section>
  );
};
