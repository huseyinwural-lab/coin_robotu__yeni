import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

export const AdminReportsArchivePage = () => {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    report_type: "",
    status: "all",
    trigger_source: "all",
    date_from: "",
    date_to: "",
  });

  const loadReports = useCallback(async () => {
    setLoading(true);
    try {
      const params = {
        report_type: filters.report_type || undefined,
        status_filter: filters.status || "all",
        trigger_source: filters.trigger_source || "all",
        date_from: filters.date_from || undefined,
        date_to: filters.date_to || undefined,
      };
      const { data } = await apiClient.get("/admin/reports/archive", { params });
      setReports(data || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Rapor arşivi yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    loadReports();
  }, [loadReports]);

  const downloadReport = async (report) => {
    try {
      const response = await apiClient.get(`/admin/reports/archive/${report.report_id}/download`, {
        params: { verify: true },
        responseType: "blob",
      });
      const url = window.URL.createObjectURL(new Blob([response.data], { type: "text/csv" }));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", report.filename || "report.csv");
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Rapor indirildi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Rapor indirilemedi");
    }
  };

  return (
    <section className="space-y-4" data-testid="admin-report-archive-page">
      <header className="border border-orange-700 bg-slate-900 p-4" data-testid="admin-report-archive-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-orange-300" data-testid="admin-report-archive-title">
          Weekly Report Archive
        </h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="admin-report-archive-description">
          Haftalık CSV raporlarının arşivi. Filtreleyin, checksum kontrol edin ve indirin.
        </p>
      </header>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="admin-report-archive-filters">
        <div className="grid gap-2 md:grid-cols-5" data-testid="admin-report-archive-filter-grid">
          <Input
            placeholder="report_type"
            value={filters.report_type}
            onChange={(event) => setFilters((prev) => ({ ...prev, report_type: event.target.value }))}
            data-testid="report-archive-report-type-input"
          />
          <Input
            placeholder="date_from (ISO)"
            value={filters.date_from}
            onChange={(event) => setFilters((prev) => ({ ...prev, date_from: event.target.value }))}
            data-testid="report-archive-date-from-input"
          />
          <Input
            placeholder="date_to (ISO)"
            value={filters.date_to}
            onChange={(event) => setFilters((prev) => ({ ...prev, date_to: event.target.value }))}
            data-testid="report-archive-date-to-input"
          />
          <select
            value={filters.status}
            onChange={(event) => setFilters((prev) => ({ ...prev, status: event.target.value }))}
            className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
            data-testid="report-archive-status-select"
          >
            <option value="all">all</option>
            <option value="generated">generated</option>
            <option value="failed">failed</option>
            <option value="purged">purged</option>
          </select>
          <select
            value={filters.trigger_source}
            onChange={(event) => setFilters((prev) => ({ ...prev, trigger_source: event.target.value }))}
            className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
            data-testid="report-archive-trigger-select"
          >
            <option value="all">all</option>
            <option value="scheduled">scheduled</option>
            <option value="manual">manual</option>
          </select>
        </div>
        <Button className="mt-3 bg-orange-500 text-black hover:bg-orange-600" onClick={loadReports} data-testid="report-archive-refresh-button">
          Refresh
        </Button>
      </div>

      {loading && <p className="text-sm text-slate-400" data-testid="report-archive-loading">Yükleniyor...</p>}
      {!loading && reports.length === 0 && (
        <p className="text-sm text-slate-400" data-testid="report-archive-empty">Arşivde rapor yok.</p>
      )}

      <div className="space-y-3" data-testid="report-archive-list">
        {reports.map((report) => (
          <div key={report.report_id} className="border border-slate-700 bg-slate-900 p-3" data-testid={`report-archive-row-${report.report_id}`}>
            <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3" data-testid={`report-archive-grid-${report.report_id}`}>
              <p className="text-sm" data-testid={`report-archive-filename-${report.report_id}`}>file: {report.filename}</p>
              <p className="text-sm" data-testid={`report-archive-status-${report.report_id}`}>status: {report.status}</p>
              <p className="text-sm" data-testid={`report-archive-trigger-${report.report_id}`}>source: {report.trigger_source}</p>
              <p className="text-xs text-slate-400" data-testid={`report-archive-period-${report.report_id}`}>
                period: {new Date(report.period_start).toLocaleDateString()} → {new Date(report.period_end).toLocaleDateString()}
              </p>
              <p className="text-xs text-slate-400" data-testid={`report-archive-size-${report.report_id}`}>size: {report.size_bytes} bytes</p>
              <p className="text-xs text-slate-400" data-testid={`report-archive-generated-${report.report_id}`}>
                generated: {new Date(report.generated_at).toLocaleString()}
              </p>
            </div>
            <p className="mt-2 break-all text-xs text-slate-400" data-testid={`report-archive-sha-${report.report_id}`}>
              sha256: {report.sha256 || "-"}
            </p>
            <div className="mt-3 flex flex-wrap gap-2" data-testid={`report-archive-actions-${report.report_id}`}>
              <Button
                size="sm"
                className="bg-emerald-500 text-black hover:bg-emerald-600"
                onClick={() => downloadReport(report)}
                data-testid={`report-archive-download-${report.report_id}`}
                disabled={report.status !== "generated"}
              >
                Download
              </Button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
};
