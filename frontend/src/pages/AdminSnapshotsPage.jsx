import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

const downloadBlob = (blobData, filename) => {
  const blob = new Blob([blobData]);
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.URL.revokeObjectURL(url);
};

export const AdminSnapshotsPage = () => {
  const [loading, setLoading] = useState(false);
  const [snapshots, setSnapshots] = useState([]);
  const [comparePayload, setComparePayload] = useState(null);
  const [running, setRunning] = useState(false);
  const [filters, setFilters] = useState({
    environment: "live",
    snapshot_type: "daily",
    as_of_date: "",
    churn_inactive_days: 30,
    top_limit: 20,
    base_snapshot_id: "",
    target_snapshot_id: "",
  });

  const loadSnapshots = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/admin/snapshots", {
        params: {
          environment: filters.environment,
          snapshot_type: filters.snapshot_type,
          limit: 50,
        },
      });
      const items = data?.items || [];
      setSnapshots(items);
      setFilters((prev) => ({
        ...prev,
        target_snapshot_id: prev.target_snapshot_id || items[0]?.id || "",
        base_snapshot_id: prev.base_snapshot_id || items[1]?.id || "",
      }));
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Snapshot listesi alınamadı");
      setSnapshots([]);
    } finally {
      setLoading(false);
    }
  }, [filters.environment, filters.snapshot_type]);

  useEffect(() => {
    loadSnapshots();
  }, [loadSnapshots]);

  const runSnapshot = async () => {
    setRunning(true);
    try {
      await apiClient.post("/admin/snapshots/run", null, {
        params: {
          environment: filters.environment,
          snapshot_type: filters.snapshot_type,
          as_of_date: filters.as_of_date || undefined,
          churn_inactive_days: filters.churn_inactive_days,
          top_limit: filters.top_limit,
        },
      });
      toast.success("Snapshot başarıyla oluşturuldu");
      await loadSnapshots();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Snapshot oluşturulamadı");
    } finally {
      setRunning(false);
    }
  };

  const compareSnapshots = async () => {
    if (!filters.base_snapshot_id || !filters.target_snapshot_id) {
      toast.error("Karşılaştırma için iki snapshot seçin");
      return;
    }
    try {
      const { data } = await apiClient.get("/admin/snapshots/compare", {
        params: {
          base_snapshot_id: filters.base_snapshot_id,
          target_snapshot_id: filters.target_snapshot_id,
        },
      });
      setComparePayload(data || null);
      toast.success("Snapshot karşılaştırması hazır");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Snapshot karşılaştırması başarısız");
    }
  };

  const runExport = async (scope, format) => {
    try {
      const endpoint = scope === "revenue" ? "/admin/export/revenue" : "/admin/export/user-economics";
      const response = await apiClient.get(endpoint, {
        params: {
          environment: filters.environment,
          churn_inactive_days: filters.churn_inactive_days,
          top_limit: 200,
          output: format,
        },
        responseType: "blob",
      });
      downloadBlob(response.data, `${scope}_export.${format}`);
      toast.success(`${scope} ${format.toUpperCase()} export hazır`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Export başarısız");
    }
  };

  const kpiRows = useMemo(() => comparePayload?.delta?.kpis || [], [comparePayload]);
  const topUserDelta = comparePayload?.delta?.top_users || [];
  const segmentDelta = comparePayload?.delta?.segments || [];

  const summaryCards = useMemo(() => {
    const preferred = ["total_revenue_usd", "today_revenue_usd", "total_users", "churn_rate_pct"];
    return kpiRows.filter((item) => preferred.includes(item.metric));
  }, [kpiRows]);

  return (
    <section className="space-y-5" data-testid="admin-snapshots-page">
      <header className="rounded border border-black/30 bg-lime-100 p-4" data-testid="admin-snapshots-header">
        <h1 className="text-4xl font-black uppercase" data-testid="admin-snapshots-title">Export & Snapshot Layer</h1>
        <p className="text-sm text-black/70" data-testid="admin-snapshots-subtitle">Revenue/User Economics export, snapshot çalıştırma ve delta karşılaştırma merkezi.</p>
      </header>

      <section className="grid gap-2 rounded border border-black/30 bg-white p-3 md:grid-cols-7" data-testid="admin-snapshots-filter-panel">
        <select
          className="h-10 rounded border px-2"
          value={filters.environment}
          onChange={(event) => setFilters((prev) => ({ ...prev, environment: event.target.value }))}
          data-testid="admin-snapshots-filter-environment-select"
        >
          <option value="live">live</option>
          <option value="live">live</option>
        </select>
        <select
          className="h-10 rounded border px-2"
          value={filters.snapshot_type}
          onChange={(event) => setFilters((prev) => ({ ...prev, snapshot_type: event.target.value }))}
          data-testid="admin-snapshots-filter-snapshot-type-select"
        >
          <option value="daily">daily</option>
          <option value="weekly">weekly</option>
        </select>
        <Input type="datetime-local" value={filters.as_of_date} onChange={(event) => setFilters((prev) => ({ ...prev, as_of_date: event.target.value }))} data-testid="admin-snapshots-filter-as-of-date-input" />
        <Input type="number" min={1} max={365} value={filters.churn_inactive_days} onChange={(event) => setFilters((prev) => ({ ...prev, churn_inactive_days: Number(event.target.value || 30) }))} data-testid="admin-snapshots-filter-churn-days-input" />
        <Input type="number" min={1} max={200} value={filters.top_limit} onChange={(event) => setFilters((prev) => ({ ...prev, top_limit: Number(event.target.value || 20) }))} data-testid="admin-snapshots-filter-top-limit-input" />
        <Button onClick={runSnapshot} disabled={running} data-testid="admin-snapshots-run-button">{running ? "Çalışıyor" : "Snapshot Çalıştır"}</Button>
        <Button variant="outline" onClick={loadSnapshots} data-testid="admin-snapshots-refresh-button">Listeyi Yenile</Button>
      </section>

      <section className="flex flex-wrap gap-2" data-testid="admin-snapshots-export-buttons-row">
        <Button variant="outline" onClick={() => runExport("revenue", "csv")} data-testid="admin-snapshots-export-revenue-csv-button">Revenue CSV</Button>
        <Button variant="outline" onClick={() => runExport("revenue", "xlsx")} data-testid="admin-snapshots-export-revenue-xlsx-button">Revenue XLSX</Button>
        <Button variant="outline" onClick={() => runExport("user_economics", "csv")} data-testid="admin-snapshots-export-user-economics-csv-button">User Economics CSV</Button>
        <Button variant="outline" onClick={() => runExport("user_economics", "xlsx")} data-testid="admin-snapshots-export-user-economics-xlsx-button">User Economics XLSX</Button>
      </section>

      <section className="rounded border border-black/30 bg-white p-3" data-testid="admin-snapshots-list-card">
        <h2 className="mb-2 text-lg font-semibold" data-testid="admin-snapshots-list-title">Snapshot Listesi</h2>
        <div className="grid gap-2 md:grid-cols-3" data-testid="admin-snapshots-compare-controls">
          <select className="h-10 rounded border px-2" value={filters.base_snapshot_id} onChange={(event) => setFilters((prev) => ({ ...prev, base_snapshot_id: event.target.value }))} data-testid="admin-snapshots-base-select">
            <option value="">Base snapshot seç</option>
            {snapshots.map((row) => (
              <option key={`base-${row.id}`} value={row.id}>{row.snapshot_date}</option>
            ))}
          </select>
          <select className="h-10 rounded border px-2" value={filters.target_snapshot_id} onChange={(event) => setFilters((prev) => ({ ...prev, target_snapshot_id: event.target.value }))} data-testid="admin-snapshots-target-select">
            <option value="">Target snapshot seç</option>
            {snapshots.map((row) => (
              <option key={`target-${row.id}`} value={row.id}>{row.snapshot_date}</option>
            ))}
          </select>
          <Button onClick={compareSnapshots} data-testid="admin-snapshots-compare-button">Compare</Button>
        </div>

        <Table className="mt-3" data-testid="admin-snapshots-list-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="admin-snapshots-list-head-date">Date</TableHead>
              <TableHead data-testid="admin-snapshots-list-head-type">Type</TableHead>
              <TableHead data-testid="admin-snapshots-list-head-env">Env</TableHead>
              <TableHead data-testid="admin-snapshots-list-head-revenue">Total Revenue</TableHead>
              <TableHead data-testid="admin-snapshots-list-head-users">Users</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {snapshots.map((row) => (
              <TableRow key={row.id} data-testid={`admin-snapshots-list-row-${row.id}`}>
                <TableCell data-testid={`admin-snapshots-list-date-${row.id}`}>{row.snapshot_date}</TableCell>
                <TableCell data-testid={`admin-snapshots-list-type-${row.id}`}>{row.snapshot_type}</TableCell>
                <TableCell data-testid={`admin-snapshots-list-env-${row.id}`}>{row.environment}</TableCell>
                <TableCell data-testid={`admin-snapshots-list-revenue-${row.id}`}>{Number(row?.kpis?.total_revenue_usd || 0).toFixed(6)}</TableCell>
                <TableCell data-testid={`admin-snapshots-list-users-${row.id}`}>{row?.kpis?.total_users || 0}</TableCell>
              </TableRow>
            ))}
            {!snapshots.length && <TableRow><TableCell colSpan={5} className="text-center text-sm text-slate-500" data-testid="admin-snapshots-list-empty">Snapshot yok</TableCell></TableRow>}
          </TableBody>
        </Table>
      </section>

      <section className="grid gap-3 md:grid-cols-4" data-testid="admin-snapshots-kpi-delta-grid">
        {summaryCards.map((item) => (
          <article key={item.metric} className="rounded border border-black/30 bg-white p-3" data-testid={`admin-snapshots-kpi-delta-card-${item.metric}`}>
            <p className="text-xs uppercase" data-testid={`admin-snapshots-kpi-delta-metric-${item.metric}`}>{item.metric}</p>
            <p className="text-sm" data-testid={`admin-snapshots-kpi-delta-from-${item.metric}`}>From: {Number(item.from || 0).toFixed(4)}</p>
            <p className="text-sm" data-testid={`admin-snapshots-kpi-delta-to-${item.metric}`}>To: {Number(item.to || 0).toFixed(4)}</p>
            <p className={`text-sm font-semibold ${Number(item.delta || 0) >= 0 ? "text-emerald-600" : "text-red-600"}`} data-testid={`admin-snapshots-kpi-delta-value-${item.metric}`}>
              Δ {Number(item.delta || 0).toFixed(4)}
            </p>
          </article>
        ))}
        {!summaryCards.length && <p className="text-xs text-slate-500" data-testid="admin-snapshots-kpi-delta-empty">Karşılaştırma sonucu yok</p>}
      </section>

      <section className="grid gap-3 lg:grid-cols-2" data-testid="admin-snapshots-delta-tables-grid">
        <article className="rounded border border-black/30 bg-white p-3" data-testid="admin-snapshots-top-users-delta-card">
          <h2 className="mb-2 text-lg font-semibold" data-testid="admin-snapshots-top-users-delta-title">Top Kullanıcı Delta</h2>
          <Table data-testid="admin-snapshots-top-users-delta-table">
            <TableHeader>
              <TableRow>
                <TableHead data-testid="admin-snapshots-top-users-delta-head-email">Email</TableHead>
                <TableHead data-testid="admin-snapshots-top-users-delta-head-from">From</TableHead>
                <TableHead data-testid="admin-snapshots-top-users-delta-head-to">To</TableHead>
                <TableHead data-testid="admin-snapshots-top-users-delta-head-delta">Delta</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {topUserDelta.map((row) => (
                <TableRow key={row.user_id} data-testid={`admin-snapshots-top-users-delta-row-${row.user_id}`}>
                  <TableCell data-testid={`admin-snapshots-top-users-delta-email-${row.user_id}`}>{row.email}</TableCell>
                  <TableCell data-testid={`admin-snapshots-top-users-delta-from-${row.user_id}`}>{Number(row.from_revenue_usd || 0).toFixed(6)}</TableCell>
                  <TableCell data-testid={`admin-snapshots-top-users-delta-to-${row.user_id}`}>{Number(row.to_revenue_usd || 0).toFixed(6)}</TableCell>
                  <TableCell data-testid={`admin-snapshots-top-users-delta-value-${row.user_id}`}>{Number(row.delta_revenue_usd || 0).toFixed(6)}</TableCell>
                </TableRow>
              ))}
              {!topUserDelta.length && <TableRow><TableCell colSpan={4} className="text-center text-sm text-slate-500" data-testid="admin-snapshots-top-users-delta-empty">Top kullanıcı delta yok</TableCell></TableRow>}
            </TableBody>
          </Table>
        </article>

        <article className="rounded border border-black/30 bg-white p-3" data-testid="admin-snapshots-segment-delta-card">
          <h2 className="mb-2 text-lg font-semibold" data-testid="admin-snapshots-segment-delta-title">Segment Delta</h2>
          <Table data-testid="admin-snapshots-segment-delta-table">
            <TableHeader>
              <TableRow>
                <TableHead data-testid="admin-snapshots-segment-delta-head-segment">Segment</TableHead>
                <TableHead data-testid="admin-snapshots-segment-delta-head-users">Users Δ</TableHead>
                <TableHead data-testid="admin-snapshots-segment-delta-head-revenue">Revenue Δ</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {segmentDelta.map((row) => (
                <TableRow key={row.segment} data-testid={`admin-snapshots-segment-delta-row-${row.segment}`}>
                  <TableCell data-testid={`admin-snapshots-segment-delta-segment-${row.segment}`}>{row.segment}</TableCell>
                  <TableCell data-testid={`admin-snapshots-segment-delta-users-${row.segment}`}>{row.delta_users}</TableCell>
                  <TableCell data-testid={`admin-snapshots-segment-delta-revenue-${row.segment}`}>{Number(row.delta_revenue_usd || 0).toFixed(6)}</TableCell>
                </TableRow>
              ))}
              {!segmentDelta.length && <TableRow><TableCell colSpan={3} className="text-center text-sm text-slate-500" data-testid="admin-snapshots-segment-delta-empty">Segment delta yok</TableCell></TableRow>}
            </TableBody>
          </Table>
        </article>
      </section>

      {loading && <p className="text-xs text-slate-500" data-testid="admin-snapshots-loading-indicator">Yükleniyor...</p>}
    </section>
  );
};
