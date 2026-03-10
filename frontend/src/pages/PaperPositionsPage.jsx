import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

export const PaperPositionsPage = () => {
  const [positions, setPositions] = useState([]);

  const fetchPositions = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/paper-positions");
      setPositions(data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Pozisyonlar yüklenemedi");
    }
  }, []);

  useEffect(() => {
    fetchPositions();
    const timer = setInterval(fetchPositions, 5000);
    return () => clearInterval(timer);
  }, [fetchPositions]);

  const manualClose = async (positionId) => {
    try {
      await apiClient.post(`/paper-positions/${positionId}/manual-close`, { reason: "manual_close" });
      toast.success("Pozisyon manuel kapatıldı");
      fetchPositions();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Pozisyon kapatılamadı");
    }
  };

  return (
    <section className="space-y-4" data-testid="paper-positions-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="paper-positions-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="paper-positions-title">Paper Position Engine</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="paper-positions-description">Açık/kapalı pozisyonlar, unrealized-realized PnL ve manuel close.</p>
      </header>

      <div className="border border-slate-800 bg-slate-900" data-testid="paper-positions-table-wrapper">
        <Table data-testid="paper-positions-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="positions-table-head-symbol">Symbol</TableHead>
              <TableHead data-testid="positions-table-head-side">Side</TableHead>
              <TableHead data-testid="positions-table-head-entry">Entry</TableHead>
              <TableHead data-testid="positions-table-head-pnl">PnL</TableHead>
              <TableHead data-testid="positions-table-head-status">Status</TableHead>
              <TableHead data-testid="positions-table-head-action">Aksiyon</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {positions.map((position) => (
              <TableRow key={position.id} data-testid={`position-row-${position.id}`}>
                <TableCell data-testid={`position-symbol-${position.id}`}>{position.symbol}</TableCell>
                <TableCell data-testid={`position-side-${position.id}`}>{position.side}</TableCell>
                <TableCell className="font-mono" data-testid={`position-entry-${position.id}`}>{position.entry_price}</TableCell>
                <TableCell className="font-mono" data-testid={`position-pnl-${position.id}`}>
                  U:{position.unrealized_pnl} / R:{position.realized_pnl}
                </TableCell>
                <TableCell data-testid={`position-status-${position.id}`}>{position.status}</TableCell>
                <TableCell>
                  {position.status === "open" ? (
                    <Button
                      size="sm"
                      variant="outline"
                      className="border-red-400 bg-transparent text-red-300"
                      onClick={() => manualClose(position.id)}
                      data-testid={`position-manual-close-${position.id}`}
                    >
                      Manual Close
                    </Button>
                  ) : (
                    <span className="text-xs text-slate-500" data-testid={`position-closed-tag-${position.id}`}>Closed</span>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  );
};