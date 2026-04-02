import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

const EXCHANGES = ["binance", "bybit", "okx"];
const MARKET_TYPES = ["spot", "usdt_perp", "coin_perp"];
const PURPOSES = ["market_data", "execution", "fallback"];
const ENVIRONMENTS = ["live"];
const SCOPE_TYPES = ["global", "tenant", "group"];
const PROBE_STATES = [
  "ready",
  "connectivity_only",
  "invalid_key",
  "permission_restricted",
  "ip_restricted",
  "env_mismatch",
  "rate_limited",
  "probe_not_supported",
  "unreachable",
  "no_probe",
];

const probeBadgeClass = {
  ready: "bg-emerald-100 text-emerald-800",
  connectivity_only: "bg-sky-100 text-sky-800",
  invalid_key: "bg-red-100 text-red-800",
  permission_restricted: "bg-amber-100 text-amber-800",
  ip_restricted: "bg-orange-100 text-orange-800",
  env_mismatch: "bg-violet-100 text-violet-800",
  rate_limited: "bg-yellow-100 text-yellow-800",
  probe_not_supported: "bg-indigo-100 text-indigo-800",
  unreachable: "bg-slate-200 text-slate-800",
  no_probe: "bg-slate-100 text-slate-700",
};

export const AdminCredentialOrchestrationPage = () => {
  const [filters, setFilters] = useState({
    exchange: "binance",
    market_type: "spot",
    environment: "live",
    purpose: "all",
  });
  const [credentials, setCredentials] = useState([]);
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState(null);
  const [traceDrawerOpen, setTraceDrawerOpen] = useState(false);
  const [traceHistoryLoading, setTraceHistoryLoading] = useState(false);
  const [traceHistory, setTraceHistory] = useState([]);
  const [selectedHistoryTrace, setSelectedHistoryTrace] = useState(null);
  const [previewForm, setPreviewForm] = useState({ user_id: "", purpose: "execution" });

  const [createForm, setCreateForm] = useState({
    scope_type: "global",
    scope_id: "",
    exchange: "binance",
    market_type: "spot",
    purpose: "market_data",
    environment: "live",
    api_key: "",
    api_secret: "",
    passphrase: "",
    base_url_override: "",
    ip_binding_note: "",
  });

  const [ruleForm, setRuleForm] = useState({
    exchange: "binance",
    market_type: "spot",
    environment: "live",
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
            purpose: filters.purpose === "all" ? undefined : filters.purpose,
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
    if (!createForm.api_key.trim() || !createForm.api_secret.trim()) {
      toast.error("API key ve secret zorunlu");
      return;
    }
    try {
      await apiClient.post("/venues/admin/credentials", {
        ...createForm,
        scope_id: createForm.scope_id || null,
        passphrase: createForm.passphrase || null,
        base_url_override: createForm.base_url_override || null,
        ip_binding_note: createForm.ip_binding_note || null,
        is_default: false,
      });
      toast.success("Credential kaydedildi (pending)");
      setCreateForm((prev) => ({ ...prev, api_key: "", api_secret: "", passphrase: "" }));
      loadData();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Credential kaydedilemedi");
    }
  };

  const handleCredentialAction = async (id, action, payload = null) => {
    try {
      await apiClient.post(`/venues/admin/credentials/${id}/${action}`, payload || undefined);
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
    if (!previewForm.user_id.trim()) {
      toast.error("user_id girin");
      return;
    }
    try {
      const { data } = await apiClient.get("/venues/admin/credential-resolution-preview", {
        params: {
          user_id: previewForm.user_id.trim(),
          exchange: filters.exchange,
          market_type: filters.market_type,
          environment: filters.environment,
          purpose: previewForm.purpose,
        },
      });
      setPreview(data || null);
      setTraceDrawerOpen(false);
      setSelectedHistoryTrace(null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Preview alınamadı");
    }
  };

  const loadTraceHistory = useCallback(async () => {
    if (!previewForm.user_id.trim()) {
      setTraceHistory([]);
      return;
    }
    setTraceHistoryLoading(true);
    try {
      const { data } = await apiClient.get("/audit-logs/timeline", {
        params: {
          action: "admin_credential_resolution_preview",
          entity_type: "credential_resolution_trace",
          q: previewForm.user_id.trim(),
          limit: 20,
        },
      });
      const items = Array.isArray(data?.items) ? data.items : [];
      const normalized = items.map((item) => ({
        audit_id: item.id,
        request_id: item?.details?.request_id || "-",
        resolved_at: item?.details?.resolved_at || item?.created_at || "-",
        source: item?.details?.source || "-",
        environment: item?.details?.environment || "-",
        market_type: item?.details?.market_type || "-",
        purpose: item?.details?.purpose || "-",
        probe_state: item?.details?.selected_probe_status || "-",
        masked_fingerprint: item?.details?.masked_fingerprint || "-",
        selection_reason: item?.details?.selection_reason || "-",
        rule_id: item?.details?.rule_id || "-",
      }));
      setTraceHistory(normalized);
    } catch (error) {
      setTraceHistory([]);
      const errorDetail = error?.response?.data?.detail;
      const errorMessage = typeof errorDetail === 'string' 
        ? errorDetail 
        : Array.isArray(errorDetail) 
          ? errorDetail.map(e => e?.msg || 'Validation error').join(', ')
          : "Trace geçmişi alınamadı";
      toast.error(errorMessage);
    } finally {
      setTraceHistoryLoading(false);
    }
  }, [previewForm.user_id]);

  const openTraceDrawer = async () => {
    setTraceDrawerOpen(true);
    await loadTraceHistory();
  };

  const probeSummary = useMemo(() => {
    const seed = PROBE_STATES.reduce((acc, key) => ({ ...acc, [key]: 0 }), {});
    return credentials.reduce((acc, row) => {
      const key = row.last_probe_status || "no_probe";
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    }, seed);
  }, [credentials]);

  const egressRows = useMemo(() => {
    return credentials.map((row) => ({
      id: row.id,
      exchange: row.exchange,
      market_type: row.market_type,
      environment: row.environment,
      egress_url: row.base_url_override || row?.last_probe_meta?.base_url || "-",
      proxy_note: row.ip_binding_note || "-",
      probe_message: row.last_probe_message || "-",
    }));
  }, [credentials]);

  const decisionTraceSteps = useMemo(() => {
    const source = String(preview?.source || "").toLowerCase();
    const reason = String(preview?.audit_metadata?.selection_reason || "").toLowerCase();
    const isUser = source.includes("user");
    const isTenant = source.includes("tenant") || source.includes("group") || reason.includes("tenant");
    const isGlobal = source.includes("global") || (!isUser && !isTenant && !!source);
    return [
      {
        key: "user",
        label: "1) user credential",
        status: isUser ? "selected" : "checked",
      },
      {
        key: "tenant_admin",
        label: "2) tenant_admin credential",
        status: isTenant ? "selected" : isUser ? "skipped" : "checked",
      },
      {
        key: "global_admin",
        label: "3) global_admin credential",
        status: isGlobal ? "selected" : isUser || isTenant ? "skipped" : "checked",
      },
    ];
  }, [preview]);

  const traceDriftHighlights = useMemo(() => {
    if (!preview || !selectedHistoryTrace) {
      return [];
    }
    const checks = [
      {
        key: "source",
        label: "source",
        severity: "critical",
        current: preview?.source || "-",
        previous: selectedHistoryTrace?.source || "-",
      },
      {
        key: "selection_reason",
        label: "selection_reason",
        severity: "medium",
        current: preview?.audit_metadata?.selection_reason || "-",
        previous: selectedHistoryTrace?.selection_reason || "-",
      },
      {
        key: "probe_state",
        label: "probe_state",
        severity: "low",
        current: preview?.selected_probe_status || "-",
        previous: selectedHistoryTrace?.probe_state || "-",
      },
    ];
    return checks.filter((item) => String(item.current) !== String(item.previous));
  }, [preview, selectedHistoryTrace]);

  return (
    <section className="space-y-6" data-testid="admin-credential-orchestration-page">
      <header className="space-y-2" data-testid="admin-credential-orchestration-header">
        <h1 className="text-4xl font-semibold" data-testid="admin-credential-orchestration-title">Credential Orchestration</h1>
        <p className="text-sm text-slate-600" data-testid="admin-credential-orchestration-subtitle">
          Multi-exchange anahtar yönetişimi: user → tenant_admin → global_admin deterministic fallback zinciri.
        </p>
      </header>

      <section className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 md:grid-cols-5" data-testid="credential-filter-panel">
        <div>
          <p className="mb-1 text-xs text-slate-500" data-testid="credential-filter-exchange-label">Exchange</p>
          <select
            className="h-10 w-full rounded border px-2"
            value={filters.exchange}
            onChange={(e) => setFilters((prev) => ({ ...prev, exchange: e.target.value }))}
            data-testid="credential-filter-exchange-select"
          >
            {EXCHANGES.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </div>
        <div>
          <p className="mb-1 text-xs text-slate-500" data-testid="credential-filter-market-label">Market</p>
          <select
            className="h-10 w-full rounded border px-2"
            value={filters.market_type}
            onChange={(e) => setFilters((prev) => ({ ...prev, market_type: e.target.value }))}
            data-testid="credential-filter-market-select"
          >
            {MARKET_TYPES.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </div>
        <div>
          <p className="mb-1 text-xs text-slate-500" data-testid="credential-filter-purpose-label">Purpose</p>
          <select
            className="h-10 w-full rounded border px-2"
            value={filters.purpose}
            onChange={(e) => setFilters((prev) => ({ ...prev, purpose: e.target.value }))}
            data-testid="credential-filter-purpose-select"
          >
            <option value="all">all</option>
            {PURPOSES.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </div>
        <div>
          <p className="mb-1 text-xs text-slate-500" data-testid="credential-filter-environment-label">Environment</p>
          <select
            className="h-10 w-full rounded border px-2"
            value={filters.environment}
            onChange={(e) => setFilters((prev) => ({ ...prev, environment: e.target.value }))}
            data-testid="credential-filter-environment-select"
          >
            {ENVIRONMENTS.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </div>
        <div className="flex items-end">
          <Button onClick={loadData} className="w-full" data-testid="credential-filter-refresh-button">Yenile</Button>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-2" data-testid="credential-main-grid">
        <article className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4" data-testid="credential-management-card">
          <h2 className="text-lg font-semibold" data-testid="credential-management-title">Master Credential Tanımı</h2>
          <div className="grid gap-2 md:grid-cols-2" data-testid="credential-create-form-grid">
            <div>
              <p className="mb-1 text-xs text-slate-500" data-testid="credential-form-scope-type-label">Scope Type</p>
              <select className="h-10 w-full rounded border px-2" value={createForm.scope_type} onChange={(e) => setCreateForm((prev) => ({ ...prev, scope_type: e.target.value }))} data-testid="credential-form-scope-type-select">
                {SCOPE_TYPES.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </div>
            <div>
              <p className="mb-1 text-xs text-slate-500" data-testid="credential-form-scope-id-label">Scope Id</p>
              <Input placeholder="tenant/group id (opsiyonel)" value={createForm.scope_id} onChange={(e) => setCreateForm((prev) => ({ ...prev, scope_id: e.target.value }))} data-testid="credential-form-scope-id-input" />
            </div>
            <div>
              <p className="mb-1 text-xs text-slate-500" data-testid="credential-form-exchange-label">Exchange</p>
              <select className="h-10 w-full rounded border px-2" value={createForm.exchange} onChange={(e) => setCreateForm((prev) => ({ ...prev, exchange: e.target.value }))} data-testid="credential-form-exchange-select">
                {EXCHANGES.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </div>
            <div>
              <p className="mb-1 text-xs text-slate-500" data-testid="credential-form-market-type-label">Market Type</p>
              <select className="h-10 w-full rounded border px-2" value={createForm.market_type} onChange={(e) => setCreateForm((prev) => ({ ...prev, market_type: e.target.value }))} data-testid="credential-form-market-type-select">
                {MARKET_TYPES.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </div>
            <div>
              <p className="mb-1 text-xs text-slate-500" data-testid="credential-form-purpose-label">Purpose</p>
              <select className="h-10 w-full rounded border px-2" value={createForm.purpose} onChange={(e) => setCreateForm((prev) => ({ ...prev, purpose: e.target.value }))} data-testid="credential-form-purpose-select">
                {PURPOSES.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </div>
            <div>
              <p className="mb-1 text-xs text-slate-500" data-testid="credential-form-environment-label">Environment</p>
              <select className="h-10 w-full rounded border px-2" value={createForm.environment} onChange={(e) => setCreateForm((prev) => ({ ...prev, environment: e.target.value }))} data-testid="credential-form-environment-select">
                {ENVIRONMENTS.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </div>
            <div className="md:col-span-2">
              <p className="mb-1 text-xs text-slate-500" data-testid="credential-form-base-url-label">Base URL / Proxy Target</p>
              <Input placeholder="https://proxy.example.com (opsiyonel)" value={createForm.base_url_override} onChange={(e) => setCreateForm((prev) => ({ ...prev, base_url_override: e.target.value }))} data-testid="credential-form-base-url-input" />
            </div>
            <div className="md:col-span-2">
              <p className="mb-1 text-xs text-slate-500" data-testid="credential-form-egress-note-label">Proxy Route / Egress Note</p>
              <Input placeholder="örn: /fapi/* -> vps-futures" value={createForm.ip_binding_note} onChange={(e) => setCreateForm((prev) => ({ ...prev, ip_binding_note: e.target.value }))} data-testid="credential-form-egress-note-input" />
            </div>
            <Input type="password" autoComplete="new-password" placeholder="API Key" value={createForm.api_key} onChange={(e) => setCreateForm((prev) => ({ ...prev, api_key: e.target.value }))} data-testid="credential-form-api-key-input" />
            <Input type="password" autoComplete="new-password" placeholder="API Secret" value={createForm.api_secret} onChange={(e) => setCreateForm((prev) => ({ ...prev, api_secret: e.target.value }))} data-testid="credential-form-api-secret-input" />
            <Input type="password" autoComplete="new-password" placeholder="Passphrase (okx için opsiyonel)" value={createForm.passphrase} onChange={(e) => setCreateForm((prev) => ({ ...prev, passphrase: e.target.value }))} data-testid="credential-form-passphrase-input" />
          </div>
          <div className="flex flex-wrap items-center gap-3" data-testid="credential-form-actions-row">
            <Button onClick={handleCreateCredential} data-testid="credential-form-save-button">Credential Kaydet</Button>
            <p className="text-xs text-slate-500" data-testid="credential-form-note">Yeni kayıt pending açılır. Aktif kullanım için approve gerekir.</p>
          </div>

          <div className="overflow-x-auto rounded border border-slate-200" data-testid="credential-table-wrapper">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Exchange</TableHead>
                  <TableHead>Market</TableHead>
                  <TableHead>Purpose</TableHead>
                  <TableHead>Scope</TableHead>
                  <TableHead>Env</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Lifecycle</TableHead>
                  <TableHead>Permission</TableHead>
                  <TableHead>Probe</TableHead>
                  <TableHead>Egress</TableHead>
                  <TableHead>Fingerprint</TableHead>
                  <TableHead>Aksiyon</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {credentials.map((row) => (
                  <TableRow key={row.id} data-testid={`credential-row-${row.id}`}>
                    <TableCell data-testid={`credential-exchange-${row.id}`}>{row.exchange}</TableCell>
                    <TableCell data-testid={`credential-market-${row.id}`}>{row.market_type}</TableCell>
                    <TableCell data-testid={`credential-purpose-${row.id}`}>{row.purpose}</TableCell>
                    <TableCell data-testid={`credential-scope-${row.id}`}>{row.scope_type}:{row.scope_id || "-"}</TableCell>
                    <TableCell>
                      <span className="rounded bg-slate-100 px-2 py-1 text-xs" data-testid={`credential-environment-badge-${row.id}`}>{row.environment}</span>
                    </TableCell>
                    <TableCell>
                      <span className="rounded bg-slate-100 px-2 py-1 text-xs" data-testid={`credential-status-badge-${row.id}`}>{row.is_active ? "active" : "disabled"}/{row.approval_status}</span>
                    </TableCell>
                    <TableCell>
                      <span className="rounded bg-amber-100 px-2 py-1 text-xs" data-testid={`credential-lifecycle-badge-${row.id}`}>{row.lifecycle_status || "pending"}</span>
                    </TableCell>
                    <TableCell>
                      <div className="text-xs" data-testid={`credential-permission-scope-${row.id}`}>
                        <p data-testid={`credential-permission-read-${row.id}`}>read:{String(Boolean(row.permission_scope?.read))}</p>
                        <p data-testid={`credential-permission-trade-${row.id}`}>trade:{String(Boolean(row.permission_scope?.trade))}</p>
                        <p data-testid={`credential-permission-withdraw-${row.id}`}>withdraw:{String(Boolean(row.permission_scope?.withdraw))}</p>
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className={`rounded px-2 py-1 text-xs ${probeBadgeClass[row.last_probe_status || "no_probe"] || "bg-slate-100 text-slate-700"}`} data-testid={`credential-last-probe-status-${row.id}`}>{row.last_probe_status || "no_probe"}</span>
                    </TableCell>
                    <TableCell>
                      <p className="max-w-44 truncate text-xs" data-testid={`credential-egress-url-${row.id}`}>{row.base_url_override || row?.last_probe_meta?.base_url || "-"}</p>
                    </TableCell>
                    <TableCell>
                      <p className="max-w-40 truncate text-xs" data-testid={`credential-fingerprint-${row.id}`}>{row.credential_fingerprint}</p>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1" data-testid={`credential-actions-${row.id}`}>
                        <Button size="sm" variant="outline" onClick={() => handleCredentialAction(row.id, "probe")} data-testid={`credential-probe-button-${row.id}`}>Probe</Button>
                        <Button size="sm" variant="outline" onClick={() => handleCredentialAction(row.id, "verify")} data-testid={`credential-verify-button-${row.id}`}>Verify</Button>
                        <Button size="sm" variant="outline" onClick={() => handleCredentialAction(row.id, "approve")} data-testid={`credential-approve-button-${row.id}`}>Approve</Button>
                        <Button size="sm" variant="outline" onClick={() => handleCredentialAction(row.id, "revoke")} data-testid={`credential-revoke-button-${row.id}`}>Revoke</Button>
                        <Button size="sm" variant="outline" onClick={() => handleCredentialAction(row.id, "disable")} data-testid={`credential-disable-button-${row.id}`}>Disable</Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {!credentials.length && (
                  <TableRow>
                    <TableCell colSpan={12} className="text-center text-sm text-slate-500" data-testid="credential-empty-state">Kayıt bulunamadı</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </article>

        <article className="space-y-6" data-testid="routing-probe-audit-column">
          <div className="rounded-2xl border border-slate-200 bg-white p-4" data-testid="routing-matrix-card">
            <h2 className="mb-2 text-lg font-semibold" data-testid="routing-matrix-title">Routing Matrix</h2>
            <p className="mb-3 text-xs text-slate-500" data-testid="routing-matrix-chain-description">Deterministik fallback: user → tenant_admin → global_admin</p>
            <div className="grid gap-2 md:grid-cols-2" data-testid="rule-form-grid">
              <select className="h-10 w-full rounded border px-2" value={ruleForm.exchange} onChange={(e) => setRuleForm((prev) => ({ ...prev, exchange: e.target.value }))} data-testid="rule-form-exchange-select">
                {EXCHANGES.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
              <select className="h-10 w-full rounded border px-2" value={ruleForm.market_type} onChange={(e) => setRuleForm((prev) => ({ ...prev, market_type: e.target.value }))} data-testid="rule-form-market-select">
                {MARKET_TYPES.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
              <select className="h-10 w-full rounded border px-2" value={ruleForm.environment} onChange={(e) => setRuleForm((prev) => ({ ...prev, environment: e.target.value }))} data-testid="rule-form-environment-select">
                {ENVIRONMENTS.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
              <select className="h-10 w-full rounded border px-2" value={ruleForm.preferred_source} onChange={(e) => setRuleForm((prev) => ({ ...prev, preferred_source: e.target.value }))} data-testid="rule-form-preferred-source-select">
                <option value="user">user</option>
                <option value="admin">admin</option>
                <option value="admin_fallback">admin_fallback</option>
              </select>
              <Input placeholder="tenant_id (opsiyonel)" value={ruleForm.tenant_id} onChange={(e) => setRuleForm((prev) => ({ ...prev, tenant_id: e.target.value }))} data-testid="rule-form-tenant-id-input" />
              <Input placeholder="user_id (opsiyonel)" value={ruleForm.user_id} onChange={(e) => setRuleForm((prev) => ({ ...prev, user_id: e.target.value }))} data-testid="rule-form-user-id-input" />
            </div>
            <div className="mt-3 flex items-center gap-3" data-testid="rule-form-actions-row">
              <Button onClick={handleRuleUpsert} data-testid="rule-form-save-button">Kural Kaydet</Button>
              <label className="flex items-center gap-2 text-sm" data-testid="rule-form-fallback-checkbox-wrapper">
                <input type="checkbox" checked={ruleForm.fallback_enabled} onChange={(e) => setRuleForm((prev) => ({ ...prev, fallback_enabled: e.target.checked }))} data-testid="rule-form-fallback-checkbox" />
                fallback_enabled
              </label>
            </div>
            <div className="mt-3 space-y-2" data-testid="rule-list-wrapper">
              {rules.map((row) => (
                <div key={row.id} className="rounded border border-slate-200 p-2 text-xs" data-testid={`rule-row-${row.id}`}>
                  <p data-testid={`rule-row-market-env-${row.id}`}>{row.exchange}/{row.market_type}/{row.environment}</p>
                  <p data-testid={`rule-row-source-${row.id}`}>preferred={row.preferred_source} fallback={String(row.fallback_enabled)}</p>
                  <p data-testid={`rule-row-scope-${row.id}`}>tenant={row.tenant_id || "-"} user={row.user_id || "-"}</p>
                </div>
              ))}
              {!rules.length && <p className="text-xs text-slate-500" data-testid="rule-empty-state">Kural yok</p>}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4" data-testid="probe-audit-dashboard-card">
            <h2 className="mb-3 text-lg font-semibold" data-testid="probe-dashboard-title">Probe & Resolution Preview</h2>
            <div className="mb-3 grid gap-2 md:grid-cols-3" data-testid="resolution-preview-form-grid">
              <Input placeholder="user_id" value={previewForm.user_id} onChange={(e) => setPreviewForm((prev) => ({ ...prev, user_id: e.target.value }))} data-testid="resolution-preview-user-id-input" />
              <select className="h-10 w-full rounded border px-2" value={previewForm.purpose} onChange={(e) => setPreviewForm((prev) => ({ ...prev, purpose: e.target.value }))} data-testid="resolution-preview-purpose-select">
                {PURPOSES.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
              <Button onClick={handlePreview} data-testid="resolution-preview-load-button">Selected Source Önizleme</Button>
            </div>
            <div className="rounded border border-slate-200 p-3 text-xs" data-testid="resolution-preview-output">
              <p data-testid="resolution-preview-request-id-line">request id: <span data-testid="resolution-preview-request-id-value">{preview?.request_id || "-"}</span></p>
              <p data-testid="resolution-preview-resolved-at-line">timestamp: <span data-testid="resolution-preview-resolved-at-value">{preview?.resolved_at || "-"}</span></p>
              <p data-testid="resolution-preview-source-line">selected source: <span data-testid="resolution-preview-source-value">{preview?.source || "-"}</span></p>
              <p data-testid="resolution-preview-credential-id-line">credential id: <span data-testid="resolution-preview-credential-id-value">{preview?.selected_credential_id || "-"}</span></p>
              <p data-testid="resolution-preview-fingerprint-line">fingerprint: <span data-testid="resolution-preview-fingerprint-value">{preview?.masked_fingerprint || "-"}</span></p>
              <p data-testid="resolution-preview-market-line">market_type: <span data-testid="resolution-preview-market-value">{preview?.market_type || filters.market_type}</span></p>
              <p data-testid="resolution-preview-environment-line">environment: <span data-testid="resolution-preview-environment-value">{preview?.environment || filters.environment}</span></p>
              <p data-testid="resolution-preview-purpose-line">purpose: <span data-testid="resolution-preview-purpose-value">{preview?.purpose || previewForm.purpose}</span></p>
              <p data-testid="resolution-preview-probe-state-line">probe state: <span data-testid="resolution-preview-probe-state-value">{preview?.selected_probe_status || "-"}</span></p>
              <p data-testid="resolution-preview-base-url-line">effective base url: <span data-testid="resolution-preview-base-url-value">{preview?.effective_base_url || "-"}</span></p>
              <p data-testid="resolution-preview-selection-reason-line">selection reason: <span data-testid="resolution-preview-selection-reason-value">{preview?.audit_metadata?.selection_reason || "-"}</span></p>
              <p data-testid="resolution-preview-rule-id-line">rule id: <span data-testid="resolution-preview-rule-id-value">{preview?.audit_metadata?.rule_id || "-"}</span></p>
              <div className="mt-2 flex flex-wrap items-center gap-2" data-testid="resolution-preview-trace-actions-row">
                <Button size="sm" variant="outline" disabled={!preview?.request_id} onClick={openTraceDrawer} data-testid="resolution-preview-open-trace-drawer-button">Audit Trace Aç</Button>
                <a
                  href={preview?.request_id ? `#trace-${preview.request_id}` : "#"}
                  className="text-xs text-sky-700 underline"
                  data-testid="resolution-preview-audit-link-anchor"
                >
                  audit_link
                </a>
              </div>
            </div>
            <div className="mt-3 rounded border border-slate-200 p-3" data-testid="decision-trace-timeline-card">
              <p className="mb-2 text-xs font-semibold text-slate-700" data-testid="decision-trace-timeline-title">Decision Trace Timeline</p>
              <div className="space-y-2" data-testid="decision-trace-timeline-list">
                {decisionTraceSteps.map((step) => (
                  <div key={step.key} className="flex items-center justify-between rounded border border-slate-200 px-2 py-1 text-xs" data-testid={`decision-trace-step-${step.key}`}>
                    <span data-testid={`decision-trace-step-label-${step.key}`}>{step.label}</span>
                    <span
                      className={`rounded px-2 py-0.5 ${step.status === "selected" ? "bg-emerald-100 text-emerald-700" : step.status === "skipped" ? "bg-slate-100 text-slate-600" : "bg-amber-100 text-amber-700"}`}
                      data-testid={`decision-trace-step-status-${step.key}`}
                    >
                      {step.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2" data-testid="probe-status-distribution-grid">
              {PROBE_STATES.map((key) => (
                <div key={key} className="rounded border border-slate-200 p-2 text-xs" data-testid={`probe-distribution-${key}`}>
                  <p className="font-semibold" data-testid={`probe-distribution-key-${key}`}>{key}</p>
                  <p data-testid={`probe-distribution-value-${key}`}>{probeSummary[key] || 0}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4" data-testid="egress-visibility-card">
            <h2 className="mb-3 text-lg font-semibold" data-testid="egress-visibility-title">Proxy / Egress Görünürlüğü</h2>
            <div className="max-h-72 overflow-auto space-y-2" data-testid="egress-visibility-list">
              {egressRows.map((row) => (
                <div key={row.id} className="rounded border border-slate-200 p-2 text-xs" data-testid={`egress-row-${row.id}`}>
                  <p data-testid={`egress-row-head-${row.id}`}>{row.exchange}/{row.market_type}/{row.environment}</p>
                  <p className="truncate" data-testid={`egress-row-url-${row.id}`}>egress_url={row.egress_url}</p>
                  <p className="truncate" data-testid={`egress-row-note-${row.id}`}>proxy_note={row.proxy_note}</p>
                  <p className="truncate" data-testid={`egress-row-probe-${row.id}`}>probe_message={row.probe_message}</p>
                </div>
              ))}
              {!egressRows.length && <p className="text-xs text-slate-500" data-testid="egress-empty-state">Egress kaydı yok</p>}
            </div>
          </div>
        </article>
      </section>

      <Dialog open={traceDrawerOpen} onOpenChange={setTraceDrawerOpen}>
        <DialogContent className="max-w-2xl" data-testid="resolution-trace-drawer-modal">
          <DialogHeader>
            <DialogTitle data-testid="resolution-trace-drawer-title">Resolution Audit Trace</DialogTitle>
            <DialogDescription data-testid="resolution-trace-drawer-description">
              request_id ile birebir eşleşen resolution ayrıntısı.
            </DialogDescription>
          </DialogHeader>
          <div id={preview?.request_id ? `trace-${preview.request_id}` : "trace-empty"} className="space-y-2 text-xs" data-testid="resolution-trace-drawer-content">
            <p data-testid="resolution-trace-request-id">request_id: {preview?.request_id || "-"}</p>
            <p data-testid="resolution-trace-timestamp">timestamp: {preview?.resolved_at || "-"}</p>
            <p data-testid="resolution-trace-source">selected source: {preview?.source || "-"}</p>
            <p data-testid="resolution-trace-fallback-chain">fallback chain: {(preview?.fallback_chain || ["user", "tenant_admin", "global_admin"]).join(" -> ")}</p>
            <p data-testid="resolution-trace-masked-credential">used credential(masked): {preview?.masked_api_key || "-"} / {preview?.masked_fingerprint || "-"}</p>
            <p data-testid="resolution-trace-environment">environment: {preview?.environment || filters.environment}</p>
            <p data-testid="resolution-trace-market">market_type: {preview?.market_type || filters.market_type}</p>
            <p data-testid="resolution-trace-purpose">purpose: {preview?.purpose || previewForm.purpose}</p>
            <p data-testid="resolution-trace-probe-state">probe state: {preview?.selected_probe_status || "-"}</p>
            <p data-testid="resolution-trace-probe-message">probe message: {preview?.selected_probe_message || "-"}</p>
          </div>
          <div className="mt-2 rounded border border-slate-200 p-3" data-testid="resolution-trace-history-card">
            <p className="mb-2 text-xs font-semibold" data-testid="resolution-trace-history-title">Geçmiş Trace Listesi (Son 20)</p>
            {traceHistoryLoading && <p className="text-xs text-slate-500" data-testid="resolution-trace-history-loading">Yükleniyor...</p>}
            {!traceHistoryLoading && !traceHistory.length && (
              <p className="text-xs text-slate-500" data-testid="resolution-trace-history-empty">Geçmiş trace bulunamadı</p>
            )}
            {!traceHistoryLoading && !!traceHistory.length && (
              <div className="space-y-2" data-testid="resolution-trace-history-list">
                {traceHistory.map((item) => (
                  <div key={item.audit_id} className="rounded border border-slate-200 p-2" data-testid={`resolution-trace-history-row-${item.audit_id}`}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-xs" data-testid={`resolution-trace-history-request-id-${item.audit_id}`}>request_id: {item.request_id}</p>
                      <Button size="sm" variant="outline" onClick={() => setSelectedHistoryTrace(item)} data-testid={`resolution-trace-history-compare-button-${item.audit_id}`}>Karşılaştır</Button>
                    </div>
                    <p className="text-xs text-slate-600" data-testid={`resolution-trace-history-meta-${item.audit_id}`}>{item.environment}/{item.market_type}/{item.purpose} • {item.source}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="mt-2 rounded border border-slate-200 p-3" data-testid="resolution-trace-compare-card">
            <p className="mb-2 text-xs font-semibold" data-testid="resolution-trace-compare-title">Trace Karşılaştırma</p>
            <div className="grid gap-2 md:grid-cols-2" data-testid="resolution-trace-compare-grid">
              <div className="rounded border border-slate-200 p-2" data-testid="resolution-trace-compare-current-column">
                <p className="font-semibold" data-testid="resolution-trace-compare-current-title">Current</p>
                <p data-testid="resolution-trace-compare-current-request-id">request_id: {preview?.request_id || "-"}</p>
                <p data-testid="resolution-trace-compare-current-source">source: {preview?.source || "-"}</p>
                <p data-testid="resolution-trace-compare-current-selection-reason">selection_reason: {preview?.audit_metadata?.selection_reason || "-"}</p>
                <p data-testid="resolution-trace-compare-current-probe">probe: {preview?.selected_probe_status || "-"}</p>
              </div>
              <div className="rounded border border-slate-200 p-2" data-testid="resolution-trace-compare-history-column">
                <p className="font-semibold" data-testid="resolution-trace-compare-history-title">Selected History</p>
                <p data-testid="resolution-trace-compare-history-request-id">request_id: {selectedHistoryTrace?.request_id || "-"}</p>
                <p data-testid="resolution-trace-compare-history-source">source: {selectedHistoryTrace?.source || "-"}</p>
                <p data-testid="resolution-trace-compare-history-selection-reason">selection_reason: {selectedHistoryTrace?.selection_reason || "-"}</p>
                <p data-testid="resolution-trace-compare-history-probe">probe: {selectedHistoryTrace?.probe_state || "-"}</p>
              </div>
            </div>
            <div className="mt-2 rounded border border-slate-200 p-2" data-testid="resolution-trace-drift-highlight-card">
              <p className="mb-1 text-xs font-semibold" data-testid="resolution-trace-drift-highlight-title">Drift Highlight</p>
              {!selectedHistoryTrace && <p className="text-xs text-slate-500" data-testid="resolution-trace-drift-highlight-empty">Karşılaştırmak için geçmiş bir trace seçin.</p>}
              {!!selectedHistoryTrace && !traceDriftHighlights.length && (
                <p className="text-xs text-emerald-700" data-testid="resolution-trace-drift-highlight-no-diff">source/reason/probe değişimi yok.</p>
              )}
              {!!traceDriftHighlights.length && (
                <div className="space-y-1" data-testid="resolution-trace-drift-highlight-list">
                  {traceDriftHighlights.map((diff) => (
                    <p key={diff.key} className="text-xs" data-testid={`resolution-trace-drift-highlight-item-${diff.key}`}>
                      <span className="rounded bg-amber-100 px-1 py-0.5 text-amber-800">{diff.label}</span>
                      <span
                        className={`ml-1 rounded px-1 py-0.5 ${diff.severity === "critical" ? "bg-rose-100 text-rose-700" : diff.severity === "medium" ? "bg-orange-100 text-orange-700" : "bg-sky-100 text-sky-700"}`}
                        data-testid={`resolution-trace-drift-severity-${diff.key}`}
                      >
                        {diff.severity}
                      </span>
                      :
                      <span className="ml-1 text-slate-700">{diff.previous}</span>
                      <span className="mx-1">→</span>
                      <span className="font-semibold text-rose-700">{diff.current}</span>
                    </p>
                  ))}
                </div>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTraceDrawerOpen(false)} data-testid="resolution-trace-drawer-close-button">Kapat</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {loading && <p className="text-xs text-slate-500" data-testid="credential-page-loading-indicator">Yükleniyor...</p>}
    </section>
  );
};
