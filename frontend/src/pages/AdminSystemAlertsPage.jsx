import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

const initialConfigForm = {
  resend_api_key: "",
  alert_from: "",
  alert_to: "",
  slack_webhook_url: "",
};

export const AdminSystemAlertsPage = () => {
  const [alerts, setAlerts] = useState([]);
  const [timeline, setTimeline] = useState([]);
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selectedIds, setSelectedIds] = useState([]);
  const [filters, setFilters] = useState({
    status: "all",
    severity: "all",
    alert_type: "",
    entity_key: "",
    limit: 50,
    days: 14,
  });
  const [configForm, setConfigForm] = useState(initialConfigForm);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [{ data: alertData }, { data: timelineData }, { data: configData }] = await Promise.all([
        apiClient.get("/admin/system-alerts", {
          params: {
            status: filters.status,
            severity: filters.severity === "all" ? undefined : filters.severity,
            alert_type: filters.alert_type || undefined,
            entity_key: filters.entity_key || undefined,
            limit: Number(filters.limit) || 50,
          },
        }),
        apiClient.get("/admin/system-alerts/timeline", {
          params: { days: Number(filters.days) || 14 },
        }),
        apiClient.get("/admin/system-alerts/config"),
      ]);

      setAlerts(alertData || []);
      setTimeline(timelineData?.points || []);
      setConfig(configData || null);
      setSelectedIds((prev) => prev.filter((id) => (alertData || []).some((item) => item.id === id)));
    } catch (error) {
      toast.error(error?.response?.data?.detail || "System alerts verisi alınamadı");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const allSelected = useMemo(() => alerts.length > 0 && selectedIds.length === alerts.length, [alerts, selectedIds]);

  const toggleSelectAll = () => {
    setSelectedIds(allSelected ? [] : alerts.map((alert) => alert.id));
  };

  const toggleSelection = (alertId) => {
    setSelectedIds((prev) => (prev.includes(alertId) ? prev.filter((id) => id !== alertId) : [...prev, alertId]));
  };

  const bulkAck = async () => {
    if (selectedIds.length === 0) {
      toast.error("Bulk acknowledge için en az bir alert seçin");
      return;
    }
    try {
      await apiClient.post("/admin/system-alerts/bulk-ack", { ids: selectedIds });
      toast.success("Seçili alertler ack edildi");
      setSelectedIds([]);
      await loadData();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bulk acknowledge başarısız");
    }
  };

  const ackOne = async (alertId) => {
    try {
      await apiClient.post(`/admin/system-alerts/${alertId}/ack`);
      toast.success("Alert ack edildi");
      await loadData();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Ack başarısız");
    }
  };

  const resolveOne = async (alertId) => {
    try {
      await apiClient.post(`/admin/system-alerts/${alertId}/resolve`);
      toast.success("Alert resolved");
      await loadData();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Resolve başarısız");
    }
  };

  const simulateAlert = async () => {
    try {
      await apiClient.post("/ops-alerts/simulate");
      toast.success("Simülasyon alert tetiklendi");
      await loadData();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Simülasyon başarısız");
    }
  };

  const saveConfig = async () => {
    try {
      const payload = {
        resend_api_key: configForm.resend_api_key || null,
        alert_from: configForm.alert_from || null,
        alert_to: configForm.alert_to || null,
        slack_webhook_url: configForm.slack_webhook_url || null,
      };
      await apiClient.post("/admin/system-alerts/config", payload);
      toast.success("Alert kanal konfigürasyonu güncellendi");
      setConfigForm((prev) => ({ ...prev, resend_api_key: "", slack_webhook_url: "" }));
      await loadData();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Konfigürasyon kaydedilemedi");
    }
  };

  const deliveryStatusLabel = (row, channel) => row?.delivery_status?.[channel]?.status || "-";

  return (
    <section className="space-y-4" data-testid="admin-system-alerts-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="admin-system-alerts-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-black" data-testid="admin-system-alerts-title">System Alerts Control Center</h2>
        <p className="mt-2 text-sm text-black/80" data-testid="admin-system-alerts-description">
          Severity/entity filtreleri, timeline, delivery status ve bulk acknowledge yönetimi.
        </p>
      </header>

      <div className="space-y-3 border border-black/30 bg-orange-100 p-4" data-testid="admin-system-alerts-config-panel">
        <p className="text-sm font-semibold text-black" data-testid="admin-system-alerts-config-title">Alert Delivery Activation</p>
        <p className="text-xs text-black/70" data-testid="admin-system-alerts-channel-status-line">
          email={config?.channels?.email || "-"} · slack={config?.channels?.slack || "-"} · config_source={config?.channels?.config_source || "-"}
        </p>
        <p className="text-xs text-black/70" data-testid="admin-system-alerts-masked-secrets-line">
          resend={config?.config?.masked?.resend_api_key || ""} · slack={config?.config?.masked?.slack_webhook_url || ""}
        </p>
        <div className="grid gap-2 md:grid-cols-2" data-testid="admin-system-alerts-config-form-grid">
          <Input
            placeholder="RESEND_API_KEY"
            value={configForm.resend_api_key}
            onChange={(event) => setConfigForm((prev) => ({ ...prev, resend_api_key: event.target.value }))}
            data-testid="admin-system-alerts-resend-api-key-input"
          />
          <Input
            placeholder="SLACK_WEBHOOK_URL"
            value={configForm.slack_webhook_url}
            onChange={(event) => setConfigForm((prev) => ({ ...prev, slack_webhook_url: event.target.value }))}
            data-testid="admin-system-alerts-slack-webhook-input"
          />
          <Input
            placeholder="ALERT_FROM"
            value={configForm.alert_from}
            onChange={(event) => setConfigForm((prev) => ({ ...prev, alert_from: event.target.value }))}
            data-testid="admin-system-alerts-alert-from-input"
          />
          <Input
            placeholder="ALERT_TO (comma separated)"
            value={configForm.alert_to}
            onChange={(event) => setConfigForm((prev) => ({ ...prev, alert_to: event.target.value }))}
            data-testid="admin-system-alerts-alert-to-input"
          />
        </div>
        <div className="flex flex-wrap gap-2" data-testid="admin-system-alerts-config-actions-row">
          <Button className="border border-black bg-black text-orange-400 hover:bg-zinc-800" onClick={saveConfig} data-testid="admin-system-alerts-save-config-button">
            Config Kaydet
          </Button>
          <Button className="border border-black bg-orange-500 text-black hover:bg-orange-600" onClick={simulateAlert} data-testid="admin-system-alerts-simulate-button">
            Simulate Alert
          </Button>
          <Button className="border border-black bg-white text-black hover:bg-neutral-100" onClick={loadData} data-testid="admin-system-alerts-refresh-button">
            Yenile
          </Button>
        </div>
      </div>

      <div className="space-y-3 border border-black/30 bg-orange-100 p-4" data-testid="admin-system-alerts-filters-panel">
        <div className="grid gap-2 md:grid-cols-6" data-testid="admin-system-alerts-filters-grid">
          <select className="border border-black/40 bg-white px-3 py-2 text-sm" value={filters.status} onChange={(event) => setFilters((prev) => ({ ...prev, status: event.target.value }))} data-testid="admin-system-alerts-status-filter-select">
            <option value="all">all</option>
            <option value="open">open</option>
            <option value="ack">ack</option>
            <option value="resolved">resolved</option>
          </select>
          <select className="border border-black/40 bg-white px-3 py-2 text-sm" value={filters.severity} onChange={(event) => setFilters((prev) => ({ ...prev, severity: event.target.value }))} data-testid="admin-system-alerts-severity-filter-select">
            <option value="all">all severities</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="CRITICAL">CRITICAL</option>
          </select>
          <Input value={filters.alert_type} onChange={(event) => setFilters((prev) => ({ ...prev, alert_type: event.target.value }))} placeholder="alert_type" data-testid="admin-system-alerts-alert-type-filter-input" />
          <Input value={filters.entity_key} onChange={(event) => setFilters((prev) => ({ ...prev, entity_key: event.target.value }))} placeholder="entity_key" data-testid="admin-system-alerts-entity-key-filter-input" />
          <Input type="number" value={filters.limit} onChange={(event) => setFilters((prev) => ({ ...prev, limit: event.target.value }))} placeholder="limit" data-testid="admin-system-alerts-limit-input" />
          <Input type="number" value={filters.days} onChange={(event) => setFilters((prev) => ({ ...prev, days: event.target.value }))} placeholder="timeline days" data-testid="admin-system-alerts-days-input" />
        </div>

        <div className="flex flex-wrap items-center gap-2" data-testid="admin-system-alerts-bulk-actions-row">
          <Button className="border border-black bg-red-700 text-white hover:bg-red-800" onClick={bulkAck} data-testid="admin-system-alerts-bulk-ack-button">
            Bulk Acknowledge
          </Button>
          <p className="text-sm text-black" data-testid="admin-system-alerts-selected-count-text">Seçili: {selectedIds.length}</p>
          <p className="text-sm text-black" data-testid="admin-system-alerts-total-count-text">Toplam alert: {alerts.length}</p>
          <p className="text-sm text-black" data-testid="admin-system-alerts-loading-state-text">loading: {String(loading)}</p>
        </div>
      </div>

      <div className="border border-black/30 bg-orange-100 p-4" data-testid="admin-system-alerts-timeline-panel">
        <p className="text-sm font-semibold text-black" data-testid="admin-system-alerts-timeline-title">Alert Timeline</p>
        <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-4" data-testid="admin-system-alerts-timeline-grid">
          {timeline.map((point) => (
            <div key={point.date} className="border border-black/20 bg-white px-2 py-2 text-xs" data-testid={`admin-system-alerts-timeline-point-${point.date}`}>
              {point.date} · {point.count}
            </div>
          ))}
          {timeline.length === 0 && <p className="text-xs text-black/70" data-testid="admin-system-alerts-timeline-empty-text">Timeline verisi yok.</p>}
        </div>
      </div>

      <div className="border border-black/30 bg-orange-100" data-testid="admin-system-alerts-table-wrapper">
        <Table data-testid="admin-system-alerts-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="admin-system-alerts-head-select">
                <Checkbox checked={allSelected} onCheckedChange={toggleSelectAll} data-testid="admin-system-alerts-select-all-checkbox" />
              </TableHead>
              <TableHead data-testid="admin-system-alerts-head-alert-type">alert_type</TableHead>
              <TableHead data-testid="admin-system-alerts-head-severity">severity</TableHead>
              <TableHead data-testid="admin-system-alerts-head-entity-key">entity_key</TableHead>
              <TableHead data-testid="admin-system-alerts-head-created-at">created_at</TableHead>
              <TableHead data-testid="admin-system-alerts-head-delivery">delivery_status</TableHead>
              <TableHead data-testid="admin-system-alerts-head-ack-status">ack_status</TableHead>
              <TableHead data-testid="admin-system-alerts-head-actions">actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {alerts.map((alert) => (
              <TableRow key={alert.id} data-testid={`admin-system-alerts-row-${alert.id}`}>
                <TableCell data-testid={`admin-system-alerts-select-cell-${alert.id}`}>
                  <Checkbox checked={selectedIds.includes(alert.id)} onCheckedChange={() => toggleSelection(alert.id)} data-testid={`admin-system-alerts-checkbox-${alert.id}`} />
                </TableCell>
                <TableCell data-testid={`admin-system-alerts-alert-type-${alert.id}`}>{alert.alert_type}</TableCell>
                <TableCell data-testid={`admin-system-alerts-severity-${alert.id}`}>{alert.severity}</TableCell>
                <TableCell data-testid={`admin-system-alerts-entity-key-${alert.id}`}>{alert.entity_key || "-"}</TableCell>
                <TableCell className="text-xs" data-testid={`admin-system-alerts-created-at-${alert.id}`}>{new Date(alert.created_at).toLocaleString()}</TableCell>
                <TableCell className="text-xs" data-testid={`admin-system-alerts-delivery-${alert.id}`}>
                  email:{deliveryStatusLabel(alert, "email")} · slack:{deliveryStatusLabel(alert, "slack")}
                </TableCell>
                <TableCell data-testid={`admin-system-alerts-ack-status-${alert.id}`}>{alert.status}</TableCell>
                <TableCell data-testid={`admin-system-alerts-actions-${alert.id}`}>
                  <div className="flex flex-wrap gap-2" data-testid={`admin-system-alerts-actions-row-${alert.id}`}>
                    <Button size="sm" className="border border-black bg-black text-orange-400 hover:bg-zinc-800" onClick={() => ackOne(alert.id)} data-testid={`admin-system-alerts-ack-button-${alert.id}`}>
                      Ack
                    </Button>
                    <Button size="sm" className="border border-black bg-orange-500 text-black hover:bg-orange-600" onClick={() => resolveOne(alert.id)} data-testid={`admin-system-alerts-resolve-button-${alert.id}`}>
                      Resolve
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}

            {!loading && alerts.length === 0 && (
              <TableRow data-testid="admin-system-alerts-empty-row">
                <TableCell colSpan={8} className="text-center text-sm text-black/70" data-testid="admin-system-alerts-empty-text">
                  Alert kaydı bulunamadı.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </section>
  );
};
