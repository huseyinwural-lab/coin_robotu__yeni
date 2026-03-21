import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

const ANOMALY_ACTION = "SCANNER_ANOMALY_DETECTED";

const toIsoFromHours = (hours) => {
  const parsed = Number(hours || 168);
  const now = Date.now();
  return new Date(now - (parsed * 60 * 60 * 1000)).toISOString();
};

const toCsvSafe = (value) => {
  const raw = String(value ?? "");
  return `"${raw.replaceAll('"', '""')}"`;
};

const sourceOf = (item) => String(item?.details?.source || "unknown_source");

const failRatioOf = (item) => Number(item?.details?.fail_ratio || 0);

const computeTimeToRecoverMap = (rows, warningThreshold) => {
  const sorted = [...rows].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
  const unresolvedByKey = new Map();
  const ttrById = {};

  for (const row of sorted) {
    const key = `${String(row?.actor_user_id || "unknown_user")}::${sourceOf(row)}`;
    const currentTs = new Date(row.created_at).getTime();
    const currentFailRatio = failRatioOf(row);
    const unresolved = unresolvedByKey.get(key) || [];

    const stillUnresolved = [];
    unresolved.forEach((candidate) => {
      const recovered = currentFailRatio <= Math.min(warningThreshold, candidate.failRatio * 0.7);
      if (recovered) {
        const deltaMinutes = Math.max(0, Math.round((currentTs - candidate.timestamp) / 60000));
        ttrById[candidate.id] = deltaMinutes;
      } else {
        stillUnresolved.push(candidate);
      }
    });

    stillUnresolved.push({
      id: row.id,
      timestamp: currentTs,
      failRatio: currentFailRatio,
    });
    unresolvedByKey.set(key, stillUnresolved);
  }

  return ttrById;
};

const defaultPolicy = {
  warning_threshold: 0.1,
  critical_threshold: 0.2,
  smart_mute_window_seconds: 300,
  smart_mute_trigger_count: 3,
  smart_mute_duration_seconds: 900,
  notifications_enabled: true,
  notify_min_severity: "warning",
  webhook_urls: [],
};

