import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

const ANOMALY_ACTION = "SCANNER_ANOMALY_DETECTED";
const HOURS_7D = 168;
const HOURS_30D = 720;
const DAY_MS = 24 * 60 * 60 * 1000;

const toIsoFromHours = (hours) => {
  const parsed = Number(hours || 168);
  const now = Date.now();
  return new Date(now - (parsed * 60 * 60 * 1000)).toISOString();
};

const average = (values) => {
  if (!Array.isArray(values) || values.length === 0) {
    return null;
  }
  return values.reduce((acc, value) => acc + Number(value || 0), 0) / values.length;
};

const safePercent = (value) => {
  if (!Number.isFinite(Number(value))) {
    return 0;
  }
  return Math.max(0, Math.min(100, Number(value) * 100));
};

const toCsvSafe = (value) => {
  const raw = String(value ?? "");
  return `"${raw.replaceAll('"', '""')}"`;
};

const errorMessageOf = (error, fallback = "İşlem başarısız") => {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail)) {
    const joined = detail
      .map((entry) => {
        if (typeof entry === "string") return entry;
        if (entry && typeof entry === "object") return entry.msg || JSON.stringify(entry);
        return "";
      })
      .filter(Boolean)
      .join("; ");
    if (joined) {
      return joined;
    }
  }
  if (detail && typeof detail === "object") {
    try {
      return JSON.stringify(detail);
    } catch {
      return fallback;
    }
  }
  return fallback;
};

const sourceOf = (item) => String(item?.details?.source || "unknown_source");

const failRatioOf = (item) => Number(item?.details?.fail_ratio || 0);

const formatTimestamp = (value) => {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString("tr-TR");
};

const ttrToneClass = (minutes) => {
  if (minutes == null || Number.isNaN(Number(minutes))) {
    return "text-slate-400";
  }
  const value = Number(minutes);
  if (value <= 15) {
    return "text-emerald-300";
  }
  if (value <= 60) {
    return "text-amber-300";
  }
  return "text-rose-300";
};

const computeTimeToRecoverDetails = (rows, warningThreshold) => {
  const sorted = [...rows].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
  const unresolvedByKey = new Map();
  const result = {};

  sorted.forEach((row) => {
    const key = `${String(row?.actor_user_id || "unknown_user")}::${sourceOf(row)}`;
    const rowTs = new Date(row.created_at).getTime();
    const rowFailRatio = failRatioOf(row);
    const unresolved = unresolvedByKey.get(key) || [];

    const keep = [];
    unresolved.forEach((candidate) => {
      const dropRatio = candidate.failRatio > 0 ? Math.max(0, (candidate.failRatio - rowFailRatio) / candidate.failRatio) : 1;
      const isRecovered = rowFailRatio <= Math.min(Number(warningThreshold || 0.1), candidate.failRatio * 0.7);
      if (!isRecovered) {
        keep.push(candidate);
        return;
      }
      const minutes = Math.max(0, Math.round((rowTs - candidate.timestamp) / 60000));
      const confidence = Math.max(0, Math.min(1, ((rowFailRatio <= Number(warningThreshold || 0.1) ? 0.6 : 0.3) + (dropRatio * 0.4))));
      result[candidate.id] = {
        minutes,
        recoveredAt: row.created_at,
        recoveredEventId: row.id,
        failRatioBefore: Number(candidate.failRatio.toFixed(4)),
        failRatioAfter: Number(rowFailRatio.toFixed(4)),
        deltaFailRatio: Number((candidate.failRatio - rowFailRatio).toFixed(4)),
        confidenceScore: Number(confidence.toFixed(2)),
      };
    });

    keep.push({ id: row.id, timestamp: rowTs, failRatio: rowFailRatio });
    unresolvedByKey.set(key, keep);
  });

  return result;
};

const applyMainFilters = ({ items, severityFilter, sourceFilter, userFilter }) => {
  return items.filter((item) => {
    const severityOk = severityFilter === "all" ? true : String(item.severity || "").toLowerCase() === severityFilter;
    const sourceOk = sourceFilter === "all" ? true : sourceOf(item) === sourceFilter;
    const userOk = userFilter === "all" ? true : String(item.actor_user_id || "unknown_user") === userFilter;
    return severityOk && sourceOk && userOk;
  });
};

