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

  const load = useCallback(async () => {
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

  useEffect(() => {
    load();
  }, [load]);

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

  return (
    <section className="space-y-4" data-testid="admin-anomaly-timeline-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="admin-anomaly-timeline-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-orange-300" data-testid="admin-anomaly-timeline-title">Anomaly Timeline</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="admin-anomaly-timeline-description">SCANNER_ANOMALY_DETECTED olaylarını filtrele, drill-down yap, export al.</p>
      </header>

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
        <Button onClick={load} data-testid="admin-anomaly-timeline-refresh-button">Yenile</Button>
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
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredItems.map((item) => (
                <TableRow key={item.id} onClick={() => setSelectedLogId(item.id)} data-testid={`admin-anomaly-timeline-row-${item.id}`}>
                  <TableCell className="font-mono text-xs">{new Date(item.created_at).toLocaleString("tr-TR")}</TableCell>
                  <TableCell>{item.severity}</TableCell>
                  <TableCell className="font-mono text-xs">{item.actor_user_id || "-"}</TableCell>
                  <TableCell>{sourceOf(item)}</TableCell>
                  <TableCell>{Number(item?.details?.fail_ratio || 0).toFixed(3)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </section>

        <section className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-anomaly-timeline-drilldown-panel">
          <p className="text-xs uppercase text-slate-500" data-testid="admin-anomaly-timeline-drilldown-title">Drill-down</p>
          {!selectedItem && <p className="mt-2 text-sm text-slate-500" data-testid="admin-anomaly-timeline-drilldown-empty">Kayıt seçin.</p>}
          {selectedItem && (
            <div className="mt-2 space-y-2" data-testid="admin-anomaly-timeline-drilldown-content">
              <p className="text-xs text-slate-300" data-testid="admin-anomaly-timeline-drilldown-time">time={new Date(selectedItem.created_at).toLocaleString("tr-TR")}</p>
              <p className="text-xs text-slate-300" data-testid="admin-anomaly-timeline-drilldown-user">user={selectedItem.actor_user_id || "-"}</p>
              <p className="text-xs text-slate-300" data-testid="admin-anomaly-timeline-drilldown-source">source={sourceOf(selectedItem)}</p>
              <p className="text-xs text-slate-300" data-testid="admin-anomaly-timeline-drilldown-severity">severity={selectedItem.severity}</p>
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
