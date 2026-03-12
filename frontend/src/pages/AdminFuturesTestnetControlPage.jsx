import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

export const AdminFuturesTestnetControlPage = () => {
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [status, setStatus] = useState(null);
  const [gate, setGate] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setErrorMessage("");
    try {
      const [statusResponse, gateResponse] = await Promise.all([
        apiClient.get("/admin/futures/testnet/status"),
        apiClient.get("/admin/futures/testnet/release-gate"),
      ]);
      setStatus(statusResponse.data || null);
      setGate(gateResponse.data || null);
    } catch (error) {
      const message = error?.response?.data?.detail || "Testnet kontrol verisi alınamadı";
      setErrorMessage(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const retryMatrix = useMemo(() => status?.retry_policy || [], [status]);
  const preflightChecks = useMemo(() => status?.preflight_template?.checks || [], [status]);

  return (
    <section className="space-y-4" data-testid="admin-futures-testnet-control-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="admin-futures-testnet-control-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-black" data-testid="admin-futures-testnet-control-title">
          Futures Testnet Control
        </h2>
        <p className="mt-2 text-sm text-black/80" data-testid="admin-futures-testnet-control-description">
          Testnet release gate ve execution safety görünürlüğü (read-only).
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 border border-black/30 bg-orange-100 p-4" data-testid="admin-futures-testnet-control-toolbar">
        <Button className="border border-black bg-black text-orange-400 hover:bg-zinc-800" onClick={loadData} data-testid="admin-futures-testnet-control-refresh-button">
          Yenile
        </Button>
        <p className="text-sm text-black" data-testid="admin-futures-testnet-control-loading-text">loading: {String(loading)}</p>
      </div>

      {loading && <div className="border border-black/25 bg-orange-50 p-4 text-sm" data-testid="admin-futures-testnet-control-loading-state">Testnet verileri yükleniyor...</div>}
      {!loading && errorMessage && <div className="border border-red-700 bg-red-100 p-4 text-sm text-red-900" data-testid="admin-futures-testnet-control-error-state">Hata: {errorMessage}</div>}

      {!loading && !errorMessage && (
        <>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4" data-testid="testnet-control-summary-grid">
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="testnet-enabled-card">
              <p className="text-xs uppercase">Testnet Enabled</p>
              <p className="text-xl font-bold" data-testid="testnet-enabled-value">{String(status?.testnet_enabled ?? false)}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="testnet-default-mode-card">
              <p className="text-xs uppercase">Default Mode</p>
              <p className="text-xl font-bold" data-testid="testnet-default-mode-value">{status?.default_mode || "paper"}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="testnet-release-gate-status-card">
              <p className="text-xs uppercase">Release Gate</p>
              <p className="text-xl font-bold" data-testid="testnet-release-gate-status-value">{gate?.status || "BLOCKED"}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="testnet-order-path-open-card">
              <p className="text-xs uppercase">Order Path Open</p>
              <p className="text-xl font-bold" data-testid="testnet-order-path-open-value">{String(gate?.order_path_open ?? false)}</p>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="testnet-control-middle-grid">
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="testnet-release-gate-reasons-panel">
              <h3 className="text-lg font-bold" data-testid="testnet-release-gate-reasons-title">Release Gate Reasons</h3>
              <div className="mt-2 space-y-1" data-testid="testnet-release-gate-reasons-list">
                {(gate?.reasons || []).map((reason, index) => (
                  <p key={`${reason}-${index}`} className="text-xs" data-testid={`testnet-release-gate-reason-item-${index}`}>{reason}</p>
                ))}
                {(gate?.reasons || []).length === 0 && <p className="text-xs" data-testid="testnet-release-gate-reasons-empty">Reason yok.</p>}
              </div>
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="testnet-config-isolation-panel">
              <h3 className="text-lg font-bold" data-testid="testnet-config-isolation-title">Config/Secret Isolation</h3>
              <p className="text-sm" data-testid="testnet-live-endpoint-access-value">live_endpoint_access: {String(status?.live_endpoint_access ?? false)}</p>
              <p className="text-sm" data-testid="testnet-secret-isolation-pass-value">isolation_pass: {String(status?.secret_isolation?.testnet_live_secret_isolation_pass ?? false)}</p>
              <p className="text-sm" data-testid="testnet-secret-isolation-reason-value">reason: {status?.secret_isolation?.reason_code || "PASS"}</p>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="testnet-control-bottom-grid">
            <div className="border border-black/25 bg-orange-100" data-testid="testnet-preflight-checks-table-wrapper">
              <div className="border-b border-black/20 px-4 py-3" data-testid="testnet-preflight-checks-header">
                <h3 className="text-lg font-bold" data-testid="testnet-preflight-checks-title">Preflight Checks</h3>
              </div>
              <Table data-testid="testnet-preflight-checks-table">
                <TableHeader>
                  <TableRow>
                    <TableHead data-testid="testnet-preflight-head-key">Check</TableHead>
                    <TableHead data-testid="testnet-preflight-head-pass">Pass</TableHead>
                    <TableHead data-testid="testnet-preflight-head-reason">Reason</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {preflightChecks.map((item, index) => (
                    <TableRow key={`${item.key}-${index}`} data-testid={`testnet-preflight-row-${index}`}>
                      <TableCell data-testid={`testnet-preflight-key-${index}`}>{item.key}</TableCell>
                      <TableCell data-testid={`testnet-preflight-pass-${index}`}>{String(item.pass)}</TableCell>
                      <TableCell data-testid={`testnet-preflight-reason-${index}`}>{item.reason}</TableCell>
                    </TableRow>
                  ))}
                  {preflightChecks.length === 0 && (
                    <TableRow data-testid="testnet-preflight-empty-row">
                      <TableCell colSpan={3} className="text-center text-sm" data-testid="testnet-preflight-empty-text">Preflight verisi yok.</TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>

            <div className="border border-black/25 bg-orange-100" data-testid="testnet-retry-policy-table-wrapper">
              <div className="border-b border-black/20 px-4 py-3" data-testid="testnet-retry-policy-header">
                <h3 className="text-lg font-bold" data-testid="testnet-retry-policy-title">Retry Policy (Reason-aware)</h3>
              </div>
              <Table data-testid="testnet-retry-policy-table">
                <TableHeader>
                  <TableRow>
                    <TableHead data-testid="testnet-retry-head-error">Error</TableHead>
                    <TableHead data-testid="testnet-retry-head-action">Action</TableHead>
                    <TableHead data-testid="testnet-retry-head-retry">Retry</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {retryMatrix.map((item, index) => (
                    <TableRow key={`${item.error_code}-${index}`} data-testid={`testnet-retry-row-${index}`}>
                      <TableCell data-testid={`testnet-retry-error-${index}`}>{item.error_code}</TableCell>
                      <TableCell data-testid={`testnet-retry-action-${index}`}>{item.decision?.action}</TableCell>
                      <TableCell data-testid={`testnet-retry-should-retry-${index}`}>{String(item.decision?.should_retry)}</TableCell>
                    </TableRow>
                  ))}
                  {retryMatrix.length === 0 && (
                    <TableRow data-testid="testnet-retry-empty-row">
                      <TableCell colSpan={3} className="text-center text-sm" data-testid="testnet-retry-empty-text">Retry policy verisi yok.</TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-3" data-testid="testnet-analytics-grid">
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="testnet-slippage-panel">
              <h3 className="text-lg font-bold" data-testid="testnet-slippage-title">Realized Slippage</h3>
              <p className="text-sm" data-testid="testnet-slippage-expected-value">expected: {status?.slippage?.expected_slippage ?? 0}</p>
              <p className="text-sm" data-testid="testnet-slippage-realized-value">realized: {status?.slippage?.realized_slippage ?? 0}</p>
              <p className="text-sm" data-testid="testnet-slippage-delta-value">delta: {status?.slippage?.delta ?? 0}</p>
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="testnet-reconciler-panel">
              <h3 className="text-lg font-bold" data-testid="testnet-reconciler-title">Execution Reconciler</h3>
              <p className="text-sm" data-testid="testnet-reconciler-state-value">state: {status?.reconciler_state || "unknown_needs_reconcile"}</p>
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="testnet-parity-panel">
              <h3 className="text-lg font-bold" data-testid="testnet-parity-title">Paper/Testnet Parity</h3>
              <p className="text-sm" data-testid="testnet-parity-drift-value">drift_bps: {status?.parity_check?.drift_bps ?? 0}</p>
              <p className="text-sm" data-testid="testnet-parity-status-value">status: {status?.parity_check?.status || "PASS"}</p>
            </div>
          </div>
        </>
      )}
    </section>
  );
};