const withinHours = (items, hours) => {
  const cutoff = Date.now() - (Number(hours || HOURS_7D) * 60 * 60 * 1000);
  return items.filter((item) => {
    const ts = new Date(item.created_at).getTime();
    return Number.isFinite(ts) && ts >= cutoff;
  });
};

const computeKpis = (items, warningThreshold) => {
  const ttrMap = computeTimeToRecoverDetails(items, warningThreshold);
  const mttrValues = items
    .map((item) => ttrMap[item.id]?.minutes)
    .filter((value) => Number.isFinite(Number(value)));
  const mttdValues = items
    .map((item) => Number(item?.details?.trend_window_minutes || 0))
    .filter((value) => Number.isFinite(value) && value > 0);

  const warningCount = items.filter((item) => String(item.severity || "").toLowerCase() === "warning").length;
  const criticalCount = items.filter((item) => String(item.severity || "").toLowerCase() === "critical").length;
  const anomalyCount = items.length;

  return {
    anomalyCount,
    warningCount,
    criticalCount,
    mttrMinutes: average(mttrValues),
    mttdMinutes: average(mttdValues),
    mttrSampleCount: mttrValues.length,
    mttdSampleCount: mttdValues.length,
    ttrMap,
  };
};

const computeWeeklyTrend = (items) => {
  const today = new Date();
  const buckets = Array.from({ length: 7 }, (_, index) => {
    const dayStart = new Date(today.getFullYear(), today.getMonth(), today.getDate() - (6 - index));
    const dayEnd = new Date(dayStart.getTime() + DAY_MS);
    return {
      key: dayStart.toISOString().slice(0, 10),
      label: dayStart.toLocaleDateString("tr-TR", { day: "2-digit", month: "2-digit" }),
      dayStart: dayStart.getTime(),
      dayEnd: dayEnd.getTime(),
      total: 0,
      warning: 0,
      critical: 0,
    };
  });

  items.forEach((item) => {
    const ts = new Date(item.created_at).getTime();
    if (!Number.isFinite(ts)) {
      return;
    }
    const bucket = buckets.find((entry) => ts >= entry.dayStart && ts < entry.dayEnd);
    if (!bucket) {
      return;
    }
    bucket.total += 1;
    const severity = String(item.severity || "").toLowerCase();
    if (severity === "warning") {
      bucket.warning += 1;
    }
    if (severity === "critical") {
      bucket.critical += 1;
    }
  });

  return buckets;
};

