import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

const EXCHANGE_TABS = [
  { value: "binance", label: "BINANCE" },
  { value: "bybit", label: "BYBIT" },
];

const MARKET_PANELS = [
  { value: "spot", label: "Spot" },
  { value: "futures", label: "Futures" },
];

const pickBestConnection = (rows = [], exchange = "binance", marketType = "spot") => {
  const matches = (rows || [])
    .filter((item) => String(item?.exchange || "").toLowerCase() === exchange)
    .filter((item) => String(item?.market_type || "").toLowerCase() === marketType)
    .filter((item) => String(item?.environment || "live").toLowerCase() === "live")
    .sort((a, b) => {
      const aDefault = a?.is_default ? 1 : 0;
      const bDefault = b?.is_default ? 1 : 0;
      if (aDefault !== bDefault) return bDefault - aDefault;
      return String(b?.updated_at || "").localeCompare(String(a?.updated_at || ""));
    });
  return matches[0] || null;
};

const statusMeta = (connection, isChecking = false) => {
  if (isChecking) {
    return {
      online: false,
      label: "Checking...",
      lightClass: "bg-amber-400",
      toneClass: "border-amber-500/40 bg-amber-950/20",
    };
  }

  const online = Boolean(
    connection
    && String(connection?.connection_health || "").toLowerCase() === "online"
    && Boolean(connection?.can_trade_effective),
  );
  return {
    online,
    label: online ? "Online" : "Pasif",
    lightClass: online ? "bg-emerald-500" : "bg-rose-500",
    toneClass: online ? "border-emerald-500/40 bg-emerald-950/20" : "border-rose-500/40 bg-rose-950/20",
  };
};

const formatTs = (value) => {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "-";
  return parsed.toLocaleString("tr-TR");
};

const toNumber = (value) => {
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
};

const formatAmount = (value) => {
  const num = toNumber(value);
  if (num === null) return "-";
  return num.toFixed(2);
};

const formatPnl = (value) => {
  const num = toNumber(value);
  if (num === null) return "-";
  const sign = num > 0 ? "+" : "";
  return `${sign}${num.toFixed(2)}`;
};

const getMiniWalletPnl = (connection) => {
  const snapshot = connection?.readiness_snapshot && typeof connection.readiness_snapshot === "object" ? connection.readiness_snapshot : {};
  const wallet = snapshot.wallet_balance ?? snapshot.available_balance ?? snapshot.total_wallet_balance ?? null;
  const pnl = snapshot.unrealized_pnl ?? snapshot.total_unrealized_pnl ?? snapshot.realized_pnl ?? null;
  return {
    wallet: formatAmount(wallet),
    pnl: formatPnl(pnl),
  };
};

const ERROR_LABEL_MAP = {
  exchange_error_451: "451: Regional Restriction",
  invalid_key: "Invalid API Key",
  invalid_ip: "Invalid IP",
};

const getLastErrorText = (connection) => {
  if (!connection) return "Bağlantı yok";
  const snapshot = connection?.readiness_snapshot && typeof connection.readiness_snapshot === "object" ? connection.readiness_snapshot : {};
  const reasonCodes = Array.isArray(snapshot.reason_codes) ? snapshot.reason_codes : [];
  const raw = String(
    snapshot.last_error
    || snapshot.error_message
    || snapshot.failure_reason
    || connection.connection_health_reason
    || reasonCodes[0]
    || "-",
  );
  return ERROR_LABEL_MAP[raw] || raw;
};

