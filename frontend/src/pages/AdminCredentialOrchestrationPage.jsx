import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

const environments = ["testnet", "live"];
const markets = ["spot", "futures"];

const badgeClass = {
  ready: "bg-emerald-100 text-emerald-800",
  invalid_key: "bg-red-100 text-red-800",
  permission_restricted: "bg-amber-100 text-amber-800",
  ip_restricted: "bg-orange-100 text-orange-800",
  env_mismatch: "bg-violet-100 text-violet-800",
  unreachable: "bg-slate-200 text-slate-800",
};

export const AdminCredentialOrchestrationPage = () => {
  const [filters, setFilters] = useState({ exchange: "binance", market_type: "spot", environment: "testnet" });
  const [credentials, setCredentials] = useState([]);
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState(null);
  const [previewUserId, setPreviewUserId] = useState("");

  const [createForm, setCreateForm] = useState({
    scope_type: "global",
    scope_id: "",
    exchange: "binance",
    market_type: "spot",
    purpose: "market_data",
    environment: "testnet",
    api_key: "",
    api_secret: "",
    base_url_override: "",
    ip_binding_note: "",
  });

  const [ruleForm, setRuleForm] = useState({
    exchange: "binance",
    market_type: "spot",
    environment: "testnet",
    tenant_id: "",
    user_id: "",
    preferred_source: "user",
    fallback_enabled: true,
  });

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [credRes, ruleRes] = await Promise.all([
        apiClient.get("/venues/admin/credentials", {
          params: {
            exchange: filters.exchange,
            market_type: filters.market_type,
            environment: filters.environment,
            include_inactive: true,
          },
        }),
        apiClient.get("/venues/admin/credential-rules", {
          params: {
            exchange: filters.exchange,
            market_type: filters.market_type,
            environment: filters.environment,
          },
        }),
      ]);
      setCredentials(credRes?.data || []);
      setRules(ruleRes?.data || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Credential verisi alınamadı");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleCreateCredential = async () => {
    if (!createForm.api_key || !createForm.api_secret) {
      toast.error("API key ve secret zorunlu");
      return;
    }
    try {
      await apiClient.post("/venues/admin/credentials", {
        ...createForm,
        scope_id: createForm.scope_id || null,
        base_url_override: createForm.base_url_override || null,
        ip_binding_note: createForm.ip_binding_note || null,
        is_default: false,
      });
      toast.success("Credential kaydedildi (pending)");
      setCreateForm((prev) => ({ ...prev, api_key: "", api_secret: "" }));
      loadData();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Credential kaydedilemedi");
    }
  };

  const handleCredentialAction = async (id, action) => {
    try {
      await apiClient.post(`/venues/admin/credentials/${id}/${action}`);
      toast.success(`${action} tamamlandı`);
      loadData();
    } catch (error) {
      toast.error(error?.response?.data?.detail || `${action} başarısız`);
    }
  };

  const handleRuleUpsert = async () => {
    try {
      await apiClient.put("/venues/admin/credential-rules", {
        ...ruleForm,
        tenant_id: ruleForm.tenant_id || null,
        user_id: ruleForm.user_id || null,
      });
      toast.success("Routing kuralı güncellendi");
      loadData();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Routing kuralı güncellenemedi");
    }
  };

  const handlePreview = async () => {
    if (!previewUserId.trim()) {
      toast.error("user_id girin");
      return;
    }
    try {
      const { data } = await apiClient.get("/venues/admin/credential-resolution-preview", {
        params: {
          user_id: previewUserId.trim(),
          exchange: filters.exchange,
          market_type: filters.market_type,
          environment: filters.environment,
          purpose: "execution_fallback",
        },
      });
      setPreview(data || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Preview alınamadı");
    }
  };

  const probeSummary = useMemo(() => {
    return credentials.reduce((acc, row) => {
      const key = row.last_probe_status || "unknown";
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    }, {});
  }, [credentials]);

  return (
    <section className="space-y-6" data-testid="admin-credential-orchestration-page">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold" data-testid="admin-credential-orchestration-title">Credential Orchestration</h1>
        <p className="text-sm text-slate-600" data-testid="admin-credential-orchestration-subtitle">
          Admin master credential + user execution credential yönetişimi (deterministic source selection)
        </p>
      </header>

      <section className="grid gap-3 rounded-xl border border-slate-200 bg-white p-4 md:grid-cols-4" data-testid="credential-filter-panel">
        <div>
          <p className="text-xs text-slate-500">Exchange</p>
          <Input value={filters.exchange} onChange={(e) => setFilters((p) => ({ ...p, exchange: e.target.value }))} data-testid="credential-filter-exchange-input" />
        </div>
        <div>
          <p className="text-xs text-slate-500">Market</p>
          <select className="h-10 w-full rounded border px-2" value={filters.market_type} onChange={(e) => setFilters((p) => ({ ...p, market_type: e.target.value }))} data-testid="credential-filter-market-select">
            {markets.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </div>
        <div>
          <p className="text-xs text-slate-500">Environment</p>
          <select className="h-10 w-full rounded border px-2" value={filters.environment} onChange={(e) => setFilters((p) => ({ ...p, environment: e.target.value }))} data-testid="credential-filter-environment-select">
            {environments.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </div>
        <div className="flex items-end">
          <Button onClick={loadData} data-testid="credential-filter-refresh-button">Yenile</Button>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <article className="rounded-xl border border-slate-200 bg-white p-4" data-testid="credential-management-card">
          <h2 className="mb-3 text-lg font-semibold">Master Credentials</h2>
          <div className="grid gap-2 md:grid-cols-2">
            <Input placeholder="scope_type (global/tenant/group)" value={createForm.scope_type} onChange={(e) => setCreateForm((p) => ({ ...p, scope_type: e.target.value }))} data-testid="credential-form-scope-type-input" />
            <Input placeholder="scope_id (opsiyonel)" value={createForm.scope_id} onChange={(e) => setCreateForm((p) => ({ ...p, scope_id: e.target.value }))} data-testid="credential-form-scope-id-input" />
            <Input placeholder="market_type (spot/futures)" value={createForm.market_type} onChange={(e) => setCreateForm((p) => ({ ...p, market_type: e.target.value }))} data-testid="credential-form-market-type-input" />
            <Input placeholder="environment (testnet/live)" value={createForm.environment} onChange={(e) => setCreateForm((p) => ({ ...p, environment: e.target.value }))} data-testid="credential-form-environment-input" />
            <Input placeholder="purpose" value={createForm.purpose} onChange={(e) => setCreateForm((p) => ({ ...p, purpose: e.target.value }))} data-testid="credential-form-purpose-input" />
            <Input placeholder="base_url_override (opsiyonel)" value={createForm.base_url_override} onChange={(e) => setCreateForm((p) => ({ ...p, base_url_override: e.target.value }))} data-testid="credential-form-base-url-input" />
            <Input placeholder="API Key" value={createForm.api_key} onChange={(e) => setCreateForm((p) => ({ ...p, api_key: e.target.value }))} data-testid="credential-form-api-key-input" />
            <Input placeholder="API Secret" value={createForm.api_secret} onChange={(e) => setCreateForm((p) => ({ ...p, api_secret: e.target.value }))} data-testid="credential-form-api-secret-input" />
          </div>
          <div className="mt-3 flex items-center gap-3">
            <Button onClick={handleCreateCredential} data-testid="credential-form-save-button">Credential Kaydet</Button>
            <p className="text-xs text-slate-500" data-testid="credential-form-note">Yeni kayıt pending açılır, Super Admin approve etmelidir.</p>
          </div>

          <div className="mt-4 rounded border border-slate-200" data-testid="credential-table-wrapper">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Market</TableHead>
                  <TableHead>Env</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Probe</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Aksiyon</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {credentials.map((row) => (
                  <TableRow key={row.id} data-testid={`credential-row-${row.id}`}>
                    <TableCell>{row.market_type}</TableCell>
                    <TableCell>
                      <span className="rounded bg-slate-100 px-2 py-1 text-xs" data-testid={`credential-environment-badge-${row.id}`}>{row.environment}</span>
                    </TableCell>
                    <TableCell>
                      <span className="rounded bg-slate-100 px-2 py-1 text-xs" data-testid={`credential-status-badge-${row.id}`}>
                        {row.is_active ? "active" : "disabled"} / {row.approval_status}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className={`rounded px-2 py-1 text-xs ${badgeClass[row.last_probe_status] || "bg-slate-100 text-slate-700"}`} data-testid={`credential-last-probe-status-${row.id}`}>
                        {row.last_probe_status || "no_probe"}
                      </span>
                    </TableCell>
                    <TableCell>
                      <p className="text-xs" data-testid={`credential-fingerprint-${row.id}`}>{row.credential_fingerprint}</p>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-2">
                        <Button size="sm" variant="outline" onClick={() => handleCredentialAction(row.id, "probe")} data-testid={`credential-probe-button-${row.id}`}>Probe</Button>
                        <Button size="sm" variant="outline" onClick={() => handleCredentialAction(row.id, "approve")} data-testid={`credential-approve-button-${row.id}`}>Approve</Button>
                        <Button size="sm" variant="outline" onClick={() => handleCredentialAction(row.id, "disable")} data-testid={`credential-disable-button-${row.id}`}>Disable</Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {!credentials.length && (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center text-sm text-slate-500" data-testid="credential-empty-state">
                      Kayıt bulunamadı
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </article>

        <article className="space-y-6" data-testid="routing-probe-audit-column">
          <div className="rounded-xl border border-slate-200 bg-white p-4" data-testid="routing-matrix-card">
            <h2 className="mb-3 text-lg font-semibold">Credential Routing Matrix</h2>
            <div className="grid gap-2 md:grid-cols-2">
              <Input placeholder="tenant_id (opsiyonel)" value={ruleForm.tenant_id} onChange={(e) => setRuleForm((p) => ({ ...p, tenant_id: e.target.value }))} data-testid="rule-form-tenant-id-input" />
              <Input placeholder="user_id (opsiyonel)" value={ruleForm.user_id} onChange={(e) => setRuleForm((p) => ({ ...p, user_id: e.target.value }))} data-testid="rule-form-user-id-input" />
              <Input placeholder="market_type" value={ruleForm.market_type} onChange={(e) => setRuleForm((p) => ({ ...p, market_type: e.target.value }))} data-testid="rule-form-market-input" />
              <Input placeholder="environment" value={ruleForm.environment} onChange={(e) => setRuleForm((p) => ({ ...p, environment: e.target.value }))} data-testid="rule-form-environment-input" />
              <select className="h-10 w-full rounded border px-2 md:col-span-2" value={ruleForm.preferred_source} onChange={(e) => setRuleForm((p) => ({ ...p, preferred_source: e.target.value }))} data-testid="rule-form-preferred-source-select">
                <option value="user">user</option>
                <option value="admin">admin</option>
                <option value="admin_fallback">admin_fallback</option>
              </select>
            </div>
            <div className="mt-3 flex items-center gap-3">
              <Button onClick={handleRuleUpsert} data-testid="rule-form-save-button">Kural Kaydet</Button>
              <label className="flex items-center gap-2 text-sm" data-testid="rule-form-fallback-checkbox-wrapper">
                <input type="checkbox" checked={ruleForm.fallback_enabled} onChange={(e) => setRuleForm((p) => ({ ...p, fallback_enabled: e.target.checked }))} data-testid="rule-form-fallback-checkbox" />
                fallback_enabled
              </label>
            </div>

            <div className="mt-3 space-y-2" data-testid="rule-list-wrapper">
              {rules.map((row) => (
                <div key={row.id} className="rounded border border-slate-200 p-2 text-xs" data-testid={`rule-row-${row.id}`}>
                  <p>market={row.market_type} env={row.environment}</p>
                  <p>preferred={row.preferred_source} fallback={String(row.fallback_enabled)}</p>
                  <p>tenant={row.tenant_id || "-"} user={row.user_id || "-"}</p>
                </div>
              ))}
              {!rules.length && <p className="text-xs text-slate-500" data-testid="rule-empty-state">Kural yok</p>}
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-4" data-testid="probe-audit-dashboard-card">
            <h2 className="mb-3 text-lg font-semibold">Probe & Audit Dashboard</h2>
            <div className="mb-3 grid gap-2 md:grid-cols-2">
              <Input placeholder="user_id" value={previewUserId} onChange={(e) => setPreviewUserId(e.target.value)} data-testid="resolution-preview-user-id-input" />
              <Button onClick={handlePreview} data-testid="resolution-preview-load-button">Selected Source Önizleme</Button>
            </div>
            <div className="rounded border border-slate-200 p-3" data-testid="resolution-preview-output">
              <p className="text-xs">selected source: <span data-testid="resolution-preview-source-value">{preview?.source || "-"}</span></p>
              <p className="text-xs">credential id: <span data-testid="resolution-preview-credential-id-value">{preview?.selected_credential_id || "-"}</span></p>
              <p className="text-xs">fingerprint: <span data-testid="resolution-preview-fingerprint-value">{preview?.masked_fingerprint || "-"}</span></p>
            </div>
            <div className="mt-3 grid gap-2 md:grid-cols-3" data-testid="probe-status-distribution-grid">
              {Object.entries(probeSummary).map(([key, value]) => (
                <div key={key} className="rounded border border-slate-200 p-2 text-xs" data-testid={`probe-distribution-${key}`}>
                  <p className="font-semibold">{key}</p>
                  <p>{value}</p>
                </div>
              ))}
              {!Object.keys(probeSummary).length && <p className="text-xs text-slate-500" data-testid="probe-distribution-empty">Probe dağılımı yok</p>}
            </div>
          </div>
        </article>
      </section>

      {loading && <p className="text-xs text-slate-500" data-testid="credential-page-loading-indicator">Yükleniyor...</p>}
    </section>
  );
};
