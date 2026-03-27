import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const CapabilityMatrixPanel = ({ matrixData, loading, error, onRefresh, onSaveOverride }) => {
  const matrixKeys = useMemo(() => Object.keys(matrixData || {}).sort(), [matrixData]);
  const [selectedKey, setSelectedKey] = useState("");
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [supportLevel, setSupportLevel] = useState("supported");
  const [note, setNote] = useState("");
  const [flags, setFlags] = useState({
    supports_leverage: false,
    supports_reduce_only: false,
    supports_margin_mode: false,
    supports_hedge_mode: false,
  });

  const activeKey = selectedKey || matrixKeys[0] || "";
  const activeMatrix = (matrixData || {})[activeKey] || {};
  const symbolCapabilities = activeMatrix.symbol_capabilities || [];

  const updateFlag = (key, value) => setFlags((prev) => ({ ...prev, [key]: value }));

  const saveOverride = async () => {
    if (!activeKey) return;
    const [exchange_code, market_type, environment] = activeKey.split(":");
    await onSaveOverride({
      exchange_code,
      market_type,
      environment,
      symbol: symbol.toUpperCase(),
      support_level: supportLevel,
      note,
      ...flags,
    });
  };

  return (
    <section className="rounded-2xl border border-slate-700 bg-slate-950/70 p-4" data-testid="capability-matrix-panel">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-orange-200" data-testid="capability-matrix-panel-title">Capability Matrix + Override</h3>
          <p className="text-xs text-slate-400" data-testid="capability-matrix-panel-subtitle">Exchange → Symbol capability görünümü ve manuel override</p>
        </div>
        <Button type="button" variant="outline" onClick={onRefresh} data-testid="capability-matrix-refresh-button">Yenile</Button>
      </div>

      {loading && <p className="text-sm text-slate-400" data-testid="capability-matrix-loading-state">Yükleniyor...</p>}
      {!loading && error && <p className="text-sm text-red-300" data-testid="capability-matrix-error-state">{error}</p>}
      {!loading && !error && matrixKeys.length === 0 && (
        <p className="text-sm text-slate-400" data-testid="capability-matrix-empty-state">Capability matrix boş.</p>
      )}

      {!loading && !error && matrixKeys.length > 0 && (
        <>
          <div className="mb-3 grid gap-2 md:grid-cols-3" data-testid="capability-matrix-controls">
            <select value={activeKey} onChange={(event) => setSelectedKey(event.target.value)} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm" data-testid="capability-matrix-key-select">
              {matrixKeys.map((key) => (
                <option key={key} value={key}>{key}</option>
              ))}
            </select>
            <Input value={symbol} onChange={(event) => setSymbol(event.target.value)} placeholder="BTCUSDT" data-testid="capability-matrix-override-symbol-input" />
            <select value={supportLevel} onChange={(event) => setSupportLevel(event.target.value)} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm" data-testid="capability-matrix-override-support-level-select">
              <option value="supported">supported</option>
              <option value="partial">partial</option>
              <option value="unsupported">unsupported</option>
            </select>
            <Input value={note} onChange={(event) => setNote(event.target.value)} placeholder="override note" className="md:col-span-2" data-testid="capability-matrix-override-note-input" />
            <Button type="button" onClick={saveOverride} data-testid="capability-matrix-override-save-button">Override Kaydet</Button>
          </div>

          <div className="mb-3 grid gap-2 md:grid-cols-2" data-testid="capability-matrix-override-flags-grid">
            {Object.entries(flags).map(([key, value]) => (
              <label key={key} className="flex items-center gap-2 text-xs text-slate-300" data-testid={`capability-matrix-override-flag-row-${key}`}>
                <input type="checkbox" checked={Boolean(value)} onChange={(event) => updateFlag(key, event.target.checked)} data-testid={`capability-matrix-override-flag-checkbox-${key}`} />
                {key}
              </label>
            ))}
          </div>

          <div className="max-h-52 overflow-auto text-xs" data-testid="capability-matrix-symbol-list">
            {(symbolCapabilities || []).length === 0 && <p data-testid="capability-matrix-symbol-list-empty">Bu anahtar için sembol kaydı yok.</p>}
            {(symbolCapabilities || []).slice(0, 50).map((item, index) => (
              <p key={`${item.symbol}-${index}`} className="border-t border-slate-800 py-1 text-slate-200" data-testid={`capability-matrix-symbol-row-${index}`}>
                {item.symbol}: {item.support_level || "partial"} · lev={String(Boolean(item.supports_leverage))} · ro={String(Boolean(item.supports_reduce_only))}
              </p>
            ))}
          </div>
        </>
      )}
    </section>
  );
};