export const UserExchangeDiagnosticsPage = () => {
  const [selectedExchange, setSelectedExchange] = useState("binance");
  const [connections, setConnections] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [revalidatingMap, setRevalidatingMap] = useState({});

  const loadConnections = useCallback(async () => {
    setIsLoading(true);
    try {
      const { data } = await apiClient.get("/user/exchange-connections");
      setConnections(Array.isArray(data) ? data : []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Diagnostics bağlantıları yüklenemedi");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConnections();
  }, [loadConnections]);

  const panels = useMemo(() => {
    return MARKET_PANELS.map((panel) => {
      const panelKey = `${selectedExchange}-${panel.value}`;
      const connection = pickBestConnection(connections, selectedExchange, panel.value);
      const isChecking = Boolean(revalidatingMap[panelKey]);
      return {
        ...panel,
        panelKey,
        connection,
        status: statusMeta(connection, isChecking),
        mini: getMiniWalletPnl(connection),
        lastError: getLastErrorText(connection),
        isChecking,
      };
    });
  }, [connections, revalidatingMap, selectedExchange]);

  const onRevalidate = async (panel) => {
    if (selectedExchange === "bybit") {
      toast.info("BYBIT revalidate bu fazda kapalı. Sadece panel/state gösteriliyor.");
      return;
    }

    if (!panel?.connection?.id) {
      toast.error(`${panel.label} için kayıtlı live connection bulunamadı`);
      return;
    }

    setRevalidatingMap((prev) => ({ ...prev, [panel.panelKey]: true }));
    try {
      await apiClient.post(`/user/exchange-connections/${panel.connection.id}/revalidate`);
      toast.success(`${selectedExchange.toUpperCase()} ${panel.label}: Bağlantı Onaylandı`);
      await loadConnections();
    } catch (error) {
      toast.error(error?.response?.data?.detail || `${panel.label} revalidate başarısız`);
    } finally {
      setRevalidatingMap((prev) => ({ ...prev, [panel.panelKey]: false }));
    }
  };

  return (
    <section className="space-y-4" data-testid="user-exchange-diagnostics-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="user-exchange-diagnostics-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-exchange-diagnostics-title">Exchange Diagnostics</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-exchange-diagnostics-subtitle">
          Exchange Settings&apos;te kaydettiğiniz Spot/Futures keyleri buraya otomatik akar. Manuel key kopyalama yok.
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2" data-testid="user-exchange-diagnostics-top-tabs">
        {EXCHANGE_TABS.map((tab) => (
          <Button
            key={tab.value}
            type="button"
            className={selectedExchange === tab.value ? "h-14 bg-orange-500 text-black hover:bg-orange-600" : "h-14 bg-slate-800 text-slate-200 hover:bg-slate-700"}
            onClick={() => setSelectedExchange(tab.value)}
            data-testid={`user-exchange-diagnostics-tab-${tab.value}`}
          >
            {tab.label}
          </Button>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2" data-testid="user-exchange-diagnostics-market-panels">
        {panels.map((panel) => {
          const connectionId = panel.connection?.id || `${selectedExchange}-${panel.value}`;
          const isRevalidating = Boolean(revalidatingMap[panel.panelKey]);
          return (
            <article
              key={`${selectedExchange}-${panel.value}`}
              className={`relative border p-4 ${panel.status.toneClass}`}
              data-testid={`user-exchange-diagnostics-panel-${selectedExchange}-${panel.value}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-xs uppercase tracking-widest text-slate-500" data-testid={`user-exchange-diagnostics-panel-kicker-${selectedExchange}-${panel.value}`}>
                    {selectedExchange.toUpperCase()} · {panel.label}
                  </p>
                  <p className="mt-1 text-sm font-semibold text-slate-100" data-testid={`user-exchange-diagnostics-panel-profile-${selectedExchange}-${panel.value}`}>
                    {panel.connection?.account_label || "Bağlantı bulunamadı"}
                  </p>
                </div>
                <div className="inline-flex items-center gap-2" data-testid={`user-exchange-diagnostics-panel-status-wrap-${selectedExchange}-${panel.value}`}>
                  <span className={`inline-block h-3 w-3 rounded-full ${panel.status.lightClass}`} data-testid={`user-exchange-diagnostics-panel-status-light-${selectedExchange}-${panel.value}`} />
                  <span className="text-xs font-semibold text-slate-100" data-testid={`user-exchange-diagnostics-panel-status-text-${selectedExchange}-${panel.value}`}>{panel.status.label}</span>
                </div>
              </div>

              <div className="mt-3 space-y-1 text-xs text-slate-300" data-testid={`user-exchange-diagnostics-panel-meta-${selectedExchange}-${panel.value}`}>
                <p data-testid={`user-exchange-diagnostics-panel-meta-exchange-${selectedExchange}-${panel.value}`}>exchange: {selectedExchange}</p>
                <p data-testid={`user-exchange-diagnostics-panel-meta-market-${selectedExchange}-${panel.value}`}>market: {panel.value}</p>
                <p data-testid={`user-exchange-diagnostics-panel-meta-env-${selectedExchange}-${panel.value}`}>environment: {panel.connection?.environment || "live"}</p>
                <p data-testid={`user-exchange-diagnostics-panel-meta-key-${selectedExchange}-${panel.value}`}>api_key: {panel.connection?.has_api_key ? "mevcut" : "yok"}</p>
                <p data-testid={`user-exchange-diagnostics-panel-meta-secret-${selectedExchange}-${panel.value}`}>api_secret: {panel.connection?.has_api_secret ? "mevcut" : "yok"}</p>
                <p data-testid={`user-exchange-diagnostics-panel-meta-global-flag-${selectedExchange}-${panel.value}`}>
                  global_flag: {panel.connection?.global_activation_flag_key || `is_${selectedExchange}_${panel.value}_active`} = {panel.connection?.global_activation_active ? "true" : "false"}
                </p>
                <p data-testid={`user-exchange-diagnostics-panel-meta-last-success-${selectedExchange}-${panel.value}`}>last_success: {formatTs(panel.connection?.last_success_at)}</p>
                <p data-testid={`user-exchange-diagnostics-panel-meta-last-error-${selectedExchange}-${panel.value}`}>last_fail_reason: {panel.lastError}</p>
                {panel.status.online && (
                  <p className="text-emerald-300" data-testid={`user-exchange-diagnostics-panel-mini-wallet-pnl-${selectedExchange}-${panel.value}`}>
                    Wallet: {panel.mini.wallet} USDT | PNL: {panel.mini.pnl}$
                  </p>
                )}
              </div>

              <div className="mt-4 flex items-center justify-between gap-2" data-testid={`user-exchange-diagnostics-panel-actions-${selectedExchange}-${panel.value}`}>
                <Button
                  type="button"
                  onClick={() => onRevalidate(panel)}
                  disabled={selectedExchange === "bybit" || !panel.connection?.id || isRevalidating}
                  className="bg-orange-500 text-black hover:bg-orange-600"
                  data-testid={`user-exchange-diagnostics-panel-revalidate-${selectedExchange}-${panel.value}`}
                >
                  {isRevalidating ? "Doğrulanıyor..." : "Revalidate"}
                </Button>
                <span className="text-[11px] text-slate-400" data-testid={`user-exchange-diagnostics-panel-revalidate-note-${selectedExchange}-${panel.value}`}>
                  {selectedExchange === "bybit"
                    ? "BYBIT: bu fazda yalnızca panel/state aktif"
                    : (panel.connection?.id ? "Başarılı olursa sistem genelinde online işaretlenir" : "Önce Settings'ten key kaydedin")}
                </span>
              </div>

              <input type="hidden" value={connectionId} data-testid={`user-exchange-diagnostics-panel-connection-id-${selectedExchange}-${panel.value}`} readOnly />

              {selectedExchange === "bybit" && (
                <div className="pointer-events-none absolute inset-0 m-0 flex items-center justify-center bg-slate-950/70" data-testid={`user-exchange-diagnostics-bybit-overlay-${panel.value}`}>
                  <div className="rounded border border-amber-500/50 bg-slate-900/90 px-3 py-2 text-center">
                    <p className="text-sm font-semibold text-amber-300">Coming Soon</p>
                    <p className="text-xs text-slate-300">Setup Required (A Plan)</p>
                  </div>
                </div>
              )}
            </article>
          );
        })}
      </div>

      <div className="flex items-center justify-end" data-testid="user-exchange-diagnostics-refresh-row">
        <Button type="button" variant="outline" onClick={loadConnections} disabled={isLoading} data-testid="user-exchange-diagnostics-refresh-button">
          {isLoading ? "Yenileniyor..." : "Bağlantıları Yenile"}
        </Button>
      </div>
    </section>
  );
};
