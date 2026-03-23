import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

const windowOptions = ["24h", "7d", "30d"];

const toIsoOrNull = (dateTimeLocal) => {
  if (!dateTimeLocal) {
    return null;
  }
  const date = new Date(dateTimeLocal);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date.toISOString();
};

export default function AdminStrategyObservabilityDetailPage() {
  const navigate = useNavigate();
  const { strategyId } = useParams();

  const [windowRange, setWindowRange] = useState("24h");
  const [timeFrom, setTimeFrom] = useState("");
  const [timeTo, setTimeTo] = useState("");
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);
  const [autoRefreshSeconds, setAutoRefreshSeconds] = useState(30);

  const [strategyOptions, setStrategyOptions] = useState([]);
  const [selectedStrategyId, setSelectedStrategyId] = useState(strategyId || "");

  const [loading, setLoading] = useState(false);
  const [timelineLoading, setTimelineLoading] = useState(false);

  const [detailData, setDetailData] = useState(null);
  const [timelineData, setTimelineData] = useState({ summary: null, items: [] });
  const [timelineKpis, setTimelineKpis] = useState(null);

  const activeFilters = useMemo(
    () => ({
      window: windowRange,
      strategy_id: selectedStrategyId,
      time_from: toIsoOrNull(timeFrom),
      time_to: toIsoOrNull(timeTo),
      top_n: 1000,
    }),
    [selectedStrategyId, timeFrom, timeTo, windowRange]
  );

  const loadStrategies = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/admin/strategy/observability/strategies", {
        params: {
          window: windowRange,
          time_from: toIsoOrNull(timeFrom),
          time_to: toIsoOrNull(timeTo),
        },
      });
      const items = data?.items || [];
      setStrategyOptions(items);
      if (!selectedStrategyId && items.length > 0) {
        setSelectedStrategyId(items[0]);
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Strategy selector yüklenemedi");
      setStrategyOptions([]);
    }
  }, [selectedStrategyId, timeFrom, timeTo, windowRange]);

  const loadDetail = useCallback(async () => {
    if (!selectedStrategyId) {
      setDetailData(null);
      return;
    }
    setLoading(true);
    try {
      const { data } = await apiClient.get(`/admin/strategy/observability/${selectedStrategyId}/detail`, {
        params: {
          window: windowRange,
          time_from: toIsoOrNull(timeFrom),
          time_to: toIsoOrNull(timeTo),
        },
      });
      setDetailData(data || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Strategy detail yüklenemedi");
      setDetailData(null);
    } finally {
      setLoading(false);
    }
  }, [selectedStrategyId, timeFrom, timeTo, windowRange]);

  const loadTimeline = useCallback(async () => {
    if (!selectedStrategyId) {
      setTimelineData({ summary: null, items: [] });
      return;
    }
    setTimelineLoading(true);
    try {
      const { data } = await apiClient.get("/admin/strategy/action-impact-timeline", {
        params: {
          window: windowRange,
          strategy_id: selectedStrategyId,
          time_from: toIsoOrNull(timeFrom),
          time_to: toIsoOrNull(timeTo),
          limit: 200,
        },
      });
      setTimelineData({
        summary: data?.summary || null,
        items: data?.items || [],
      });
      setTimelineKpis(data?.kpi_cards || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Action impact timeline yüklenemedi");
      setTimelineData({ summary: null, items: [] });
      setTimelineKpis(null);
    } finally {
      setTimelineLoading(false);
    }
  }, [selectedStrategyId, timeFrom, timeTo, windowRange]);

  const refreshAll = useCallback(async () => {
    await Promise.all([loadStrategies(), loadDetail(), loadTimeline()]);
  }, [loadDetail, loadStrategies, loadTimeline]);

  const exportObservability = async (exportFormat) => {
    try {
      if (exportFormat === "json") {
        const { data } = await apiClient.get("/admin/strategy/observability/export", {
          params: {
            ...activeFilters,
            export_format: "json",
          },
        });
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json;charset=utf-8" });
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = `observability_${selectedStrategyId || "all"}_${windowRange}.json`;
        document.body.append(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(link.href);
      } else {
        const response = await apiClient.get("/admin/strategy/observability/export", {
          params: {
            ...activeFilters,
            export_format: "csv",
          },
          responseType: "blob",
        });
        const contentDisposition = response.headers?.["content-disposition"] || "";
        const fileNameMatch = /filename="([^"]+)"/.exec(contentDisposition);
        const filename = fileNameMatch?.[1] || `observability_${selectedStrategyId || "all"}_${windowRange}.csv`;
        const link = document.createElement("a");
        link.href = URL.createObjectURL(response.data);
        link.download = filename;
        document.body.append(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(link.href);
      }
      toast.success(`${exportFormat.toUpperCase()} export hazırlandı`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || `${exportFormat.toUpperCase()} export başarısız`);
    }
  };

  useEffect(() => {
    loadStrategies();
  }, [loadStrategies]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  useEffect(() => {
    loadTimeline();
  }, [loadTimeline]);

  useEffect(() => {
    if (!autoRefreshEnabled) {
      return undefined;
    }
    const intervalMs = Math.max(Number(autoRefreshSeconds) || 30, 10) * 1000;
    const timer = window.setInterval(() => {
      refreshAll();
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [autoRefreshEnabled, autoRefreshSeconds, refreshAll]);

  return (
    <section className="space-y-4" data-testid="strategy-observability-detail-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="strategy-observability-detail-header">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="strategy-observability-detail-header-row">
          <div>
            <h1 className="text-4xl font-black uppercase tracking-tight" data-testid="strategy-observability-detail-title">
              Strategy Report Detail
            </h1>
            <p className="text-sm text-black/80" data-testid="strategy-observability-detail-subtitle">
              Trend grafikleri, filtreler, export ve action impact timeline
            </p>
          </div>
          <Button
            variant="outline"
            className="border-black bg-white text-black"
            onClick={() => navigate("/admin/strategy/observability")}
            data-testid="strategy-observability-detail-back-button"
          >
            Ana Sayfaya Dön
          </Button>
        </div>
      </header>

      <section className="grid gap-2 border border-black/30 bg-orange-100 p-4 md:grid-cols-6" data-testid="strategy-observability-detail-filters">
        <select
          className="border border-black/40 bg-white px-3 py-2 text-sm"
          value={windowRange}
          onChange={(event) => setWindowRange(event.target.value)}
          data-testid="strategy-observability-detail-window-select"
        >
          {windowOptions.map((value) => (
            <option key={value} value={value} data-testid={`strategy-observability-detail-window-option-${value}`}>
              {value}
            </option>
          ))}
        </select>

        <select
          className="border border-black/40 bg-white px-3 py-2 text-sm"
          value={selectedStrategyId}
          onChange={(event) => setSelectedStrategyId(event.target.value)}
          data-testid="strategy-observability-detail-strategy-select"
        >
          <option value="" data-testid="strategy-observability-detail-strategy-option-empty">strategy seçin</option>
          {strategyOptions.map((value) => (
            <option key={value} value={value} data-testid={`strategy-observability-detail-strategy-option-${value}`}>
              {value}
            </option>
          ))}
        </select>

        <Input
          type="datetime-local"
          value={timeFrom}
          onChange={(event) => setTimeFrom(event.target.value)}
          data-testid="strategy-observability-detail-time-from-input"
        />
        <Input
          type="datetime-local"
          value={timeTo}
          onChange={(event) => setTimeTo(event.target.value)}
          data-testid="strategy-observability-detail-time-to-input"
        />

        <div className="flex items-center gap-2" data-testid="strategy-observability-detail-auto-refresh-row">
          <Switch
            checked={autoRefreshEnabled}
            onCheckedChange={(checked) => setAutoRefreshEnabled(Boolean(checked))}
            data-testid="strategy-observability-detail-auto-refresh-switch"
          />
          <span className="text-xs">Auto refresh</span>
          <Input
            type="number"
            min={10}
            max={180}
            value={autoRefreshSeconds}
            onChange={(event) => setAutoRefreshSeconds(Math.min(Math.max(Number(event.target.value) || 30, 10), 180))}
            className="w-24"
            data-testid="strategy-observability-detail-auto-refresh-seconds-input"
          />
        </div>

        <div className="flex gap-2" data-testid="strategy-observability-detail-filter-actions-row">
          <Button
            className="border border-black bg-black text-orange-300 hover:bg-zinc-800"
            onClick={refreshAll}
            data-testid="strategy-observability-detail-refresh-button"
          >
            Yenile
          </Button>
          <Button
            variant="outline"
            className="border-black bg-white text-black"
            onClick={() => exportObservability("csv")}
            data-testid="strategy-observability-detail-export-csv-button"
          >
            CSV Export
          </Button>
          <Button
            variant="outline"
            className="border-black bg-white text-black"
            onClick={() => exportObservability("json")}
            data-testid="strategy-observability-detail-export-json-button"
          >
            JSON Export
          </Button>
        </div>
      </section>

      <section className="grid gap-3 lg:grid-cols-4" data-testid="strategy-observability-detail-summary-grid">
        <div className="border border-black/30 bg-orange-100 p-3" data-testid="strategy-observability-detail-summary-total-card">
          <p className="text-xs uppercase">Signals Total</p>
          <p className="text-2xl font-bold" data-testid="strategy-observability-detail-summary-total-value">
            {detailData?.summary?.signals_total ?? 0}
          </p>
        </div>
        <div className="border border-black/30 bg-orange-100 p-3" data-testid="strategy-observability-detail-summary-selected-card">
          <p className="text-xs uppercase">Selected</p>
          <p className="text-2xl font-bold" data-testid="strategy-observability-detail-summary-selected-value">
            {detailData?.summary?.signals_selected ?? 0}
          </p>
        </div>
        <div className="border border-black/30 bg-orange-100 p-3" data-testid="strategy-observability-detail-summary-rejected-card">
          <p className="text-xs uppercase">Rejected</p>
          <p className="text-2xl font-bold" data-testid="strategy-observability-detail-summary-rejected-value">
            {detailData?.summary?.signals_rejected ?? 0}
          </p>
        </div>
        <div className="border border-black/30 bg-orange-100 p-3" data-testid="strategy-observability-detail-summary-score-card">
          <p className="text-xs uppercase">Avg Adjusted</p>
          <p className="text-2xl font-bold" data-testid="strategy-observability-detail-summary-score-value">
            {detailData?.summary?.avg_adjusted_score ?? 0}
          </p>
        </div>
      </section>

      <section className="grid gap-3 lg:grid-cols-2" data-testid="strategy-observability-detail-trend-grid">
        <div className="border border-black/30 bg-orange-100 p-4" data-testid="strategy-observability-detail-trend-chart-panel">
          <h3 className="text-lg font-bold" data-testid="strategy-observability-detail-trend-chart-title">Temel Trend Grafikleri</h3>
          <div className="mt-3 space-y-2" data-testid="strategy-observability-detail-trend-chart-rows">
            {(detailData?.trend_rows || []).map((row, index) => {
              const maxCount = Math.max(
                ...(detailData?.trend_rows || []).map((item) => (item.selected_count || 0) + (item.rejected_count || 0)),
                1
              );
              const total = (row.selected_count || 0) + (row.rejected_count || 0);
              const barWidth = Math.max((total / maxCount) * 100, 6);
              return (
                <div key={`${row.bucket}-${index}`} className="space-y-1" data-testid={`strategy-observability-detail-trend-row-${index}`}>
                  <p className="text-xs" data-testid={`strategy-observability-detail-trend-label-${index}`}>
                    {row.bucket} · sel:{row.selected_count} · rej:{row.rejected_count} · avg:{row.avg_adjusted_score}
                  </p>
                  <div className="h-3 w-full border border-black/30 bg-white" data-testid={`strategy-observability-detail-trend-bar-wrap-${index}`}>
                    <div className="h-full bg-black" style={{ width: `${barWidth}%` }} data-testid={`strategy-observability-detail-trend-bar-fill-${index}`} />
                  </div>
                </div>
              );
            })}
            {!loading && (detailData?.trend_rows || []).length === 0 && (
              <p className="text-sm text-black/70" data-testid="strategy-observability-detail-trend-empty">Trend verisi yok.</p>
            )}
          </div>
        </div>

        <div className="border border-black/30 bg-orange-100 p-4" data-testid="strategy-observability-detail-symbols-panel">
          <h3 className="text-lg font-bold" data-testid="strategy-observability-detail-symbols-title">Top Symbols & Rejection Reasons</h3>
          <div className="mt-3 space-y-2" data-testid="strategy-observability-detail-symbols-list">
            {(detailData?.top_symbols || []).slice(0, 12).map((row, index) => (
              <p key={`${row.symbol}-${index}`} className="text-xs" data-testid={`strategy-observability-detail-symbol-item-${index}`}>
                {row.symbol}: {row.count}
              </p>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap gap-2" data-testid="strategy-observability-detail-rejection-reason-chips">
            {(detailData?.rejection_reasons || []).slice(0, 12).map((row, index) => (
              <Badge key={`${row.reason}-${index}`} className="border border-black bg-white text-black" data-testid={`strategy-observability-detail-reason-chip-${index}`}>
                {row.reason} ({row.count})
              </Badge>
            ))}
          </div>
        </div>
      </section>

      <section className="border border-black/30 bg-orange-100 p-4" data-testid="strategy-observability-detail-timeline-panel">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="strategy-observability-detail-timeline-header-row">
          <h3 className="text-lg font-bold" data-testid="strategy-observability-detail-timeline-title">Action Impact Timeline</h3>
          <div className="flex gap-2" data-testid="strategy-observability-detail-timeline-summary-badges">
            <Badge className="border border-black bg-white text-black" data-testid="strategy-observability-detail-timeline-total-badge">
              total: {timelineData?.summary?.total ?? 0}
            </Badge>
            <Badge className="border border-black bg-white text-black" data-testid="strategy-observability-detail-timeline-manual-badge">
              manual: {timelineData?.summary?.manual_action_count ?? 0}
            </Badge>
            <Badge className="border border-black bg-white text-black" data-testid="strategy-observability-detail-timeline-system-badge">
              system: {timelineData?.summary?.system_reaction_count ?? 0}
            </Badge>
          </div>
        </div>

        <div className="mt-3 grid gap-2 md:grid-cols-3" data-testid="strategy-observability-detail-kpi-cards-grid">
          {[
            { key: "selected_signals", label: "Selected" },
            { key: "rejected_signals", label: "Rejected" },
            { key: "risk_breaches", label: "Risk Breaches" },
          ].map((card) => {
            const values = timelineKpis?.[card.key] || { before: 0, after: 0, delta: 0 };
            return (
              <div key={card.key} className="border border-black/30 bg-white p-2" data-testid={`strategy-observability-detail-kpi-card-${card.key}`}>
                <p className="text-xs font-semibold" data-testid={`strategy-observability-detail-kpi-title-${card.key}`}>{card.label}</p>
                <p className="text-xs" data-testid={`strategy-observability-detail-kpi-before-${card.key}`}>before: {values.before ?? 0}</p>
                <p className="text-xs" data-testid={`strategy-observability-detail-kpi-after-${card.key}`}>after: {values.after ?? 0}</p>
                <p className="text-xs" data-testid={`strategy-observability-detail-kpi-delta-${card.key}`}>delta: {values.delta ?? 0}</p>
              </div>
            );
          })}
        </div>

        <div className="mt-3 overflow-x-auto border border-black/25 bg-white" data-testid="strategy-observability-detail-timeline-table-wrapper">
          <Table data-testid="strategy-observability-detail-timeline-table">
            <TableHeader>
              <TableRow>
                <TableHead data-testid="strategy-observability-detail-timeline-head-time">Time</TableHead>
                <TableHead data-testid="strategy-observability-detail-timeline-head-type">Type</TableHead>
                <TableHead data-testid="strategy-observability-detail-timeline-head-action">Action</TableHead>
                <TableHead data-testid="strategy-observability-detail-timeline-head-role">Role</TableHead>
                <TableHead data-testid="strategy-observability-detail-timeline-head-reason">Reason</TableHead>
                <TableHead data-testid="strategy-observability-detail-timeline-head-chain">Chain</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(timelineData?.items || []).map((row, index) => (
                <TableRow key={`${row.event_id}-${index}`} data-testid={`strategy-observability-detail-timeline-row-${index}`}>
                  <TableCell className="text-xs" data-testid={`strategy-observability-detail-timeline-time-${index}`}>
                    {row.timestamp ? new Date(row.timestamp).toLocaleString() : "-"}
                  </TableCell>
                  <TableCell data-testid={`strategy-observability-detail-timeline-type-${index}`}>{row.event_type}</TableCell>
                  <TableCell data-testid={`strategy-observability-detail-timeline-action-${index}`}>{row.action || "-"}</TableCell>
                  <TableCell data-testid={`strategy-observability-detail-timeline-role-${index}`}>{row.actor_role || "-"}</TableCell>
                  <TableCell data-testid={`strategy-observability-detail-timeline-reason-${index}`}>{row.reason || "-"}</TableCell>
                  <TableCell data-testid={`strategy-observability-detail-timeline-chain-${index}`}>{row.chain_ref || "-"}</TableCell>
                </TableRow>
              ))}
              {!timelineLoading && (timelineData?.items || []).length === 0 && (
                <TableRow data-testid="strategy-observability-detail-timeline-empty-row">
                  <TableCell colSpan={6} className="text-center text-sm text-black/70" data-testid="strategy-observability-detail-timeline-empty-text">
                    Timeline verisi bulunamadı.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </section>

      <section className="border border-black/30 bg-orange-100 p-4" data-testid="strategy-observability-detail-recent-rows-panel">
        <h3 className="text-lg font-bold" data-testid="strategy-observability-detail-recent-rows-title">Recent Rows</h3>
        <div className="mt-3 overflow-x-auto border border-black/25 bg-white" data-testid="strategy-observability-detail-recent-rows-table-wrapper">
          <Table data-testid="strategy-observability-detail-recent-rows-table">
            <TableHeader>
              <TableRow>
                <TableHead data-testid="strategy-observability-detail-recent-rows-head-time">Time</TableHead>
                <TableHead data-testid="strategy-observability-detail-recent-rows-head-symbol">Symbol</TableHead>
                <TableHead data-testid="strategy-observability-detail-recent-rows-head-event">Event</TableHead>
                <TableHead data-testid="strategy-observability-detail-recent-rows-head-score">Adjusted</TableHead>
                <TableHead data-testid="strategy-observability-detail-recent-rows-head-reason">Reason</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(detailData?.recent_rows || []).map((row, index) => (
                <TableRow key={`${row.signal_id}-${index}`} data-testid={`strategy-observability-detail-recent-rows-row-${index}`}>
                  <TableCell className="text-xs" data-testid={`strategy-observability-detail-recent-rows-time-${index}`}>
                    {row.created_at ? new Date(row.created_at).toLocaleString() : "-"}
                  </TableCell>
                  <TableCell data-testid={`strategy-observability-detail-recent-rows-symbol-${index}`}>{row.symbol || "-"}</TableCell>
                  <TableCell data-testid={`strategy-observability-detail-recent-rows-event-${index}`}>{row.event_type || "-"}</TableCell>
                  <TableCell data-testid={`strategy-observability-detail-recent-rows-score-${index}`}>{row.adjusted_score ?? 0}</TableCell>
                  <TableCell data-testid={`strategy-observability-detail-recent-rows-reason-${index}`}>{row.rejection_reason || "-"}</TableCell>
                </TableRow>
              ))}
              {!loading && (detailData?.recent_rows || []).length === 0 && (
                <TableRow data-testid="strategy-observability-detail-recent-rows-empty-row">
                  <TableCell colSpan={5} className="text-center text-sm text-black/70" data-testid="strategy-observability-detail-recent-rows-empty-text">
                    Recent row bulunamadı.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </section>

      <div className="border border-black/20 bg-white p-3 text-xs" data-testid="strategy-observability-detail-filter-echo-panel">
        <p data-testid="strategy-observability-detail-filter-echo-title" className="font-semibold">Active Filters Echo</p>
        <p data-testid="strategy-observability-detail-filter-echo-json">{JSON.stringify(activeFilters)}</p>
      </div>
    </section>
  );
}
