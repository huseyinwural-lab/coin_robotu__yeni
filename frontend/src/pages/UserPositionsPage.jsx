import { useEffect, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

export const UserPositionsPage = () => {
  const [rows, setRows] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [busyAction, setBusyAction] = useState("");
  const [partialSize, setPartialSize] = useState({});
  const [reverseSize, setReverseSize] = useState({});
  const [stopPrice, setStopPrice] = useState({});
  const [takeProfitPrice, setTakeProfitPrice] = useState({});

  const load = async () => {
    setIsLoading(true);
    try {
      const { data } = await apiClient.get("/user/execution/positions", { params: { include_closed: false } });
      setRows(data || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Pozisyonlar yüklenemedi");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const runPositionAction = async (row, intentType, overrides = {}) => {
    const key = `${intentType}-${row.position_id}`;
    setBusyAction(key);
    try {
      const payload = {
        intent_type: intentType,
        position_id: row.position_id,
        symbol: row.symbol,
        size: Number(overrides.size ?? row.size),
        reduce_only: overrides.reduce_only ?? true,
        price: overrides.price ?? null,
        stop_price: overrides.stop_price ?? null,
        take_profit_price: overrides.take_profit_price ?? null,
      };
      const preview = await apiClient.post("/user/execution/position-actions/preview", payload);
      if (preview.data?.validation_status !== "valid") {
        toast.error((preview.data?.reject_reason_codes || []).join(", ") || "Action preview başarısız");
        return;
      }

      await apiClient.post("/user/execution/position-actions/submit", {
        intent_token: preview.data.intent_token,
        preview_hash: preview.data.preview_hash,
      });
      toast.success(`${intentType} intent kuyruğa alındı`);
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || `${intentType} işlemi başarısız`);
    } finally {
      setBusyAction("");
    }
  };

  if (isLoading) {
    return <LoadingSkeleton rows={8} testId="user-positions-loading-skeleton" />;
  }

  return (
    <section className="grid grid-cols-12 gap-4" data-testid="user-positions-page">
      <header className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="user-positions-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-positions-title">Positions</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-positions-description">Open pozisyon yönetimi: close, partial close, reverse, stop/tp güncelleme.</p>
      </header>

      <div className="col-span-12 overflow-x-auto border border-slate-800 bg-slate-900" data-testid="user-positions-table-wrapper">
        <table className="min-w-full text-sm" data-testid="user-positions-table">
          <thead className="bg-slate-800 text-left" data-testid="user-positions-table-head">
            <tr>
              <th className="px-3 py-2">Symbol</th>
              <th className="px-3 py-2">Size</th>
              <th className="px-3 py-2">Entry</th>
              <th className="px-3 py-2">Current</th>
              <th className="px-3 py-2">Unrealized PnL</th>
              <th className="px-3 py-2">Leverage</th>
              <th className="px-3 py-2">Strategy</th>
              <th className="px-3 py-2">Cluster</th>
              <th className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody data-testid="user-positions-table-body">
            {rows.map((row) => (
              <tr key={row.position_id} className="border-t border-slate-800" data-testid={`user-positions-row-${row.position_id}`}>
                <td className="px-3 py-2" data-testid={`user-positions-symbol-${row.position_id}`}>{row.symbol}</td>
                <td className="px-3 py-2" data-testid={`user-positions-size-${row.position_id}`}>{row.size}</td>
                <td className="px-3 py-2" data-testid={`user-positions-entry-${row.position_id}`}>{row.entry_price}</td>
                <td className="px-3 py-2" data-testid={`user-positions-current-${row.position_id}`}>{row.current_price}</td>
                <td className="px-3 py-2" data-testid={`user-positions-unrealized-${row.position_id}`}>{row.unrealized_pnl}</td>
                <td className="px-3 py-2" data-testid={`user-positions-leverage-${row.position_id}`}>{row.leverage}</td>
                <td className="px-3 py-2" data-testid={`user-positions-strategy-${row.position_id}`}>{row.strategy_id || "-"}</td>
                <td className="px-3 py-2" data-testid={`user-positions-cluster-${row.position_id}`}>{row.cluster_id || "UNCLUSTERED"}</td>
                <td className="px-3 py-2">
                  <div className="grid gap-2" data-testid={`user-positions-actions-${row.position_id}`}>
                    <div className="flex flex-wrap gap-2" data-testid={`user-positions-primary-actions-${row.position_id}`}>
                      <Button
                        className="bg-rose-500 text-white hover:bg-rose-400"
                        disabled={busyAction === `CLOSE_POSITION-${row.position_id}`}
                        onClick={() => runPositionAction(row, "CLOSE_POSITION", { size: row.size, reduce_only: true })}
                        data-testid={`user-positions-close-button-${row.position_id}`}
                      >
                        Close
                      </Button>

                      <Input
                        className="w-24"
                        type="number"
                        value={partialSize[row.position_id] ?? Math.max(Number(row.size) / 2, 0.001)}
                        onChange={(event) => setPartialSize((prev) => ({ ...prev, [row.position_id]: event.target.value }))}
                        data-testid={`user-positions-partial-size-input-${row.position_id}`}
                      />
                      <Button
                        variant="outline"
                        disabled={busyAction === `PARTIAL_CLOSE-${row.position_id}`}
                        onClick={() =>
                          runPositionAction(row, "PARTIAL_CLOSE", {
                            size: Number(partialSize[row.position_id] ?? Math.max(Number(row.size) / 2, 0.001)),
                            reduce_only: true,
                          })
                        }
                        data-testid={`user-positions-partial-close-button-${row.position_id}`}
                      >
                        Partial Close
                      </Button>

                      <Input
                        className="w-24"
                        type="number"
                        value={reverseSize[row.position_id] ?? row.size}
                        onChange={(event) => setReverseSize((prev) => ({ ...prev, [row.position_id]: event.target.value }))}
                        data-testid={`user-positions-reverse-size-input-${row.position_id}`}
                      />
                      <Button
                        variant="outline"
                        disabled={busyAction === `REVERSE_POSITION-${row.position_id}`}
                        onClick={() =>
                          runPositionAction(row, "REVERSE_POSITION", {
                            size: Number(reverseSize[row.position_id] ?? row.size),
                            reduce_only: false,
                          })
                        }
                        data-testid={`user-positions-reverse-button-${row.position_id}`}
                      >
                        Reverse
                      </Button>
                    </div>

                    <div className="flex flex-wrap gap-2" data-testid={`user-positions-risk-actions-${row.position_id}`}>
                      <Input
                        className="w-28"
                        type="number"
                        value={stopPrice[row.position_id] ?? ""}
                        placeholder="stop"
                        onChange={(event) => setStopPrice((prev) => ({ ...prev, [row.position_id]: event.target.value }))}
                        data-testid={`user-positions-stop-input-${row.position_id}`}
                      />
                      <Button
                        variant="outline"
                        disabled={busyAction === `MOVE_STOP-${row.position_id}`}
                        onClick={() =>
                          runPositionAction(row, "MOVE_STOP", {
                            size: Number(row.size),
                            stop_price: Number(stopPrice[row.position_id]),
                            reduce_only: true,
                          })
                        }
                        data-testid={`user-positions-move-stop-button-${row.position_id}`}
                      >
                        Edit Stop
                      </Button>

                      <Input
                        className="w-28"
                        type="number"
                        value={takeProfitPrice[row.position_id] ?? ""}
                        placeholder="take profit"
                        onChange={(event) => setTakeProfitPrice((prev) => ({ ...prev, [row.position_id]: event.target.value }))}
                        data-testid={`user-positions-tp-input-${row.position_id}`}
                      />
                      <Button
                        variant="outline"
                        disabled={busyAction === `MOVE_TAKE_PROFIT-${row.position_id}`}
                        onClick={() =>
                          runPositionAction(row, "MOVE_TAKE_PROFIT", {
                            size: Number(row.size),
                            take_profit_price: Number(takeProfitPrice[row.position_id]),
                            reduce_only: true,
                          })
                        }
                        data-testid={`user-positions-move-tp-button-${row.position_id}`}
                      >
                        Edit Take Profit
                      </Button>
                    </div>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
};