const computeSourceBreakdown = (items) => {
  const map = items.reduce((acc, item) => {
    const source = sourceOf(item);
    const current = acc.get(source) || { source, total: 0, warning: 0, critical: 0 };
    current.total += 1;
    const severity = String(item.severity || "").toLowerCase();
    if (severity === "warning") {
      current.warning += 1;
    }
    if (severity === "critical") {
      current.critical += 1;
    }
    acc.set(source, current);
    return acc;
  }, new Map());

  return Array.from(map.values()).sort((a, b) => b.total - a.total);
};

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
      toast.error(errorMessageOf(error, "Alert policy yüklenemedi"));
    }
  }, []);

  const loadMutes = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/admin/anomaly-alerts/mutes", { params: { limit: 20 } });
      setActiveMutes(data || []);
    } catch (error) {
      toast.error(errorMessageOf(error, "Active mute listesi yüklenemedi"));
    }
  }, []);

  const loadTimeline = useCallback(async () => {
    setIsLoading(true);
    try {
      const { data } = await apiClient.get("/audit-logs/timeline", {
        params: {
          action: ANOMALY_ACTION,
          limit: 500,
          date_from: toIsoFromHours(HOURS_30D),
        },
      });
      const nextItems = data?.items || [];
      setItems(nextItems);
      setSelectedLogId((prev) => prev || nextItems[0]?.id || null);
    } catch (error) {
      toast.error(errorMessageOf(error, "Anomaly timeline yüklenemedi"));
    } finally {
      setIsLoading(false);
    }
  }, []);

  const loadAll = useCallback(async () => {
    await Promise.all([loadTimeline(), loadPolicy(), loadMutes()]);
  }, [loadTimeline, loadPolicy, loadMutes]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const sourceOptions = useMemo(() => {
    const counts = withinHours(items, windowHours).reduce((acc, item) => {
      const source = sourceOf(item);
      acc[source] = (acc[source] || 0) + 1;
      return acc;
    }, {});
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .map(([value, count]) => ({ value, count }));
  }, [items, windowHours]);

  const userOptions = useMemo(() => {
    const counts = withinHours(items, windowHours).reduce((acc, item) => {
      const actorUserId = String(item?.actor_user_id || "unknown_user");
      acc[actorUserId] = (acc[actorUserId] || 0) + 1;
      return acc;
    }, {});
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .map(([value, count]) => ({ value, count }));
  }, [items, windowHours]);

  const windowItems = useMemo(() => withinHours(items, windowHours), [items, windowHours]);

  const filteredWindowItems = useMemo(
    () => applyMainFilters({
      items: windowItems,
      severityFilter,
      sourceFilter,
      userFilter,
    }),
    [windowItems, severityFilter, sourceFilter, userFilter],
  );

  const filteredItems = useMemo(() => {
    const normalizedSearch = searchText.trim().toLowerCase();
    if (!normalizedSearch) {
      return filteredWindowItems;
    }
    return filteredWindowItems.filter((item) => JSON.stringify(item).toLowerCase().includes(normalizedSearch));
  }, [filteredWindowItems, searchText]);

  const filtered30dItems = useMemo(
    () => applyMainFilters({
      items: withinHours(items, HOURS_30D),
      severityFilter,
      sourceFilter,
      userFilter,
    }),
    [items, severityFilter, sourceFilter, userFilter],
  );

  const filtered7dItems = useMemo(
    () => applyMainFilters({
      items: withinHours(items, HOURS_7D),
      severityFilter,
      sourceFilter,
      userFilter,
    }),
    [items, severityFilter, sourceFilter, userFilter],
  );

  const dashboardKpisCurrent = useMemo(
    () => computeKpis(filteredWindowItems, Number(policy.warning_threshold || 0.1)),
    [filteredWindowItems, policy.warning_threshold],
  );

  const dashboardKpis7d = useMemo(
    () => computeKpis(filtered7dItems, Number(policy.warning_threshold || 0.1)),
    [filtered7dItems, policy.warning_threshold],
  );

  const dashboardKpis30d = useMemo(
    () => computeKpis(filtered30dItems, Number(policy.warning_threshold || 0.1)),
    [filtered30dItems, policy.warning_threshold],
  );

  const weeklyTrend = useMemo(() => computeWeeklyTrend(filtered7dItems), [filtered7dItems]);

  const sourceBreakdown = useMemo(() => computeSourceBreakdown(filteredWindowItems), [filteredWindowItems]);

  const warningCriticalDistribution = useMemo(() => {
    const warning = filteredWindowItems.filter((item) => String(item.severity || "").toLowerCase() === "warning").length;
    const critical = filteredWindowItems.filter((item) => String(item.severity || "").toLowerCase() === "critical").length;
    const total = warning + critical;
    return {
      warning,
      critical,
      warningRatio: total > 0 ? warning / total : 0,
      criticalRatio: total > 0 ? critical / total : 0,
    };
  }, [filteredWindowItems]);

  const ttrDetailByLogId = useMemo(
    () => computeTimeToRecoverDetails(filteredWindowItems, Number(policy.warning_threshold || 0.1)),
    [filteredWindowItems, policy.warning_threshold],
  );

  const selectedItem = useMemo(
    () => filteredItems.find((item) => item.id === selectedLogId) || filteredItems[0] || null,
    [filteredItems, selectedLogId],
  );

  const dashboardSnapshot = useMemo(() => {
    const mttrCurrent = dashboardKpisCurrent.mttrMinutes;
    const mttdCurrent = dashboardKpisCurrent.mttdMinutes;
    const mttr7d = dashboardKpis7d.mttrMinutes;
    const mttr30d = dashboardKpis30d.mttrMinutes;
    const mttd7d = dashboardKpis7d.mttdMinutes;
    const mttd30d = dashboardKpis30d.mttdMinutes;
    return {
      generated_at: new Date().toISOString(),
      window_hours: Number(windowHours),
      filters: {
        severity: severityFilter,
        source: sourceFilter,
        user: userFilter,
      },
      kpis: {
        current: {
          anomaly_count: dashboardKpisCurrent.anomalyCount,
          warning_count: dashboardKpisCurrent.warningCount,
          critical_count: dashboardKpisCurrent.criticalCount,
          mttr_minutes: mttrCurrent,
          mttd_minutes: mttdCurrent,
        },
        compare_7d: {
          anomaly_count: dashboardKpis7d.anomalyCount,
          mttr_minutes: mttr7d,
          mttd_minutes: mttd7d,
        },
        compare_30d: {
          anomaly_count: dashboardKpis30d.anomalyCount,
          mttr_minutes: mttr30d,
          mttd_minutes: mttd30d,
        },
        delta_7d_vs_30d: {
          anomaly_count_delta: Number(dashboardKpis7d.anomalyCount || 0) - Number(dashboardKpis30d.anomalyCount || 0),
          mttr_minutes_delta: mttr7d != null && mttr30d != null ? Number((mttr7d - mttr30d).toFixed(2)) : null,
          mttd_minutes_delta: mttd7d != null && mttd30d != null ? Number((mttd7d - mttd30d).toFixed(2)) : null,
        },
      },
      warning_critical_distribution: warningCriticalDistribution,
      weekly_trend: weeklyTrend,
      source_breakdown: sourceBreakdown,
    };
  }, [
    dashboardKpisCurrent,
    dashboardKpis7d,
    dashboardKpis30d,
    sourceBreakdown,
    severityFilter,
    sourceFilter,
    userFilter,
    warningCriticalDistribution,
    weeklyTrend,
    windowHours,
  ]);

  const exportTimelineJson = () => {
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

  const exportTimelineCsv = () => {
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
        ttrDetailByLogId[item.id]?.minutes ?? "",
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

  const exportKpiJson = () => {
    const blob = new Blob([JSON.stringify(dashboardSnapshot, null, 2)], { type: "application/json" });
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `anomaly_kpi_snapshot_${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.URL.revokeObjectURL(url);
    toast.success("KPI snapshot JSON indirildi");
  };

  const exportKpiCsv = () => {
    const rows = [
      ["metric", "value"],
      ["window_hours", windowHours],
      ["anomaly_count_current", dashboardSnapshot.kpis.current.anomaly_count],
      ["warning_count_current", dashboardSnapshot.kpis.current.warning_count],
      ["critical_count_current", dashboardSnapshot.kpis.current.critical_count],
      ["mttr_minutes_current", dashboardSnapshot.kpis.current.mttr_minutes ?? ""],
      ["mttd_minutes_current", dashboardSnapshot.kpis.current.mttd_minutes ?? ""],
      ["anomaly_count_7d", dashboardSnapshot.kpis.compare_7d.anomaly_count],
      ["anomaly_count_30d", dashboardSnapshot.kpis.compare_30d.anomaly_count],
      ["mttr_delta_7d_vs_30d", dashboardSnapshot.kpis.delta_7d_vs_30d.mttr_minutes_delta ?? ""],
      ["mttd_delta_7d_vs_30d", dashboardSnapshot.kpis.delta_7d_vs_30d.mttd_minutes_delta ?? ""],
    ];
    const csv = rows.map((row) => row.map(toCsvSafe).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `anomaly_kpi_snapshot_${new Date().toISOString().replace(/[:.]/g, "-")}.csv`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.URL.revokeObjectURL(url);
    toast.success("KPI snapshot CSV indirildi");
  };

  const exportWeeklySummaryReport = () => {
    const lines = [
      "# Weekly Anomaly Summary",
      `Generated At: ${new Date().toISOString()}`,
      `Window Hours: ${windowHours}`,
      `Filters: severity=${severityFilter}, source=${sourceFilter}, user=${userFilter}`,
      "",
      "## KPI",
      `- Anomaly Count: ${dashboardSnapshot.kpis.current.anomaly_count}`,
      `- Warning/Critical: ${dashboardSnapshot.kpis.current.warning_count}/${dashboardSnapshot.kpis.current.critical_count}`,
      `- MTTR (minutes): ${dashboardSnapshot.kpis.current.mttr_minutes ?? "n/a"}`,
      `- MTTD (minutes): ${dashboardSnapshot.kpis.current.mttd_minutes ?? "n/a"}`,
      "",
      "## 7d vs 30d",
      `- Anomaly delta: ${dashboardSnapshot.kpis.delta_7d_vs_30d.anomaly_count_delta}`,
      `- MTTR delta: ${dashboardSnapshot.kpis.delta_7d_vs_30d.mttr_minutes_delta ?? "n/a"}`,
      `- MTTD delta: ${dashboardSnapshot.kpis.delta_7d_vs_30d.mttd_minutes_delta ?? "n/a"}`,
      "",
      "## Source Breakdown",
      ...dashboardSnapshot.source_breakdown.slice(0, 5).map((row) => `- ${row.source}: total=${row.total}, warning=${row.warning}, critical=${row.critical}`),
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8;" });
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `anomaly_weekly_summary_${new Date().toISOString().replace(/[:.]/g, "-")}.md`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.URL.revokeObjectURL(url);
    toast.success("Haftalık özet rapor indirildi");
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
      toast.error(errorMessageOf(error, "Policy güncellenemedi"));
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
      toast.error(errorMessageOf(error, "Pattern mute başarısız"));
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

      <section className="space-y-3 border border-slate-800 bg-slate-900 p-3" data-testid="admin-anomaly-dashboard-panel">
        <header className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-anomaly-dashboard-header">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-anomaly-dashboard-title">Operatör Dashboard</p>
          <div className="flex flex-wrap gap-2" data-testid="admin-anomaly-dashboard-export-actions">
            <Button variant="outline" onClick={exportKpiJson} data-testid="admin-anomaly-dashboard-export-kpi-json-button">KPI JSON</Button>
            <Button variant="outline" onClick={exportKpiCsv} data-testid="admin-anomaly-dashboard-export-kpi-csv-button">KPI CSV</Button>
            <Button variant="outline" onClick={exportWeeklySummaryReport} data-testid="admin-anomaly-dashboard-export-weekly-summary-button">Haftalık Özet</Button>
          </div>
        </header>
        <div className="grid gap-2 md:grid-cols-4" data-testid="admin-anomaly-dashboard-kpi-grid">
          <div className="rounded border border-slate-700 bg-slate-950 p-2" data-testid="admin-anomaly-dashboard-kpi-anomaly-count-card">
            <p className="text-xs text-slate-500">Anomaly Count</p>
            <p className="text-lg font-bold text-orange-300" data-testid="admin-anomaly-dashboard-kpi-anomaly-count-value">{dashboardKpisCurrent.anomalyCount}</p>
          </div>
          <div className="rounded border border-slate-700 bg-slate-950 p-2" data-testid="admin-anomaly-dashboard-kpi-mttr-card">
            <p className="text-xs text-slate-500">MTTR (dk)</p>
            <p className="text-lg font-bold text-emerald-300" data-testid="admin-anomaly-dashboard-kpi-mttr-value">{dashboardKpisCurrent.mttrMinutes != null ? dashboardKpisCurrent.mttrMinutes.toFixed(1) : "n/a"}</p>
          </div>
          <div className="rounded border border-slate-700 bg-slate-950 p-2" data-testid="admin-anomaly-dashboard-kpi-mttd-card">
            <p className="text-xs text-slate-500">MTTD (dk)</p>
            <p className="text-lg font-bold text-cyan-300" data-testid="admin-anomaly-dashboard-kpi-mttd-value">{dashboardKpisCurrent.mttdMinutes != null ? dashboardKpisCurrent.mttdMinutes.toFixed(1) : "n/a"}</p>
          </div>
          <div className="rounded border border-slate-700 bg-slate-950 p-2" data-testid="admin-anomaly-dashboard-kpi-warning-critical-card">
            <p className="text-xs text-slate-500">Warning / Critical</p>
            <p className="text-lg font-bold text-amber-300" data-testid="admin-anomaly-dashboard-kpi-warning-critical-value">{dashboardKpisCurrent.warningCount} / {dashboardKpisCurrent.criticalCount}</p>
          </div>
        </div>
        <div className="grid gap-2 md:grid-cols-3" data-testid="admin-anomaly-dashboard-compare-grid">
          <div className="rounded border border-slate-700 bg-slate-950 p-2" data-testid="admin-anomaly-dashboard-compare-7d-card">
            <p className="text-xs text-slate-500">7g KPI</p>
            <p className="text-xs text-slate-300" data-testid="admin-anomaly-dashboard-compare-7d-values">count={dashboardKpis7d.anomalyCount}, MTTR={dashboardKpis7d.mttrMinutes != null ? dashboardKpis7d.mttrMinutes.toFixed(1) : "n/a"}, MTTD={dashboardKpis7d.mttdMinutes != null ? dashboardKpis7d.mttdMinutes.toFixed(1) : "n/a"}</p>
          </div>
          <div className="rounded border border-slate-700 bg-slate-950 p-2" data-testid="admin-anomaly-dashboard-compare-30d-card">
            <p className="text-xs text-slate-500">30g KPI</p>
            <p className="text-xs text-slate-300" data-testid="admin-anomaly-dashboard-compare-30d-values">count={dashboardKpis30d.anomalyCount}, MTTR={dashboardKpis30d.mttrMinutes != null ? dashboardKpis30d.mttrMinutes.toFixed(1) : "n/a"}, MTTD={dashboardKpis30d.mttdMinutes != null ? dashboardKpis30d.mttdMinutes.toFixed(1) : "n/a"}</p>
          </div>
          <div className="rounded border border-slate-700 bg-slate-950 p-2" data-testid="admin-anomaly-dashboard-compare-delta-card">
            <p className="text-xs text-slate-500">7g vs 30g Delta</p>
            <p className="text-xs text-slate-300" data-testid="admin-anomaly-dashboard-compare-delta-values">count={dashboardSnapshot.kpis.delta_7d_vs_30d.anomaly_count_delta}, MTTR={dashboardSnapshot.kpis.delta_7d_vs_30d.mttr_minutes_delta ?? "n/a"}, MTTD={dashboardSnapshot.kpis.delta_7d_vs_30d.mttd_minutes_delta ?? "n/a"}</p>
          </div>
        </div>
        <div className="grid gap-2 md:grid-cols-3" data-testid="admin-anomaly-dashboard-analytics-grid">
          <div className="rounded border border-slate-700 bg-slate-950 p-2" data-testid="admin-anomaly-dashboard-weekly-trend-card">
            <p className="text-xs uppercase text-slate-500" data-testid="admin-anomaly-dashboard-weekly-trend-title">Haftalık Trend</p>
            <div className="mt-2 space-y-1" data-testid="admin-anomaly-dashboard-weekly-trend-list">
              {weeklyTrend.map((row, index) => {
                const maxTotal = Math.max(1, ...weeklyTrend.map((item) => item.total));
                const ratio = row.total / maxTotal;
                return (
                  <div key={row.key} className="space-y-1" data-testid={`admin-anomaly-dashboard-weekly-trend-item-${index}`}>
                    <p className="text-[11px] text-slate-300">{row.label} → total={row.total}, w/c={row.warning}/{row.critical}</p>
                    <div className="h-1.5 w-full overflow-hidden rounded bg-slate-800" data-testid={`admin-anomaly-dashboard-weekly-trend-sparkbar-${index}`}>
                      <div className="h-full bg-orange-400" style={{ width: `${(ratio * 100).toFixed(1)}%` }} data-testid={`admin-anomaly-dashboard-weekly-trend-sparkbar-fill-${index}`} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          <div className="rounded border border-slate-700 bg-slate-950 p-2" data-testid="admin-anomaly-dashboard-warning-critical-distribution-card">
            <p className="text-xs uppercase text-slate-500" data-testid="admin-anomaly-dashboard-warning-critical-distribution-title">Warning/Critical Dağılımı</p>
            <p className="mt-2 text-xs text-slate-300" data-testid="admin-anomaly-dashboard-warning-critical-distribution-values">warning={warningCriticalDistribution.warning} ({safePercent(warningCriticalDistribution.warningRatio).toFixed(1)}%) | critical={warningCriticalDistribution.critical} ({safePercent(warningCriticalDistribution.criticalRatio).toFixed(1)}%)</p>
            <div className="mt-2 space-y-1" data-testid="admin-anomaly-dashboard-warning-critical-distribution-bars">
              <div className="h-1.5 w-full overflow-hidden rounded bg-slate-800" data-testid="admin-anomaly-dashboard-warning-critical-warning-bar">
                <div className="h-full bg-amber-400" style={{ width: `${safePercent(warningCriticalDistribution.warningRatio).toFixed(1)}%` }} data-testid="admin-anomaly-dashboard-warning-critical-warning-bar-fill" />
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded bg-slate-800" data-testid="admin-anomaly-dashboard-warning-critical-critical-bar">
                <div className="h-full bg-rose-400" style={{ width: `${safePercent(warningCriticalDistribution.criticalRatio).toFixed(1)}%` }} data-testid="admin-anomaly-dashboard-warning-critical-critical-bar-fill" />
              </div>
            </div>
          </div>
          <div className="rounded border border-slate-700 bg-slate-950 p-2" data-testid="admin-anomaly-dashboard-source-breakdown-card">
            <p className="text-xs uppercase text-slate-500" data-testid="admin-anomaly-dashboard-source-breakdown-title">Source Bazlı Kırılım</p>
            <div className="mt-2 space-y-1" data-testid="admin-anomaly-dashboard-source-breakdown-list">
              {sourceBreakdown.slice(0, 5).map((row, index) => {
                const maxTotal = Math.max(1, ...sourceBreakdown.map((item) => item.total));
                const ratio = row.total / maxTotal;
                return (
                  <div key={`${row.source}-${index}`} className="space-y-1" data-testid={`admin-anomaly-dashboard-source-breakdown-item-${index}`}>
                    <p className="text-[11px] text-slate-300">{row.source} → total={row.total}, w/c={row.warning}/{row.critical}</p>
                    <div className="h-1.5 w-full overflow-hidden rounded bg-slate-800" data-testid={`admin-anomaly-dashboard-source-breakdown-sparkbar-${index}`}>
                      <div className="h-full bg-cyan-400" style={{ width: `${(ratio * 100).toFixed(1)}%` }} data-testid={`admin-anomaly-dashboard-source-breakdown-sparkbar-fill-${index}`} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
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
        <Button variant="outline" onClick={exportTimelineJson} data-testid="admin-anomaly-timeline-export-json-button">Export JSON</Button>
        <Button variant="outline" onClick={exportTimelineCsv} data-testid="admin-anomaly-timeline-export-csv-button">Export CSV</Button>
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
                  <TableCell
                    className={ttrToneClass(ttrDetailByLogId[item.id]?.minutes)}
                    title={
                      ttrDetailByLogId[item.id]
                        ? `recovered_at=${formatTimestamp(ttrDetailByLogId[item.id].recoveredAt)} | fail_ratio=${ttrDetailByLogId[item.id].failRatioBefore}→${ttrDetailByLogId[item.id].failRatioAfter} | delta=${ttrDetailByLogId[item.id].deltaFailRatio} | confidence=${(Number(ttrDetailByLogId[item.id].confidenceScore || 0) * 100).toFixed(0)}%`
                        : "Henüz recovery eşleşmesi yok"
                    }
                    data-testid={`admin-anomaly-timeline-ttr-${item.id}`}
                  >
                    {ttrDetailByLogId[item.id]?.minutes != null ? `${ttrDetailByLogId[item.id].minutes}m` : "-"}
                  </TableCell>
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
