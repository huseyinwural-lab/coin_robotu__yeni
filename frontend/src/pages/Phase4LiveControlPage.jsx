import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { MetricCard } from "@/components/MetricCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

const initialConfig = {
  exchange: "binance",
  market_type: "futures_testnet",
  safe_mode_enabled: true,
  live_mode_enabled: false,
  symbol_whitelist: ["BTCUSDT"],
  max_position_pct: 0.1,
  leverage_cap: 1,
  max_trades_per_hour: 6,
  max_notional_exposure: 150,
  kill_switch_enabled: false,
  disable_futures: false,
  ip_whitelist_ready: false,
  trading_permission_ready: false,
};

export const Phase4LiveControlPage = () => {
  const [config, setConfig] = useState(initialConfig);
  const [readiness, setReadiness] = useState(null);
  const [connectivity, setConnectivity] = useState(null);
  const [readinessScore, setReadinessScore] = useState(null);
  const [releaseGate, setReleaseGate] = useState(null);
  const [qualityRows, setQualityRows] = useState([]);
  const [permissionStatus, setPermissionStatus] = useState(null);
  const [permissionResult, setPermissionResult] = useState(null);
  const [permissionForm, setPermissionForm] = useState({ api_key: "", api_secret: "" });

  const loadAll = useCallback(async () => {
    try {
      const [
        { data: configData },
        { data: readinessData },
        { data: connectivityData },
        { data: readinessScoreData },
        { data: releaseGateData },
        { data: qualityData },
        { data: permissionStatusData },
      ] = await Promise.all([
        apiClient.get("/phase4/live-config"),
        apiClient.get("/phase4/readiness-check"),
        apiClient.get("/phase4/testnet-connectivity"),
        apiClient.get("/phase4/admin/live-readiness-score"),
        apiClient.get("/phase4/admin/release-gate"),
        apiClient.get("/phase4/admin/execution-quality?limit=20"),
        apiClient.get("/phase4/admin/permission-status"),
      ]);
      setConfig(configData);
      setReadiness(readinessData);
      setConnectivity(connectivityData);
      setReadinessScore(readinessScoreData);
      setReleaseGate(releaseGateData);
      setQualityRows(qualityData);
      setPermissionStatus(permissionStatusData);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Phase-4 panel verisi alınamadı");
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const saveConfig = async (event) => {
    event.preventDefault();
    try {
      await apiClient.put("/phase4/live-config", {
        ...config,
        symbol_whitelist: ["BTCUSDT"],
        max_position_pct: Number(config.max_position_pct),
        leverage_cap: Number(config.leverage_cap),
        max_trades_per_hour: Number(config.max_trades_per_hour),
        max_notional_exposure: Number(config.max_notional_exposure),
      });
      toast.success("Live config güncellendi");
      loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Config güncellenemedi");
    }
  };

  const runPermissionCheck = async (event) => {
    event.preventDefault();
    try {
      const { data } = await apiClient.post("/phase4/permission-check", permissionForm);
      setPermissionResult(data);
      toast.success("Permission check çalıştı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Permission check başarısız");
    }
  };

  const runKillAction = async (action) => {
    try {
      await apiClient.post(`/phase4/kill-switch/${action}`);
      toast.success(`Kill switch aksiyonu çalıştı: ${action}`);
      loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Kill switch aksiyonu başarısız");
    }
  };

  return (
    <section className="space-y-4" data-testid="phase4-live-control-page">
      <header className="border border-blue-900 bg-slate-900 p-4" data-testid="phase4-live-control-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-blue-300" data-testid="phase4-live-control-title">Phase-4 Controlled Live Activation</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="phase4-live-control-description">
          Binance Futures Testnet hazırlık modu: key olmadan safety/permission/kill-switch doğrulaması.
        </p>
      </header>

      <div className="grid gap-3 md:grid-cols-4" data-testid="phase4-live-control-metrics-grid">
        <MetricCard label="Mode" value={readiness?.mode || "-"} tone="blue" testId="phase4-metric-mode" />
        <MetricCard label="Exchange" value={readiness?.exchange || "-"} tone="blue" testId="phase4-metric-exchange" />
        <MetricCard label="Market" value={readiness?.market_type || "-"} tone="blue" testId="phase4-metric-market" />
        <MetricCard label="Whitelist" value={config?.symbol_whitelist?.join(",") || "-"} tone="orange" testId="phase4-metric-whitelist" />
        <MetricCard label="Testnet" value={connectivity?.status || "-"} tone={connectivity?.status === "reachable" ? "blue" : "red"} testId="phase4-metric-testnet" />
        <MetricCard label="Live Readiness" value={readinessScore?.readiness_score ?? "-"} tone={Number(readinessScore?.readiness_score || 0) >= 80 ? "blue" : "red"} testId="phase4-metric-live-readiness-score" />
        <MetricCard label="Release Gate" value={releaseGate?.status || "-"} tone={releaseGate?.status === "PASS" ? "blue" : releaseGate?.status === "WARNING" ? "orange" : "red"} testId="phase4-metric-release-gate" />
        <MetricCard label="Live Activation" value={releaseGate?.live_activation || "disabled"} tone={releaseGate?.live_activation === "guarded" ? "orange" : "red"} testId="phase4-metric-live-activation" />
      </div>

      <div className="border border-red-500/30 bg-red-950/10 p-4" data-testid="phase4-release-gate-panel">
        <p className="text-xs uppercase tracking-widest text-red-300" data-testid="phase4-release-gate-title">Dry-Run Release Gate</p>
        <p className="mt-2 text-sm text-slate-300" data-testid="phase4-release-gate-status">Status: {releaseGate?.status || "-"}</p>
        <div className="mt-2 space-y-1" data-testid="phase4-release-gate-reasons-list">
          {(releaseGate?.reasons || []).map((item, index) => (
            <p key={`${item}-${index}`} className="text-xs font-mono text-red-200" data-testid={`phase4-release-gate-reason-${index}`}>{item}</p>
          ))}
        </div>
      </div>

      <div className="border border-blue-900 bg-slate-900 p-4" data-testid="phase4-live-readiness-factor-panel">
        <p className="text-xs uppercase tracking-widest text-blue-300" data-testid="phase4-live-readiness-factor-title">Live Readiness Factors</p>
        <div className="mt-3 grid gap-2 md:grid-cols-2" data-testid="phase4-live-readiness-factor-grid">
          <p data-testid="phase4-factor-permission">permission_ready: {String(readinessScore?.permission_ready || false)}</p>
          <p data-testid="phase4-factor-risk">risk_engine_pass: {String(readinessScore?.risk_engine_pass || false)}</p>
          <p data-testid="phase4-factor-execution">execution_simulation_pass: {String(readinessScore?.execution_simulation_pass || false)}</p>
          <p data-testid="phase4-factor-correlation">correlation_model_pass: {String(readinessScore?.correlation_model_pass || false)}</p>
          <p data-testid="phase4-factor-hardening">hardening_checklist_pass: {String(readinessScore?.hardening_checklist_pass || false)}</p>
        </div>
      </div>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="phase4-permission-status-panel">
        <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="phase4-permission-status-title">Permission Status</p>
        <p className="mt-2 text-sm text-slate-300" data-testid="phase4-permission-status-overall">overall={permissionStatus?.overall_status || "-"} | live_activation={permissionStatus?.live_activation || "-"}</p>
        <div className="mt-2 space-y-1" data-testid="phase4-permission-status-controls-list">
          {(permissionStatus?.controls || []).map((item) => (
            <p key={item.key} className="font-mono text-xs text-slate-300" data-testid={`phase4-permission-status-control-${item.key}`}>
              {item.key}: {item.status} ({item.reason})
            </p>
          ))}
        </div>
      </div>

      <div className="border border-blue-900 bg-slate-900 p-4" data-testid="phase4-testnet-connectivity-panel">
        <div className="flex flex-wrap items-center justify-between gap-3" data-testid="phase4-testnet-connectivity-header">
          <p className="text-xs uppercase tracking-widest text-blue-300" data-testid="phase4-testnet-connectivity-title">Binance Futures Testnet Connectivity</p>
          <Button className="bg-blue-600 text-white hover:bg-blue-700" onClick={loadAll} data-testid="phase4-testnet-refresh-button">Yenile</Button>
        </div>
        <p className="mt-3 text-sm text-slate-300" data-testid="phase4-testnet-connectivity-message">{connectivity?.message || "-"}</p>
        <p className="mt-1 font-mono text-xs text-slate-400" data-testid="phase4-testnet-connectivity-rest">REST: {connectivity?.rest_url || "-"}</p>
        <p className="mt-1 font-mono text-xs text-slate-400" data-testid="phase4-testnet-connectivity-ws">WS: {connectivity?.ws_url || "-"}</p>
      </div>

      <form onSubmit={saveConfig} className="grid gap-3 border border-slate-800 bg-slate-900 p-4 md:grid-cols-2" data-testid="phase4-config-form">
        <Input value={config.exchange} onChange={(event) => setConfig((prev) => ({ ...prev, exchange: event.target.value }))} data-testid="phase4-config-exchange-input" />
        <Input value={config.market_type} onChange={(event) => setConfig((prev) => ({ ...prev, market_type: event.target.value }))} data-testid="phase4-config-market-type-input" />
        <Input type="number" step="0.01" value={config.max_position_pct} onChange={(event) => setConfig((prev) => ({ ...prev, max_position_pct: event.target.value }))} data-testid="phase4-config-max-position-input" />
        <Input type="number" value={config.leverage_cap} onChange={(event) => setConfig((prev) => ({ ...prev, leverage_cap: event.target.value }))} data-testid="phase4-config-leverage-input" />
        <Input type="number" value={config.max_trades_per_hour} onChange={(event) => setConfig((prev) => ({ ...prev, max_trades_per_hour: event.target.value }))} data-testid="phase4-config-max-trades-input" />
        <Input type="number" value={config.max_notional_exposure} onChange={(event) => setConfig((prev) => ({ ...prev, max_notional_exposure: event.target.value }))} data-testid="phase4-config-max-notional-input" />

        <div className="md:col-span-2 flex flex-wrap gap-3" data-testid="phase4-config-toggle-row">
          <label className="flex items-center gap-2 text-sm" data-testid="phase4-config-safe-mode-label">
            <input type="checkbox" checked={config.safe_mode_enabled} onChange={(event) => setConfig((prev) => ({ ...prev, safe_mode_enabled: event.target.checked }))} data-testid="phase4-config-safe-mode-toggle" />
            Safe Mode
          </label>
          <label className="flex items-center gap-2 text-sm" data-testid="phase4-config-live-mode-label">
            <input type="checkbox" checked={config.live_mode_enabled} onChange={(event) => setConfig((prev) => ({ ...prev, live_mode_enabled: event.target.checked }))} data-testid="phase4-config-live-mode-toggle" />
            Live Mode
          </label>
          <label className="flex items-center gap-2 text-sm" data-testid="phase4-config-ip-ready-label">
            <input type="checkbox" checked={config.ip_whitelist_ready} onChange={(event) => setConfig((prev) => ({ ...prev, ip_whitelist_ready: event.target.checked }))} data-testid="phase4-config-ip-ready-toggle" />
            IP Whitelist Ready
          </label>
          <label className="flex items-center gap-2 text-sm" data-testid="phase4-config-permission-ready-label">
            <input type="checkbox" checked={config.trading_permission_ready} onChange={(event) => setConfig((prev) => ({ ...prev, trading_permission_ready: event.target.checked }))} data-testid="phase4-config-permission-ready-toggle" />
            Trading Permission Ready
          </label>
        </div>

        <Button className="bg-blue-600 text-white hover:bg-blue-700 md:col-span-2" data-testid="phase4-config-save-button">Config Kaydet</Button>
      </form>

      <form onSubmit={runPermissionCheck} className="grid gap-3 border border-slate-800 bg-slate-900 p-4 md:grid-cols-3" data-testid="phase4-permission-form">
        <Input placeholder="API key (opsiyonel)" value={permissionForm.api_key} onChange={(event) => setPermissionForm((prev) => ({ ...prev, api_key: event.target.value }))} data-testid="phase4-permission-key-input" />
        <Input placeholder="API secret (opsiyonel)" value={permissionForm.api_secret} onChange={(event) => setPermissionForm((prev) => ({ ...prev, api_secret: event.target.value }))} data-testid="phase4-permission-secret-input" />
        <Button className="bg-orange-500 text-black hover:bg-orange-600" data-testid="phase4-permission-check-button">Permission Check</Button>
        {permissionResult && (
          <p className="md:col-span-3 text-xs font-mono" data-testid="phase4-permission-result">
            status={permissionResult.status} | masked={permissionResult.masked_key} | key={String(permissionResult.api_key_present)} | secret={String(permissionResult.api_secret_present)}
          </p>
        )}
      </form>

      <div className="border border-red-500/40 bg-red-950/10 p-4" data-testid="phase4-kill-switch-panel">
        <p className="text-xs uppercase tracking-widest text-red-300" data-testid="phase4-kill-switch-title">Emergency Kill Switch</p>
        <div className="mt-3 flex flex-wrap gap-2" data-testid="phase4-kill-switch-buttons">
          <Button className="bg-red-700 text-white hover:bg-red-800" onClick={() => runKillAction("stop-all-bots")} data-testid="phase4-kill-stop-bots-button">STOP ALL BOTS</Button>
          <Button className="bg-red-700 text-white hover:bg-red-800" onClick={() => runKillAction("close-all-positions")} data-testid="phase4-kill-close-positions-button">CLOSE ALL POSITIONS</Button>
          <Button className="bg-red-700 text-white hover:bg-red-800" onClick={() => runKillAction("disable-futures")} data-testid="phase4-kill-disable-futures-button">DISABLE FUTURES</Button>
        </div>
      </div>

      <div className="border border-slate-800 bg-slate-900" data-testid="phase4-readiness-table-wrapper">
        <Table data-testid="phase4-readiness-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="phase4-readiness-head-key">Check</TableHead>
              <TableHead data-testid="phase4-readiness-head-critical">Critical</TableHead>
              <TableHead data-testid="phase4-readiness-head-status">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(readiness?.checks || []).map((item) => (
              <TableRow key={item.key} data-testid={`phase4-readiness-row-${item.key}`}>
                <TableCell data-testid={`phase4-readiness-label-${item.key}`}>{item.label}</TableCell>
                <TableCell data-testid={`phase4-readiness-critical-${item.key}`}>{String(item.critical)}</TableCell>
                <TableCell data-testid={`phase4-readiness-status-${item.key}`}>{item.status}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="border border-slate-800 bg-slate-900" data-testid="phase4-execution-quality-table-wrapper">
        <Table data-testid="phase4-execution-quality-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="phase4-exec-quality-head-time">Timestamp</TableHead>
              <TableHead data-testid="phase4-exec-quality-head-symbol">Symbol</TableHead>
              <TableHead data-testid="phase4-exec-quality-head-expected">Expected</TableHead>
              <TableHead data-testid="phase4-exec-quality-head-fill">Fill</TableHead>
              <TableHead data-testid="phase4-exec-quality-head-slippage">Slippage</TableHead>
              <TableHead data-testid="phase4-exec-quality-head-latency">Latency</TableHead>
              <TableHead data-testid="phase4-exec-quality-head-score">Quality Score</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {qualityRows.map((item) => (
              <TableRow key={item.execution_id} data-testid={`phase4-exec-quality-row-${item.execution_id}`}>
                <TableCell className="font-mono text-xs" data-testid={`phase4-exec-quality-time-${item.execution_id}`}>{new Date(item.timestamp).toLocaleString()}</TableCell>
                <TableCell data-testid={`phase4-exec-quality-symbol-${item.execution_id}`}>{item.symbol}</TableCell>
                <TableCell data-testid={`phase4-exec-quality-expected-${item.execution_id}`}>{item.expected_price}</TableCell>
                <TableCell data-testid={`phase4-exec-quality-fill-${item.execution_id}`}>{item.fill_price ?? "-"}</TableCell>
                <TableCell data-testid={`phase4-exec-quality-slippage-${item.execution_id}`}>{item.slippage ?? "-"}</TableCell>
                <TableCell data-testid={`phase4-exec-quality-latency-${item.execution_id}`}>{item.execution_latency ?? "-"}</TableCell>
                <TableCell data-testid={`phase4-exec-quality-score-${item.execution_id}`}>{item.execution_quality_score}</TableCell>
              </TableRow>
            ))}
            {qualityRows.length === 0 && (
              <TableRow data-testid="phase4-exec-quality-empty-row">
                <TableCell colSpan={7} className="text-center text-sm text-slate-400" data-testid="phase4-exec-quality-empty-text">
                  Henüz test order execution kaydı yok.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </section>
  );
};
