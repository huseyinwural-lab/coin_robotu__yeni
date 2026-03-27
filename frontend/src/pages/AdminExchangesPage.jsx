import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { AuditTimelinePanel } from "@/components/exchanges/AuditTimelinePanel";
import { CapabilityDiscoveryPanel } from "@/components/exchanges/CapabilityDiscoveryPanel";
import { CapabilityMatrixPanel } from "@/components/exchanges/CapabilityMatrixPanel";
import { ConflictDetectionPanel } from "@/components/exchanges/ConflictDetectionPanel";
import { ControlPlaneCockpitPanel } from "@/components/exchanges/ControlPlaneCockpitPanel";
import { MarketPolicyPanel } from "@/components/exchanges/MarketPolicyPanel";
import { OperationalHealthPanel } from "@/components/exchanges/OperationalHealthPanel";
import { RoutingPolicyPanel } from "@/components/exchanges/RoutingPolicyPanel";
import { RoutingPreviewPanel } from "@/components/exchanges/RoutingPreviewPanel";
import { apiClient } from "@/lib/api";

const defaultAuditFilters = { limit: 50 };

const defaultPanelState = { data: null, loading: false, error: null };

export const AdminExchangesPage = () => {
  const [pageLoading, setPageLoading] = useState(true);
  const [exchanges, setExchanges] = useState([]);
  const [approvedUsers, setApprovedUsers] = useState([]);

  const [capabilityDiscoveryState, setCapabilityDiscoveryState] = useState(defaultPanelState);
  const [capabilityMatrixState, setCapabilityMatrixState] = useState({ data: {}, loading: true, error: null });
  const [marketPolicyState, setMarketPolicyState] = useState({ data: null, loading: true, error: null });
  const [routingPolicyState, setRoutingPolicyState] = useState({ data: null, loading: true, error: null });
  const [failoverPolicyState, setFailoverPolicyState] = useState({ data: { rules: {}, runtime_state: {}, transition_logs: [], routing_decision_logs: [] }, loading: true, error: null });
  const [cockpitState, setCockpitState] = useState({ data: null, loading: true, error: null });
  const [conflictState, setConflictState] = useState({ data: null, loading: true, error: null });
  const [routingPreviewState, setRoutingPreviewState] = useState(defaultPanelState);
  const [operationalHealthState, setOperationalHealthState] = useState({ data: null, loading: true, error: null });
  const [auditTimelineState, setAuditTimelineState] = useState({ data: { items: [] }, loading: true, error: null });
  const [lastAuditFilters, setLastAuditFilters] = useState(defaultAuditFilters);

  const exchangeCodes = useMemo(() => (exchanges || []).map((item) => item.exchange_code), [exchanges]);

  const loadBootstrap = useCallback(async () => {
    setPageLoading(true);
    try {
      const [exchangesRes, usersRes] = await Promise.all([
        apiClient.get("/venues/admin/exchanges"),
        apiClient.get("/auth/admin/user-approval-requests?status=approved"),
      ]);
      setExchanges(exchangesRes.data || []);
      setApprovedUsers(usersRes.data || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Sayfa başlangıç verileri yüklenemedi");
    } finally {
      setPageLoading(false);
    }
  }, []);

  const loadCapabilityMatrix = useCallback(async () => {
    setCapabilityMatrixState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const { data } = await apiClient.get("/venues/admin/capability-matrix");
      setCapabilityMatrixState({ data: data || {}, loading: false, error: null });
    } catch (error) {
      setCapabilityMatrixState({ data: {}, loading: false, error: error?.response?.data?.detail || "Capability matrix yüklenemedi" });
    }
  }, []);

  const loadMarketPolicy = useCallback(async () => {
    setMarketPolicyState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const { data } = await apiClient.get("/venues/admin/market-policy-layer");
      setMarketPolicyState({ data: data || { rules: {} }, loading: false, error: null });
    } catch (error) {
      setMarketPolicyState({ data: null, loading: false, error: error?.response?.data?.detail || "Market policy yüklenemedi" });
    }
  }, []);

  const loadRoutingPolicies = useCallback(async () => {
    setRoutingPolicyState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const { data } = await apiClient.get("/venues/admin/routing-policies");
      setRoutingPolicyState({ data: data || { rules: {} }, loading: false, error: null });
    } catch (error) {
      setRoutingPolicyState({ data: null, loading: false, error: error?.response?.data?.detail || "Routing policy yüklenemedi" });
    }
  }, []);

  const loadFailoverPolicies = useCallback(async () => {
    setFailoverPolicyState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const { data } = await apiClient.get("/venues/admin/failover-policies");
      setFailoverPolicyState({ data: data || { rules: {}, runtime_state: {}, transition_logs: [], routing_decision_logs: [] }, loading: false, error: null });
    } catch (error) {
      setFailoverPolicyState({ data: { rules: {}, runtime_state: {}, transition_logs: [], routing_decision_logs: [] }, loading: false, error: error?.response?.data?.detail || "Failover policy yüklenemedi" });
    }
  }, []);

  const loadOperationalHealth = useCallback(async () => {
    setOperationalHealthState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const { data } = await apiClient.get("/venues/admin/operational-health");
      setOperationalHealthState({ data: data || null, loading: false, error: null });
    } catch (error) {
      setOperationalHealthState({ data: null, loading: false, error: error?.response?.data?.detail || "Operational health yüklenemedi" });
    }
  }, []);

  const loadControlPlaneCockpit = useCallback(async (params = { window_minutes: 30, churn_threshold: 5 }) => {
    setCockpitState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const { data } = await apiClient.get("/venues/admin/control-plane-cockpit", { params });
      setCockpitState({ data: data || null, loading: false, error: null });
    } catch (error) {
      setCockpitState({ data: null, loading: false, error: error?.response?.data?.detail || "Control plane cockpit yüklenemedi" });
    }
  }, []);

  const loadConflictDetection = useCallback(async () => {
    setConflictState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const { data } = await apiClient.get("/venues/admin/conflict-detection-center");
      setConflictState({ data: data || null, loading: false, error: null });
    } catch (error) {
      setConflictState({ data: null, loading: false, error: error?.response?.data?.detail || "Conflict detection yüklenemedi" });
    }
  }, []);

  const loadAuditTimeline = useCallback(async (filters = defaultAuditFilters) => {
    setAuditTimelineState((prev) => ({ ...prev, loading: true, error: null }));
    setLastAuditFilters(filters);
    try {
      const { data } = await apiClient.get("/venues/admin/audit-timeline", { params: filters });
      setAuditTimelineState({ data: data || { items: [] }, loading: false, error: null });
    } catch (error) {
      setAuditTimelineState({ data: { items: [] }, loading: false, error: error?.response?.data?.detail || "Audit timeline yüklenemedi" });
    }
  }, []);

  useEffect(() => {
    loadBootstrap();
    loadCapabilityMatrix();
    loadMarketPolicy();
    loadRoutingPolicies();
    loadFailoverPolicies();
    loadOperationalHealth();
    loadControlPlaneCockpit();
    loadConflictDetection();
    loadAuditTimeline(defaultAuditFilters);
  }, [loadBootstrap, loadCapabilityMatrix, loadMarketPolicy, loadRoutingPolicies, loadFailoverPolicies, loadOperationalHealth, loadControlPlaneCockpit, loadConflictDetection, loadAuditTimeline]);

  const runCapabilityDiscovery = useCallback(async (payload) => {
    setCapabilityDiscoveryState({ data: null, loading: true, error: null });
    try {
      const { data } = await apiClient.post("/venues/admin/capability-discovery", payload);
      setCapabilityDiscoveryState({ data: data || null, loading: false, error: null });
      toast.success("Capability discovery tamamlandı");
      await Promise.all([loadCapabilityMatrix(), loadConflictDetection(), loadAuditTimeline(lastAuditFilters)]);
    } catch (error) {
      const message = error?.response?.data?.detail || "Capability discovery başarısız";
      setCapabilityDiscoveryState({ data: null, loading: false, error: message });
      toast.error(message);
    }
  }, [loadAuditTimeline, loadCapabilityMatrix, lastAuditFilters]);

  const saveCapabilityOverride = useCallback(async (payload) => {
    try {
      await apiClient.put("/venues/admin/capability-matrix/override", payload);
      toast.success("Capability override kaydedildi");
      await Promise.all([loadCapabilityMatrix(), loadConflictDetection(), loadAuditTimeline(lastAuditFilters)]);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Capability override kaydedilemedi");
    }
  }, [loadAuditTimeline, loadCapabilityMatrix, lastAuditFilters]);

  const saveMarketPolicy = useCallback(async (payload) => {
    try {
      await apiClient.put("/venues/admin/market-policy-layer", payload);
      toast.success("Market policy güncellendi");
      await Promise.all([loadMarketPolicy(), loadConflictDetection(), loadAuditTimeline(lastAuditFilters)]);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Market policy kaydedilemedi");
    }
  }, [loadAuditTimeline, loadMarketPolicy, lastAuditFilters]);

  const saveRoutingPolicy = useCallback(async (payload) => {
    try {
      await apiClient.put("/venues/admin/routing-policies", payload);
      toast.success("Routing policy güncellendi");
      await Promise.all([loadRoutingPolicies(), loadControlPlaneCockpit(), loadConflictDetection(), loadAuditTimeline(lastAuditFilters)]);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Routing policy kaydedilemedi");
    }
  }, [loadAuditTimeline, loadRoutingPolicies, loadControlPlaneCockpit, loadConflictDetection, lastAuditFilters]);

  const saveFailoverPolicy = useCallback(async (payload) => {
    try {
      await apiClient.put("/venues/admin/failover-policies", payload);
      toast.success("Failover policy güncellendi");
      await Promise.all([loadFailoverPolicies(), loadControlPlaneCockpit(), loadConflictDetection(), loadAuditTimeline(lastAuditFilters)]);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Failover policy kaydedilemedi");
    }
  }, [loadAuditTimeline, loadFailoverPolicies, loadControlPlaneCockpit, loadConflictDetection, lastAuditFilters]);

  const applyFailoverManualOverride = useCallback(async (payload) => {
    try {
      await apiClient.post("/venues/admin/failover/manual-override", payload);
      toast.success("Failover manual override uygulandı");
      await Promise.all([loadFailoverPolicies(), loadControlPlaneCockpit(), loadConflictDetection(), loadAuditTimeline(lastAuditFilters)]);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Failover manual override başarısız");
    }
  }, [loadAuditTimeline, loadFailoverPolicies, loadControlPlaneCockpit, loadConflictDetection, lastAuditFilters]);

  const runRoutingPreview = useCallback(async (payload) => {
    setRoutingPreviewState({ data: null, loading: true, error: null });
    try {
      const { data } = await apiClient.post("/venues/admin/routing-preview-v2", payload);
      setRoutingPreviewState({ data: data || null, loading: false, error: null });
      toast.success(`Routing preview sonucu: ${data?.net_status || "UNKNOWN"}`);
      await Promise.all([loadFailoverPolicies(), loadControlPlaneCockpit()]);
    } catch (error) {
      const message = error?.response?.data?.detail || "Routing preview çalıştırılamadı";
      setRoutingPreviewState({ data: null, loading: false, error: message });
      toast.error(message);
    }
  }, [loadFailoverPolicies, loadControlPlaneCockpit]);

  return (
    <section className="space-y-4" data-testid="admin-exchanges-page">
      <header className="rounded-2xl border border-orange-500/30 bg-gradient-to-r from-slate-900 via-slate-950 to-slate-900 p-4" data-testid="admin-exchanges-header">
        <h1 className="text-4xl font-black uppercase tracking-tight text-orange-200" data-testid="admin-exchanges-title">Venue / Exchange Control Plane</h1>
        <p className="mt-1 text-sm text-slate-300" data-testid="admin-exchanges-description">
          P2 motoru: failover orchestration, deterministic multi-venue routing ve validation uyumluluğu.
        </p>
        <p className="mt-1 text-xs text-slate-500" data-testid="admin-exchanges-bootstrap-status">bootstrap: {pageLoading ? "yükleniyor" : `hazır · exchanges=${exchangeCodes.length}`}</p>
      </header>

      <div className="grid gap-4 xl:grid-cols-2" data-testid="admin-exchanges-cockpit-grid">
        <ControlPlaneCockpitPanel
          data={cockpitState.data}
          loading={cockpitState.loading}
          error={cockpitState.error}
          onRefresh={loadControlPlaneCockpit}
        />

        <ConflictDetectionPanel
          data={conflictState.data}
          loading={conflictState.loading}
          error={conflictState.error}
          onRefresh={loadConflictDetection}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-2" data-testid="admin-exchanges-panels-grid">
        <OperationalHealthPanel
          data={operationalHealthState.data}
          loading={operationalHealthState.loading}
          error={operationalHealthState.error}
          onRefresh={loadOperationalHealth}
        />

        <RoutingPreviewPanel
          approvedUsers={approvedUsers}
          previewResult={routingPreviewState.data}
          loading={routingPreviewState.loading}
          error={routingPreviewState.error}
          onRunPreview={runRoutingPreview}
        />

        <MarketPolicyPanel
          exchanges={exchanges}
          data={marketPolicyState.data}
          loading={marketPolicyState.loading}
          error={marketPolicyState.error}
          onRefresh={loadMarketPolicy}
          onSavePolicy={saveMarketPolicy}
        />

        <RoutingPolicyPanel
          approvedUsers={approvedUsers}
          exchanges={exchanges}
          data={routingPolicyState.data}
          failoverData={failoverPolicyState.data}
          loading={routingPolicyState.loading || failoverPolicyState.loading}
          error={routingPolicyState.error || failoverPolicyState.error}
          onRefresh={loadRoutingPolicies}
          onRefreshFailover={loadFailoverPolicies}
          onSavePolicy={saveRoutingPolicy}
          onSaveFailoverPolicy={saveFailoverPolicy}
          onApplyManualOverride={applyFailoverManualOverride}
        />

        <CapabilityDiscoveryPanel
          exchanges={exchanges}
          result={capabilityDiscoveryState.data}
          loading={capabilityDiscoveryState.loading}
          error={capabilityDiscoveryState.error}
          onRunDiscovery={runCapabilityDiscovery}
        />

        <CapabilityMatrixPanel
          matrixData={capabilityMatrixState.data}
          loading={capabilityMatrixState.loading}
          error={capabilityMatrixState.error}
          onRefresh={loadCapabilityMatrix}
          onSaveOverride={saveCapabilityOverride}
        />
      </div>

      <AuditTimelinePanel
        data={auditTimelineState.data}
        loading={auditTimelineState.loading}
        error={auditTimelineState.error}
        onLoad={loadAuditTimeline}
      />
    </section>
  );
};