export const AdminAnomalyTimelinePage = () => {
  const { user } = useAuth();
  const [isLoading, setIsLoading] = useState(true);
  const [windowHours, setWindowHours] = useState("168");
  const [searchText, setSearchText] = useState("");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [userFilter, setUserFilter] = useState("all");
  const [items, setItems] = useState([]);
  const [selectedLogId, setSelectedLogId] = useState(null);
  const [policy, setPolicy] = useState(defaultPolicy);
  const [webhookInput, setWebhookInput] = useState("");
  const [isSavingPolicy, setIsSavingPolicy] = useState(false);
  const [activeMutes, setActiveMutes] = useState([]);
  const [muteDurationSeconds, setMuteDurationSeconds] = useState("900");

  const loadPolicy = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/admin/anomaly-alerts/policy");
      const nextPolicy = { ...defaultPolicy, ...(data || {}) };
      setPolicy(nextPolicy);
      setWebhookInput((nextPolicy.webhook_urls || []).join("\n"));
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Alert policy yüklenemedi");
    }
  }, []);

  const loadMutes = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/admin/anomaly-alerts/mutes", { params: { limit: 20 } });
      setActiveMutes(data || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Active mute listesi yüklenemedi");
    }
  }, []);

  const loadTimeline = useCallback(async () => {
    setIsLoading(true);
    try {
      const { data } = await apiClient.get("/audit-logs/timeline", {
        params: {
          action: ANOMALY_ACTION,
          limit: 500,
          date_from: toIsoFromHours(windowHours),
        },
      });
      const nextItems = data?.items || [];
      setItems(nextItems);
      setSelectedLogId((prev) => prev || nextItems[0]?.id || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Anomaly timeline yüklenemedi");
    } finally {
      setIsLoading(false);
    }
  }, [windowHours]);

  const loadAll = useCallback(async () => {
    await Promise.all([loadTimeline(), loadPolicy(), loadMutes()]);
  }, [loadTimeline, loadPolicy, loadMutes]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const sourceOptions = useMemo(() => {
    const counts = items.reduce((acc, item) => {
      const source = sourceOf(item);
      acc[source] = (acc[source] || 0) + 1;
      return acc;
    }, {});
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .map(([value, count]) => ({ value, count }));
  }, [items]);

  const userOptions = useMemo(() => {
    const counts = items.reduce((acc, item) => {
      const actorUserId = String(item?.actor_user_id || "unknown_user");
      acc[actorUserId] = (acc[actorUserId] || 0) + 1;
      return acc;
    }, {});
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .map(([value, count]) => ({ value, count }));
  }, [items]);

  const filteredItems = useMemo(() => {
    const normalizedSearch = searchText.trim().toLowerCase();
    return items.filter((item) => {
      const severityOk = severityFilter === "all" ? true : String(item.severity || "").toLowerCase() === severityFilter;
      const sourceOk = sourceFilter === "all" ? true : sourceOf(item) === sourceFilter;
      const userOk = userFilter === "all" ? true : String(item.actor_user_id || "unknown_user") === userFilter;
      const searchOk = !normalizedSearch
        ? true
        : JSON.stringify(item).toLowerCase().includes(normalizedSearch);
      return severityOk && sourceOk && userOk && searchOk;
    });
  }, [items, searchText, severityFilter, sourceFilter, userFilter]);

  const ttrByLogId = useMemo(
    () => computeTimeToRecoverMap(filteredItems, Number(policy.warning_threshold || 0.1)),
    [filteredItems, policy.warning_threshold],
  );

  const selectedItem = useMemo(
    () => filteredItems.find((item) => item.id === selectedLogId) || filteredItems[0] || null,
    [filteredItems, selectedLogId],
  );

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(filteredItems, null, 2)], { type: "application/json" });
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `anomaly_timeline_${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.URL.revokeObjectURL(url);
    toast.success("Anomaly timeline JSON indirildi");
  };

  const exportCsv = () => {
    const header = [
      "created_at",
      "severity",
      "actor_user_id",
      "source",
      "fail_ratio",
      "total_requests",
      "failed_requests",
      "success_requests",
      "trend_window_minutes",
      "payload_hash",
      "suppress_reason",
      "time_to_recover_minutes",
    ];
    const rows = filteredItems.map((item) => {
      const details = item.details || {};
      return [
        item.created_at,
        item.severity,
        item.actor_user_id,
        sourceOf(item),
        details.fail_ratio,
        details.total_requests,
        details.failed_requests,
        details.success_requests,
        details.trend_window_minutes,
        details.payload_hash,
        details.suppress_reason,
        ttrByLogId[item.id] ?? "",
      ].map(toCsvSafe).join(",");
    });
    const csv = [header.join(","), ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `anomaly_timeline_${new Date().toISOString().replace(/[:.]/g, "-")}.csv`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.URL.revokeObjectURL(url);
    toast.success("Anomaly timeline CSV indirildi");
  };

  const savePolicy = async () => {
    setIsSavingPolicy(true);
    try {
      const webhookUrls = webhookInput
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean);
      const payload = {
        ...policy,
        warning_threshold: Number(policy.warning_threshold || 0.1),
        critical_threshold: Number(policy.critical_threshold || 0.2),
        smart_mute_window_seconds: Number(policy.smart_mute_window_seconds || 300),
        smart_mute_trigger_count: Number(policy.smart_mute_trigger_count || 3),
        smart_mute_duration_seconds: Number(policy.smart_mute_duration_seconds || 900),
        webhook_urls: webhookUrls,
      };
      const { data } = await apiClient.put("/admin/anomaly-alerts/policy", payload);
      const nextPolicy = { ...defaultPolicy, ...(data || {}) };
      setPolicy(nextPolicy);
      setWebhookInput((nextPolicy.webhook_urls || []).join("\n"));
      toast.success("Anomaly alert policy güncellendi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Policy güncellenemedi");
    } finally {
      setIsSavingPolicy(false);
    }
  };

  const muteSelectedPattern = async () => {
    const payloadHash = String(selectedItem?.details?.payload_hash || "").trim();
    if (!payloadHash) {
      toast.error("Seçili kayıtta payload_hash yok");
      return;
    }
    try {
      await apiClient.post("/admin/anomaly-alerts/mutes", {
        payload_hash: payloadHash,
        duration_seconds: Number(muteDurationSeconds || 900),
        reason: "manual_timeline_mute",
      });
      toast.success("Pattern geçici olarak susturuldu");
      await loadMutes();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Pattern mute başarısız");
    }
  };

  return (
    <section className="space-y-4" data-testid="admin-anomaly-timeline-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="admin-anomaly-timeline-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-orange-300" data-testid="admin-anomaly-timeline-title">Anomaly Timeline</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="admin-anomaly-timeline-description">SCANNER_ANOMALY_DETECTED olaylarını filtrele, drill-down yap, export al.</p>
      </header>

      <section className="space-y-3 border border-slate-800 bg-slate-900 p-3" data-testid="admin-anomaly-alert-policy-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-anomaly-alert-policy-title">Uyarı Politikası</p>
        <div className="grid gap-2 md:grid-cols-4" data-testid="admin-anomaly-alert-policy-grid">
          <label className="space-y-1" data-testid="admin-anomaly-alert-policy-warning-threshold-field">
            <span className="text-xs text-slate-400">warning_threshold</span>
            <Input type="number" step="0.01" value={policy.warning_threshold} onChange={(event) => setPolicy((prev) => ({ ...prev, warning_threshold: event.target.value }))} data-testid="admin-anomaly-alert-policy-warning-threshold-input" />
          </label>
          <label className="space-y-1" data-testid="admin-anomaly-alert-policy-critical-threshold-field">
            <span className="text-xs text-slate-400">critical_threshold</span>
            <Input type="number" step="0.01" value={policy.critical_threshold} onChange={(event) => setPolicy((prev) => ({ ...prev, critical_threshold: event.target.value }))} data-testid="admin-anomaly-alert-policy-critical-threshold-input" />
          </label>
          <label className="space-y-1" data-testid="admin-anomaly-alert-policy-smart-mute-window-field">
            <span className="text-xs text-slate-400">smart_mute_window_seconds</span>
            <Input type="number" value={policy.smart_mute_window_seconds} onChange={(event) => setPolicy((prev) => ({ ...prev, smart_mute_window_seconds: event.target.value }))} data-testid="admin-anomaly-alert-policy-smart-mute-window-input" />
          </label>
          <label className="space-y-1" data-testid="admin-anomaly-alert-policy-smart-mute-trigger-field">
            <span className="text-xs text-slate-400">smart_mute_trigger_count</span>
            <Input type="number" value={policy.smart_mute_trigger_count} onChange={(event) => setPolicy((prev) => ({ ...prev, smart_mute_trigger_count: event.target.value }))} data-testid="admin-anomaly-alert-policy-smart-mute-trigger-input" />
          </label>
          <label className="space-y-1" data-testid="admin-anomaly-alert-policy-smart-mute-duration-field">
            <span className="text-xs text-slate-400">smart_mute_duration_seconds</span>
            <Input type="number" value={policy.smart_mute_duration_seconds} onChange={(event) => setPolicy((prev) => ({ ...prev, smart_mute_duration_seconds: event.target.value }))} data-testid="admin-anomaly-alert-policy-smart-mute-duration-input" />
          </label>
          <label className="space-y-1" data-testid="admin-anomaly-alert-policy-notify-min-severity-field">
            <span className="text-xs text-slate-400">notify_min_severity</span>
            <select className="h-10 border border-slate-700 bg-slate-950 px-2 text-sm" value={policy.notify_min_severity} onChange={(event) => setPolicy((prev) => ({ ...prev, notify_min_severity: event.target.value }))} data-testid="admin-anomaly-alert-policy-notify-min-severity-select">
              <option value="warning">warning</option>
              <option value="critical">critical</option>
            </select>
          </label>
          <div className="space-y-1" data-testid="admin-anomaly-alert-policy-notifications-enabled-field">
            <span className="text-xs text-slate-400">notifications_enabled</span>
            <Button type="button" variant={policy.notifications_enabled ? "default" : "outline"} onClick={() => setPolicy((prev) => ({ ...prev, notifications_enabled: !prev.notifications_enabled }))} data-testid="admin-anomaly-alert-policy-notifications-toggle-button">
              {policy.notifications_enabled ? "Açık" : "Kapalı"}
            </Button>
          </div>
        </div>
        <label className="space-y-1" data-testid="admin-anomaly-alert-policy-webhook-urls-field">
          <span className="text-xs text-slate-400">Webhook URL'leri (her satır bir URL)</span>
          <textarea
            value={webhookInput}
            onChange={(event) => setWebhookInput(event.target.value)}
            className="min-h-24 w-full border border-slate-700 bg-slate-950 p-2 text-sm"
            data-testid="admin-anomaly-alert-policy-webhook-urls-textarea"
          />
        </label>
        <div className="flex flex-wrap gap-2" data-testid="admin-anomaly-alert-policy-actions">
          <Button onClick={savePolicy} disabled={isSavingPolicy} data-testid="admin-anomaly-alert-policy-save-button">{isSavingPolicy ? "Kaydediliyor..." : "Policy Kaydet"}</Button>
          <Button variant="outline" onClick={loadAll} data-testid="admin-anomaly-alert-policy-refresh-button">Yenile</Button>
        </div>
      </section>

      <div className="grid gap-2 border border-slate-800 bg-slate-900 p-3 md:grid-cols-8" data-testid="admin-anomaly-timeline-filters-grid">
        <Input value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder="search" data-testid="admin-anomaly-timeline-search-input" />
        <select className="border border-slate-700 bg-slate-950 px-2 text-sm" value={severityFilter} onChange={(event) => setSeverityFilter(event.target.value)} data-testid="admin-anomaly-timeline-severity-select">
          <option value="all">all severity</option>
          <option value="warning">warning</option>
          <option value="critical">critical</option>
          <option value="info">info</option>
        </select>
        <select className="border border-slate-700 bg-slate-950 px-2 text-sm" value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)} data-testid="admin-anomaly-timeline-source-select">
          <option value="all">all source</option>
          {sourceOptions.map((option) => (
            <option key={option.value} value={option.value}>{option.value} ({option.count})</option>
          ))}
        </select>
        <select className="border border-slate-700 bg-slate-950 px-2 text-sm" value={userFilter} onChange={(event) => setUserFilter(event.target.value)} data-testid="admin-anomaly-timeline-user-select">
          <option value="all">all user</option>
          {userOptions.map((option) => (
            <option key={option.value} value={option.value}>{option.value} ({option.count})</option>
          ))}
        </select>
        <select className="border border-slate-700 bg-slate-950 px-2 text-sm" value={windowHours} onChange={(event) => setWindowHours(event.target.value)} data-testid="admin-anomaly-timeline-window-select">
          <option value="24">24h</option>
          <option value="72">72h</option>
          <option value="168">7 gün</option>
          <option value="720">30 gün</option>
        </select>
        <Button onClick={loadTimeline} data-testid="admin-anomaly-timeline-refresh-button">Yenile</Button>
        <Button variant="outline" onClick={exportJson} data-testid="admin-anomaly-timeline-export-json-button">Export JSON</Button>
        <Button variant="outline" onClick={exportCsv} data-testid="admin-anomaly-timeline-export-csv-button">Export CSV</Button>
      </div>

      <div className="grid gap-2 border border-slate-800 bg-slate-900 p-3 md:grid-cols-3" data-testid="admin-anomaly-timeline-presets-panel">
        <div data-testid="admin-anomaly-timeline-severity-presets">
          <p className="text-xs uppercase text-slate-500">Severity Preset</p>
          <div className="mt-1 flex flex-wrap gap-1">
            {[
              { label: "All", value: "all" },
              { label: "Warning", value: "warning" },
              { label: "Critical", value: "critical" },
              { label: "Info", value: "info" },
            ].map((preset) => (
              <Button key={preset.value} size="sm" variant={severityFilter === preset.value ? "default" : "outline"} onClick={() => setSeverityFilter(preset.value)} data-testid={`admin-anomaly-timeline-severity-preset-${preset.value}`}>
                {preset.label}
              </Button>
            ))}
          </div>
        </div>
        <div data-testid="admin-anomaly-timeline-source-presets">
          <p className="text-xs uppercase text-slate-500">Source Preset</p>
          <div className="mt-1 flex flex-wrap gap-1">
            <Button size="sm" variant={sourceFilter === "all" ? "default" : "outline"} onClick={() => setSourceFilter("all")} data-testid="admin-anomaly-timeline-source-preset-all">All</Button>
            {sourceOptions.slice(0, 3).map((preset) => (
              <Button key={preset.value} size="sm" variant={sourceFilter === preset.value ? "default" : "outline"} onClick={() => setSourceFilter(preset.value)} data-testid={`admin-anomaly-timeline-source-preset-${preset.value}`}>
                {preset.value}
              </Button>
            ))}
          </div>
        </div>
        <div data-testid="admin-anomaly-timeline-user-presets">
          <p className="text-xs uppercase text-slate-500">User Preset</p>
          <div className="mt-1 flex flex-wrap gap-1">
            <Button size="sm" variant={userFilter === "all" ? "default" : "outline"} onClick={() => setUserFilter("all")} data-testid="admin-anomaly-timeline-user-preset-all">All</Button>
            {user?.id && (
              <Button size="sm" variant={userFilter === user.id ? "default" : "outline"} onClick={() => setUserFilter(user.id)} data-testid="admin-anomaly-timeline-user-preset-me">Me</Button>
            )}
            {userOptions.slice(0, 2).map((preset) => (
              <Button key={preset.value} size="sm" variant={userFilter === preset.value ? "default" : "outline"} onClick={() => setUserFilter(preset.value)} data-testid={`admin-anomaly-timeline-user-preset-${preset.value}`}>
                {preset.value.slice(0, 8)}...
              </Button>
            ))}
          </div>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-3" data-testid="admin-anomaly-timeline-content-grid">
        <section className="lg:col-span-2 border border-slate-800 bg-slate-900" data-testid="admin-anomaly-timeline-table-panel">
          {isLoading && <p className="p-3 text-sm text-slate-400" data-testid="admin-anomaly-timeline-loading">Yükleniyor...</p>}
          {!isLoading && filteredItems.length === 0 && <p className="p-3 text-sm text-slate-500" data-testid="admin-anomaly-timeline-empty">Kayıt bulunamadı.</p>}
          <Table data-testid="admin-anomaly-timeline-table">
            <TableHeader>
              <TableRow>
                <TableHead>Zaman</TableHead>
                <TableHead>Severity</TableHead>
                <TableHead>User</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Fail Ratio</TableHead>
                <TableHead>Time-to-Recover</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredItems.map((item) => (
                <TableRow key={item.id} onClick={() => setSelectedLogId(item.id)} data-testid={`admin-anomaly-timeline-row-${item.id}`}>
                  <TableCell className="font-mono text-xs">{new Date(item.created_at).toLocaleString("tr-TR")}</TableCell>
                  <TableCell>{item.severity}</TableCell>
                  <TableCell className="font-mono text-xs">{item.actor_user_id || "-"}</TableCell>
                  <TableCell>{sourceOf(item)}</TableCell>
                  <TableCell>{failRatioOf(item).toFixed(3)}</TableCell>
                  <TableCell data-testid={`admin-anomaly-timeline-ttr-${item.id}`}>{ttrByLogId[item.id] != null ? `${ttrByLogId[item.id]}m` : "-"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </section>

        <section className="space-y-3 border border-slate-800 bg-slate-900 p-3" data-testid="admin-anomaly-timeline-drilldown-panel">
          <p className="text-xs uppercase text-slate-500" data-testid="admin-anomaly-timeline-drilldown-title">Drill-down</p>
          {!selectedItem && <p className="mt-2 text-sm text-slate-500" data-testid="admin-anomaly-timeline-drilldown-empty">Kayıt seçin.</p>}
          {selectedItem && (
            <div className="mt-2 space-y-2" data-testid="admin-anomaly-timeline-drilldown-content">
              <p className="text-xs text-slate-300" data-testid="admin-anomaly-timeline-drilldown-time">time={new Date(selectedItem.created_at).toLocaleString("tr-TR")}</p>
              <p className="text-xs text-slate-300" data-testid="admin-anomaly-timeline-drilldown-user">user={selectedItem.actor_user_id || "-"}</p>
              <p className="text-xs text-slate-300" data-testid="admin-anomaly-timeline-drilldown-source">source={sourceOf(selectedItem)}</p>
              <p className="text-xs text-slate-300" data-testid="admin-anomaly-timeline-drilldown-severity">severity={selectedItem.severity}</p>
              <div className="flex flex-wrap items-end gap-2" data-testid="admin-anomaly-timeline-mute-action-row">
                <label className="space-y-1">
                  <span className="text-xs text-slate-400">mute duration (sec)</span>
                  <Input value={muteDurationSeconds} onChange={(event) => setMuteDurationSeconds(event.target.value)} data-testid="admin-anomaly-timeline-mute-duration-input" />
                </label>
                <Button variant="outline" onClick={muteSelectedPattern} data-testid="admin-anomaly-timeline-mute-selected-pattern-button">Pattern Mute</Button>
              </div>
              <div className="max-h-56 overflow-auto rounded border border-slate-700 bg-slate-950 p-2" data-testid="admin-anomaly-timeline-active-mutes-wrap">
                <p className="text-xs uppercase text-slate-500" data-testid="admin-anomaly-timeline-active-mutes-title">Active Mutes</p>
                {(activeMutes || []).map((mute, index) => (
                  <p key={`${mute.payload_hash}-${mute.mute_until}`} className="text-xs text-slate-300" data-testid={`admin-anomaly-timeline-active-mute-item-${index}`}>
                    {String(mute.payload_hash).slice(0, 12)}... until {new Date(mute.mute_until).toLocaleString("tr-TR")}
                  </p>
                ))}
                {(activeMutes || []).length === 0 && <p className="text-xs text-slate-500" data-testid="admin-anomaly-timeline-active-mute-empty">Aktif mute yok.</p>}
              </div>
              <div className="max-h-72 overflow-auto rounded border border-slate-700 bg-slate-950 p-2" data-testid="admin-anomaly-timeline-drilldown-json-wrap">
                <pre className="text-xs text-slate-200" data-testid="admin-anomaly-timeline-drilldown-json">{JSON.stringify(selectedItem.details || {}, null, 2)}</pre>
              </div>
            </div>
          )}
        </section>
      </div>
    </section>
  );
};
