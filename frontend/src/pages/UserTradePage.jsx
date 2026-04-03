import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient, buildSessionHeaders, FRONTEND_BACKEND_URL } from "@/lib/api";

const DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"];

const defaultForm = {
  symbol: "BTCUSDT",
  side: "buy",
  size_mode: "USDT",
  size_value: 100,
  leverage: 1,
  margin_type: "isolated",
  order_type: "market",
  price: "",
  stop_price: "",
  take_profit_price: "",
  stop_loss_mode: "none",
  take_profit_mode: "none",
};

const parseErrorText = (error) => {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (detail?.code) {
    return detail.code;
  }
  return "trade_submit_failed";
};

const postJsonWithSession = async (path, body) => {
  const token = window.localStorage.getItem("token");
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 45000);
  let response;
  try {
    response = await fetch(`${FRONTEND_BACKEND_URL}/api${path}`, {
      method: "POST",
      headers: {
        ...buildSessionHeaders(),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      credentials: "include",
      cache: "no-store",
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } finally {
    window.clearTimeout(timeoutId);
  }
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const error = new Error((payload && (payload.detail || payload.message || payload.reason_code)) || `request_failed_${response.status}`);
    error.response = { status: response.status, data: payload };
    throw error;
  }
  return payload;
};

const formatConnectionLabel = (connection) => {
  const accountLabel = String(connection?.account_label || "connection").trim();
  const exchange = String(connection?.exchange || "-").trim();
  const marketType = String(connection?.market_type || "-").trim();
  const environment = String(connection?.environment || "-").trim();
  return `${accountLabel} · ${exchange}/${marketType}/${environment}`;
};

export const UserTradePage = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [form, setForm] = useState(defaultForm);
  const [symbolOptions, setSymbolOptions] = useState(DEFAULT_SYMBOLS);
  const [connections, setConnections] = useState([]);
  const [selectedConnectionId, setSelectedConnectionId] = useState("");
  const [midPrice, setMidPrice] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [validationResult, setValidationResult] = useState(null);
  const [previewResult, setPreviewResult] = useState(null);
  const [executionResult, setExecutionResult] = useState(null);
  const [openOrders, setOpenOrders] = useState([]);
  const [confirmChecked, setConfirmChecked] = useState(false);

  const estimatedQty = useMemo(() => {
    const sizeValue = Number(form.size_value || 0);
    const price = Number(midPrice || 0);
    if (form.size_mode === "QTY") {
      return Number(sizeValue.toFixed(6));
    }
    if (price <= 0) {
      return 0;
    }
    return Number((sizeValue / price).toFixed(6));
  }, [form.size_mode, form.size_value, midPrice]);

  const orderSizeForValidation = useMemo(() => {
    if (form.size_mode === "USDT") {
      const fallback = Number(form.size_value || 0);
      const qty = Number(estimatedQty || 0);
      return qty > 0 ? qty : fallback;
    }
    return Number(estimatedQty || 0);
  }, [form.size_mode, form.size_value, estimatedQty]);

  const canRunValidation = useMemo(() => {
    if (!form.symbol) return false;
    if (form.size_mode === "USDT") {
      return Number(form.size_value || 0) > 0;
    }
    return Number(estimatedQty || 0) > 0;
  }, [form.symbol, form.size_mode, form.size_value, estimatedQty]);
  const canConfirmPreview = useMemo(() => {
    const preview = previewResult?.preview || {};
    const status = String(preview.validation_status || "").toLowerCase();
    const hasToken = Boolean(preview.intent_token);
    if (!hasToken) return false;
    if (!status) return true;
    return ["valid", "approved", "ready"].includes(status);
  }, [previewResult]);
  const isFutures = useMemo(() => {
    const selectedConnection = connections.find((row) => row.id === selectedConnectionId);
    return String(selectedConnection?.market_type || "spot").toLowerCase() === "futures";
  }, [connections, selectedConnectionId]);

  useEffect(() => {
    const symbolFromQuery = String(searchParams.get("symbol") || "").trim().toUpperCase();
    if (symbolFromQuery) {
      setForm((prev) => ({ ...prev, symbol: symbolFromQuery }));
    }
  }, [searchParams]);

  useEffect(() => {
    const loadBootstrap = async () => {
      setIsLoading(true);
      try {
        const [connectionRes, screenerRes] = await Promise.all([
          apiClient.get("/user/exchange-connections"),
          apiClient.get("/screener", { params: { limit: 80 } }),
        ]);
        const connectionRows = connectionRes.data || [];
        setConnections(connectionRows);
        const defaultConnection = connectionRows.find((row) => row.is_default) || connectionRows[0] || null;
        setSelectedConnectionId((prev) => {
          if (prev && connectionRows.some((row) => row.id === prev)) {
            return prev;
          }
          return defaultConnection?.id || "";
        });

        const scannerSymbols = (screenerRes.data || [])
          .map((row) => String(row.symbol || "").trim().toUpperCase())
          .filter(Boolean);
        const merged = Array.from(new Set([...DEFAULT_SYMBOLS, ...scannerSymbols]));
        setSymbolOptions(merged.length > 0 ? merged : DEFAULT_SYMBOLS);
      } catch {
        setSymbolOptions(DEFAULT_SYMBOLS);
      } finally {
        setIsLoading(false);
      }
    };

    loadBootstrap();
  }, []);

  useEffect(() => {
    const loadTicker = async () => {
      if (!form.symbol) {
        setMidPrice(0);
        return;
      }
      try {
        const { data } = await apiClient.get("/market/ticker", {
          params: { symbol: form.symbol },
        });
        setMidPrice(Number(data?.mid_price || 0));
      } catch {
        setMidPrice(0);
      }
    };

    loadTicker();
  }, [form.symbol]);

  useEffect(() => {
    const loadOpenOrders = async () => {
      try {
        const { data } = await apiClient.get("/user/execution/intents", { params: { limit: 20 } });
        setOpenOrders((data || []).filter((item) => ["PREVIEWED", "QUEUED", "APPROVED", "SUBMITTED"].includes(String(item.status || "").toUpperCase())));
      } catch {
        setOpenOrders([]);
      }
    };
    loadOpenOrders();
  }, [executionResult, previewResult]);

  useEffect(() => {
    setPreviewResult(null);
    setConfirmChecked(false);
  }, [
    selectedConnectionId,
    form.symbol,
    form.side,
    form.order_type,
    form.size_mode,
    form.size_value,
    form.leverage,
    form.margin_type,
  ]);

  const runValidation = async ({ silent = false } = {}) => {
    const payload = {
      symbol: form.symbol,
      market_type: isFutures ? "futures" : "spot",
      order_type: form.order_type,
      side: form.side,
      price: Number(form.price || midPrice || 0),
      size: Number(orderSizeForValidation || 0),
      leverage: isFutures ? Number(form.leverage || 1) : 1,
      margin_mode: isFutures ? form.margin_type : "isolated",
    };

    const { data } = await apiClient.post("/user/validate-order", payload);
    setValidationResult(data);

    if (!silent) {
      if (data?.valid) {
        toast.success("Validation başarılı");
      } else {
        toast.error("Validation failed: trade açılması engellendi");
      }
    }
    return data;
  };

  const handlePreview = async () => {
    try {
      const validation = await runValidation({ silent: true });
      const stalePreviewOrders = openOrders.filter(
        (item) =>
          String(item.symbol || "").toUpperCase() === String(form.symbol || "").toUpperCase() &&
          ["PREVIEWED", "REJECTED"].includes(String(item.status || "").toUpperCase()),
      );
      for (const item of stalePreviewOrders) {
        try {
          await apiClient.post("/user/execution/intent/cancel", { intent_token: item.intent_token });
        } catch {
          // stale cancel hatası preview akışını bloklamasın
        }
      }
      const hasExecutionModeSwitch = (validation?.violations || []).some((item) => item.code === "execution_mode_switch_required");
      const resolvedOrderType = (() => {
        const currentType = String(form.order_type || "market").toUpperCase();
        if (!hasExecutionModeSwitch) {
          return currentType;
        }
        if (currentType === "STOP_LOSS") return "STOP_LOSS_LIMIT";
        if (currentType === "TAKE_PROFIT") return "TAKE_PROFIT_LIMIT";
        return currentType.includes("LIMIT") ? currentType : "LIMIT";
      })();
      const payload = {
        source_type: "manual",
        intent_type: "OPEN_POSITION",
        market_type: isFutures ? "futures" : "spot",
        symbol: form.symbol,
        side: form.side,
        order_type: resolvedOrderType,
        position_size_mode: "fixed_notional",
        position_size_value: form.size_mode === "USDT" ? Number(form.size_value || 0) : Number((Number(form.size_value || 0) * Number(midPrice || 0)).toFixed(4)),
        margin_mode: isFutures ? form.margin_type : null,
        leverage: isFutures ? Number(form.leverage || 1) : null,
        size: Number(orderSizeForValidation || 0),
        price: form.price ? Number(form.price) : undefined,
        stop_price: form.stop_price ? Number(form.stop_price) : undefined,
        take_profit_price: form.take_profit_price ? Number(form.take_profit_price) : undefined,
        take_profit_mode: form.take_profit_mode,
        stop_loss_mode: form.stop_loss_mode,
        execution_mode: "manual",
        exchange_connection_id: selectedConnectionId || null,
      };
      const data = await postJsonWithSession("/v1/user/trading/preview", payload);
      setPreviewResult(data);
      setConfirmChecked(false);
      const previewStatus = String(data?.preview?.validation_status || "").toLowerCase();
      const rejectCodes = (data?.preview?.reject_reason_codes || []).filter(Boolean);
      if (previewStatus && !["valid", "approved", "ready"].includes(previewStatus)) {
        toast.error(`Preview geçersiz: ${rejectCodes.join(", ") || previewStatus}`);
        return;
      }
      if (!validation?.valid) {
        toast.warning(hasExecutionModeSwitch ? "Fast market tespit edildi; preview limit-style moda adapte edildi" : "Validation warning var; preview panelinde detayları inceleyin");
      } else {
        toast.success("Preview oluşturuldu");
      }
    } catch (error) {
      const detail = error?.response?.data?.detail;
      if (String(detail || "").includes("duplicate_execution_intent")) {
        toast.error("Aynı sembol için açık preview/order bulundu. Önce mevcut order’ı iptal edin.");
      } else {
        toast.error(parseErrorText(error));
      }
    }
  };

  const handleValidateOnly = async () => {
    try {
      await runValidation();
    } catch (error) {
      toast.error(parseErrorText(error));
    }
  };

  const handleConfirmAndExecute = async () => {
    if (!previewResult?.preview?.intent_token || !confirmChecked || !canConfirmPreview) {
      toast.error("Confirm onayı gerekli");
      return;
    }
    setIsSubmitting(true);
    setExecutionResult(null);

    try {
      const submitRes = await postJsonWithSession("/user/open-position", {
        intent_token: previewResult.preview.intent_token,
        preview_hash: previewResult.preview.preview_hash,
      });

      const executionMode =
        submitRes?.execution_mode || previewResult?.preview?.execution_mode || "mocked";

      setExecutionResult({
        status: "submitted",
        intent_id: submitRes?.intent_id,
        queue_state: submitRes?.queue_state,
        reason_codes: submitRes?.reason_codes || [],
        execution_mode: executionMode,
        policy_decision: submitRes?.policy_decision || {},
        pipeline_trace: submitRes?.pipeline_trace || [],
        explain: submitRes?.explain || [],
        error_text: "",
      });

      toast.success("Order confirmed → execution queue’ya gönderildi");
    } catch (error) {
      const statusCode = Number(error?.response?.status || 0);
      const detail = error?.response?.data?.detail;
      const violations = Array.isArray(detail?.violations) ? detail.violations : [];

      setExecutionResult({
        status: "failed",
        execution_mode: previewResult?.preview?.execution_mode || validationResult?.execution_mode || "mocked",
        violations,
        explain: validationResult?.explain || [],
        error_text: statusCode === 423 ? "EXECUTION_BLOCKED_BY_READINESS" : parseErrorText(error),
      });
      if (statusCode === 423) {
        toast.error("Execution blocked by readiness (423)");
      } else {
        toast.error(parseErrorText(error));
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading) {
    return (
      <section className="rounded border border-slate-800 bg-slate-900 p-6" data-testid="user-trade-loading-state">
        <p className="text-sm text-slate-300" data-testid="user-trade-loading-text">Trade panel hazırlanıyor...</p>
      </section>
    );
  }

  const executionStateClass =
    executionResult?.status === "submitted"
      ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-100"
      : "border-red-500/60 bg-red-500/10 text-red-100";

  return (
    <section className="grid grid-cols-12 gap-4" data-testid="user-trade-page">
      <header className="col-span-12 rounded border border-slate-800 bg-slate-900 p-4" data-testid="user-trade-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-trade-title">Trade Entry Panel</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-trade-description">
          Zorunlu akış: validate-order → valid ise open-position.
        </p>
      </header>

      <div className="col-span-12 lg:col-span-7 rounded border border-slate-800 bg-slate-900 p-4" data-testid="user-trade-form-card">
        <div className="grid grid-cols-12 gap-3" data-testid="user-trade-form-grid">
          <div className="col-span-12 md:col-span-6" data-testid="user-trade-symbol-field">
            <label className="text-xs text-slate-400" htmlFor="user-trade-symbol-select" data-testid="user-trade-symbol-label">Symbol</label>
            <select
              id="user-trade-symbol-select"
              className="mt-1 h-10 w-full rounded border border-slate-700 bg-slate-950 px-3 text-sm"
              value={form.symbol}
              onChange={(event) => setForm((prev) => ({ ...prev, symbol: event.target.value.toUpperCase() }))}
              data-testid="user-trade-symbol-select"
            >
              {symbolOptions.map((symbol) => (
                <option key={symbol} value={symbol} data-testid={`user-trade-symbol-option-${symbol}`}>
                  {symbol}
                </option>
              ))}
            </select>
          </div>

          <div className="col-span-12 md:col-span-6" data-testid="user-trade-side-field">
            <label className="text-xs text-slate-400" htmlFor="user-trade-side-select">Side</label>
            <select id="user-trade-side-select" className="mt-1 h-10 w-full rounded border border-slate-700 bg-slate-950 px-3 text-sm" value={form.side} onChange={(event) => setForm((prev) => ({ ...prev, side: event.target.value }))} data-testid="user-trade-side-select">
              <option value="buy">BUY</option>
              <option value="sell">SELL</option>
            </select>
          </div>

          <div className="col-span-12 md:col-span-6" data-testid="user-trade-connection-field">
            <label className="text-xs text-slate-400" htmlFor="user-trade-connection-select" data-testid="user-trade-connection-label">Exchange Connection</label>
            <select
              id="user-trade-connection-select"
              className="mt-1 h-10 w-full rounded border border-slate-700 bg-slate-950 px-3 text-sm"
              value={selectedConnectionId}
              onChange={(event) => setSelectedConnectionId(event.target.value)}
              data-testid="user-trade-connection-select"
            >
              {connections.length === 0 && <option value="" data-testid="user-trade-connection-option-empty">no-connection</option>}
              {connections.map((connection) => (
                <option key={connection.id} value={connection.id} data-testid={`user-trade-connection-option-${connection.id}`}>
                  {formatConnectionLabel(connection)}
                </option>
              ))}
            </select>
          </div>

          <div className="col-span-6 md:col-span-3" data-testid="user-trade-size-mode-field">
            <label className="text-xs text-slate-400" htmlFor="user-trade-size-mode-select" data-testid="user-trade-size-mode-label">Size Mode</label>
            <select
              id="user-trade-size-mode-select"
              className="mt-1 h-10 w-full rounded border border-slate-700 bg-slate-950 px-3 text-sm"
              value={form.size_mode}
              onChange={(event) => setForm((prev) => ({ ...prev, size_mode: event.target.value }))}
              data-testid="user-trade-size-mode-select"
            >
              <option value="USDT" data-testid="user-trade-size-mode-option-usdt">USDT</option>
              <option value="QTY" data-testid="user-trade-size-mode-option-qty">QTY</option>
            </select>
          </div>

          <div className="col-span-6 md:col-span-3" data-testid="user-trade-size-value-field">
            <label className="text-xs text-slate-400" htmlFor="user-trade-size-value-input" data-testid="user-trade-size-value-label">Size</label>
            <Input
              id="user-trade-size-value-input"
              type="number"
              min="0"
              step="0.0001"
              value={form.size_value}
              onChange={(event) => setForm((prev) => ({ ...prev, size_value: Number(event.target.value || 0) }))}
              data-testid="user-trade-size-value-input"
            />
          </div>

          {isFutures && <div className="col-span-6 md:col-span-3" data-testid="user-trade-leverage-field">
            <label className="text-xs text-slate-400" htmlFor="user-trade-leverage-input" data-testid="user-trade-leverage-label">Leverage</label>
            <Input
              id="user-trade-leverage-input"
              type="number"
              min="1"
              max="125"
              value={form.leverage}
              onChange={(event) => setForm((prev) => ({ ...prev, leverage: Number(event.target.value || 1) }))}
              data-testid="user-trade-leverage-input"
            />
          </div>}

          {isFutures && <div className="col-span-6 md:col-span-3" data-testid="user-trade-margin-type-field">
            <label className="text-xs text-slate-400" htmlFor="user-trade-margin-type-select" data-testid="user-trade-margin-type-label">Margin Type</label>
            <select
              id="user-trade-margin-type-select"
              className="mt-1 h-10 w-full rounded border border-slate-700 bg-slate-950 px-3 text-sm"
              value={form.margin_type}
              onChange={(event) => setForm((prev) => ({ ...prev, margin_type: event.target.value }))}
              data-testid="user-trade-margin-type-select"
            >
              <option value="isolated" data-testid="user-trade-margin-type-option-isolated">isolated</option>
              <option value="cross" data-testid="user-trade-margin-type-option-cross">cross</option>
            </select>
          </div>}

          <div className="col-span-12 md:col-span-4" data-testid="user-trade-order-type-field">
            <label className="text-xs text-slate-400" htmlFor="user-trade-order-type-select" data-testid="user-trade-order-type-label">Order Type</label>
            <select
              id="user-trade-order-type-select"
              className="mt-1 h-10 w-full rounded border border-slate-700 bg-slate-950 px-3 text-sm"
              value={form.order_type}
              onChange={(event) => setForm((prev) => ({ ...prev, order_type: event.target.value }))}
              data-testid="user-trade-order-type-select"
            >
              <option value="market" data-testid="user-trade-order-type-option-market">market</option>
              <option value="limit" data-testid="user-trade-order-type-option-limit">limit</option>
              <option value="stop_loss" data-testid="user-trade-order-type-option-stop-loss">stop</option>
              <option value="stop_loss_limit" data-testid="user-trade-order-type-option-stop-limit">stop-limit</option>
              <option value="take_profit" data-testid="user-trade-order-type-option-tp">tp</option>
              <option value="take_profit_limit" data-testid="user-trade-order-type-option-tp-limit">tp-limit</option>
            </select>
          </div>

          {form.order_type !== "market" && (
            <div className="col-span-6 md:col-span-4" data-testid="user-trade-price-field">
              <label className="text-xs text-slate-400" htmlFor="user-trade-price-input">Limit Price</label>
              <Input id="user-trade-price-input" type="number" min="0" step="0.0001" value={form.price} onChange={(event) => setForm((prev) => ({ ...prev, price: event.target.value }))} data-testid="user-trade-price-input" />
            </div>
          )}
          {form.order_type.includes("stop") && (
            <div className="col-span-6 md:col-span-4" data-testid="user-trade-stop-price-field">
              <label className="text-xs text-slate-400" htmlFor="user-trade-stop-price-input">Stop Price</label>
              <Input id="user-trade-stop-price-input" type="number" min="0" step="0.0001" value={form.stop_price} onChange={(event) => setForm((prev) => ({ ...prev, stop_price: event.target.value }))} data-testid="user-trade-stop-price-input" />
            </div>
          )}
          {form.order_type.includes("take_profit") && (
            <div className="col-span-6 md:col-span-4" data-testid="user-trade-take-profit-price-field">
              <label className="text-xs text-slate-400" htmlFor="user-trade-take-profit-price-input">Take Profit Price</label>
              <Input id="user-trade-take-profit-price-input" type="number" min="0" step="0.0001" value={form.take_profit_price} onChange={(event) => setForm((prev) => ({ ...prev, take_profit_price: event.target.value }))} data-testid="user-trade-take-profit-price-input" />
            </div>
          )}

          <div className="col-span-12 md:col-span-8 rounded border border-slate-700 bg-slate-950 p-3" data-testid="user-trade-estimation-card">
            <p className="text-xs text-slate-400" data-testid="user-trade-mid-price-label">Mid Price</p>
            <p className="text-sm font-semibold text-slate-100" data-testid="user-trade-mid-price-value">{midPrice || 0}</p>
            <p className="mt-1 text-xs text-slate-400" data-testid="user-trade-estimated-qty-label">Estimated Qty</p>
            <p className="text-sm font-semibold text-emerald-300" data-testid="user-trade-estimated-qty-value">{estimatedQty}</p>
          </div>
        </div>

        {validationResult && !validationResult.valid && (
          <div className="mt-4 rounded border border-red-500/70 bg-red-500/10 p-3" data-testid="user-trade-validation-failed-panel">
            <p className="text-sm font-semibold text-red-200" data-testid="user-trade-validation-failed-title">Validation Failed</p>
            <div className="mt-2 space-y-1" data-testid="user-trade-validation-failed-list">
              {(validationResult.violations || []).map((violation, index) => (
                <p
                  key={`${violation.code}-${index}`}
                  className="text-xs text-red-100"
                  data-testid={`user-trade-validation-failed-item-${index}`}
                >
                  {violation.code}: {violation.message}
                </p>
              ))}
            </div>
          </div>
        )}

        {validationResult && (validationResult.explain || []).length > 0 && (
          <div className="mt-4 rounded border border-cyan-500/60 bg-cyan-500/10 p-3" data-testid="user-trade-validation-explain-panel">
            <p className="text-sm font-semibold text-cyan-100" data-testid="user-trade-validation-explain-title">Validation Explain</p>
            <div className="mt-2 space-y-1" data-testid="user-trade-validation-explain-list">
              {(validationResult.explain || []).map((item, index) => (
                <p key={`${item}-${index}`} className="text-xs text-cyan-50" data-testid={`user-trade-validation-explain-item-${index}`}>
                  {item}
                </p>
              ))}
            </div>
          </div>
        )}

        <div className="mt-4 flex flex-wrap gap-2" data-testid="user-trade-action-buttons">
          <Button
            type="button"
            variant="outline"
            onClick={handleValidateOnly}
            disabled={!canRunValidation}
            data-testid="user-trade-validate-button"
          >
            Validate
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={handlePreview}
            disabled={isSubmitting || !canRunValidation}
            data-testid="user-trade-preview-button"
          >
            Preview
          </Button>
        </div>
        {!canRunValidation && (
          <p className="mt-2 text-xs text-amber-300" data-testid="user-trade-actions-disabled-hint">
            Market fiyatı yüklenene kadar validate/trade aksiyonu kilitli.
          </p>
        )}
      </div>

      <aside className="col-span-12 lg:col-span-5 rounded border border-slate-800 bg-slate-900 p-4" data-testid="user-trade-right-column">
        <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="user-trade-preview-title">Order Preview</p>

        {!previewResult && <p className="mt-3 text-sm text-slate-300" data-testid="user-trade-preview-empty">Henüz preview yok.</p>}

        {previewResult && (
          <div className="mt-3 space-y-3" data-testid="user-trade-preview-panel">
            <pre className="overflow-x-auto rounded border border-cyan-500/60 bg-cyan-500/10 p-3 text-xs text-cyan-50" data-testid="user-trade-preview-metrics-json">{JSON.stringify(previewResult.metrics || {}, null, 2)}</pre>
            <pre className="overflow-x-auto rounded border border-slate-700 bg-slate-950 p-3 text-xs text-slate-200" data-testid="user-trade-preview-intent-json">{JSON.stringify(previewResult.preview || {}, null, 2)}</pre>
            <label className="flex items-center gap-2 text-sm text-slate-300" data-testid="user-trade-confirm-checkbox-wrapper">
              <input type="checkbox" checked={confirmChecked} onChange={(event) => setConfirmChecked(event.target.checked)} data-testid="user-trade-confirm-checkbox" />
              Risk preview ve execution etkisini okudum, confirm ediyorum.
            </label>
            <Button type="button" onClick={handleConfirmAndExecute} disabled={isSubmitting || !confirmChecked || !canConfirmPreview} data-testid="user-trade-confirm-order-button">
              {isSubmitting ? "Executing..." : "Confirm Order"}
            </Button>
            {!canConfirmPreview && (
              <p className="text-xs text-amber-200" data-testid="user-trade-preview-invalid-hint">
                Preview geçersiz; notional/kurallar uygun olduğunda confirm aktif olur.
              </p>
            )}
          </div>
        )}

        <div className="mt-6 border-t border-slate-800 pt-4" data-testid="user-trade-open-orders-panel">
          <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="user-trade-open-orders-title">Open Orders</p>
          <div className="mt-3 space-y-2" data-testid="user-trade-open-orders-list">
            {openOrders.length === 0 && <p className="text-sm text-slate-300" data-testid="user-trade-open-orders-empty">Açık order yok.</p>}
            {openOrders.map((row, idx) => (
              <div key={`${row.id}-${idx}`} className="rounded border border-slate-700 bg-slate-950 p-3" data-testid={`user-trade-open-order-item-${idx}`}>
                <p className="font-mono text-xs">{row.symbol} · {row.status}</p>
                <p className="mt-1 text-xs text-slate-400">intent={row.intent_token}</p>
                <Button
                  type="button"
                  variant="outline"
                  className="mt-2"
                  onClick={async () => {
                    try {
                      await apiClient.post('/user/execution/intent/cancel', { intent_token: row.intent_token });
                      toast.success('Open order cancelled');
                      const { data } = await apiClient.get('/user/execution/intents', { params: { limit: 20 } });
                      setOpenOrders((data || []).filter((item) => ['PREVIEWED', 'QUEUED', 'APPROVED', 'SUBMITTED'].includes(String(item.status || '').toUpperCase())));
                    } catch (error) {
                      toast.error(parseErrorText(error));
                    }
                  }}
                  data-testid={`user-trade-open-order-cancel-button-${idx}`}
                >
                  Cancel
                </Button>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-6 border-t border-slate-800 pt-4" data-testid="user-trade-result-card">
          <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="user-trade-result-title">Execution Feedback</p>

        {!executionResult && (
          <p className="mt-3 text-sm text-slate-300" data-testid="user-trade-result-empty">
            Henüz trade sonucu yok.
          </p>
        )}

        {executionResult && (
          <div className={`mt-3 rounded border p-3 ${executionStateClass}`} data-testid="user-trade-result-state">
            <p className="text-sm font-semibold" data-testid="user-trade-result-status">
              status: {executionResult.status}
            </p>
            {executionResult.intent_id && <p className="mt-1 text-xs" data-testid="user-trade-result-intent-id">intent_id: {executionResult.intent_id}</p>}
            {executionResult.queue_state && <p className="mt-1 text-xs" data-testid="user-trade-result-queue-state">queue_state: {executionResult.queue_state}</p>}
            <p className="mt-1 inline-flex rounded-full border border-current px-2 py-0.5 text-xs" data-testid="user-trade-result-execution-mode">
              execution_mode: {executionResult.execution_mode}
            </p>
            {executionResult.error_text && (
              <p className="mt-2 text-xs" data-testid="user-trade-result-error-text">{executionResult.error_text}</p>
            )}
            {(executionResult.violations || []).length > 0 && (
              <div className="mt-2 space-y-1" data-testid="user-trade-result-violations-list">
                {(executionResult.violations || []).map((violation, index) => (
                  <p key={`${violation.code || "violation"}-${index}`} className="text-xs" data-testid={`user-trade-result-violation-item-${index}`}>
                    {violation.code}: {violation.message}
                  </p>
                ))}
              </div>
            )}
            {(executionResult.explain || []).length > 0 && (
              <div className="mt-2 space-y-1" data-testid="user-trade-result-explain-list">
                {(executionResult.explain || []).map((item, index) => (
                  <p key={`${item}-${index}`} className="text-xs" data-testid={`user-trade-result-explain-item-${index}`}>
                    {item}
                  </p>
                ))}
              </div>
            )}
            <div className="mt-3 flex flex-wrap gap-2" data-testid="user-trade-result-shortcuts">
              <Button type="button" variant="outline" onClick={() => navigate('/user/trades')} data-testid="user-trade-result-view-history-button">View in history</Button>
              <Button type="button" variant="outline" onClick={() => navigate('/user/execution')} data-testid="user-trade-result-view-execution-button">View in execution panel</Button>
            </div>
          </div>
        )}
        </div>
      </aside>
    </section>
  );
};
