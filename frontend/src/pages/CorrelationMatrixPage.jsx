import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const CorrelationMatrixPage = () => {
  const [windowSize, setWindowSize] = useState(200);
  const [payload, setPayload] = useState(null);

  const loadMatrix = async (nextWindow = windowSize) => {
    try {
      const { data } = await apiClient.get(`/admin-phase3/correlation-matrix?window=${nextWindow}`);
      setPayload(data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Correlation matrix alınamadı");
    }
  };

  useEffect(() => {
    loadMatrix(200);
  }, []);

  return (
    <section className="space-y-4" data-testid="correlation-matrix-page">
      <header className="border border-blue-900 bg-slate-900 p-4" data-testid="correlation-matrix-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-blue-300" data-testid="correlation-matrix-title">Correlation Matrix</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="correlation-matrix-description">
          Hibrit model: statik gruplar + rolling correlation window.
        </p>
        <div className="mt-3 flex flex-wrap gap-2" data-testid="correlation-matrix-controls">
          {[120, 200, 300].map((size) => (
            <Button
              key={size}
              type="button"
              variant="outline"
              className="border-slate-700 bg-transparent"
              onClick={() => {
                setWindowSize(size);
                loadMatrix(size);
              }}
              data-testid={`correlation-window-${size}-button`}
            >
              Window {size}
            </Button>
          ))}
        </div>
      </header>

      <div className="overflow-auto border border-slate-800 bg-slate-900 p-3" data-testid="correlation-matrix-table-wrapper">
        <table className="min-w-full border-collapse text-xs" data-testid="correlation-matrix-table">
          <thead>
            <tr>
              <th className="border border-slate-700 px-2 py-1" data-testid="correlation-head-symbol">Symbol</th>
              {(payload?.symbols || []).map((symbol) => (
                <th key={symbol} className="border border-slate-700 px-2 py-1" data-testid={`correlation-head-${symbol}`}>
                  {symbol}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(payload?.symbols || []).map((base) => (
              <tr key={base} data-testid={`correlation-row-${base}`}>
                <td className="border border-slate-700 px-2 py-1 font-semibold" data-testid={`correlation-row-label-${base}`}>
                  {base}
                </td>
                {(payload?.symbols || []).map((compare) => {
                  const value = payload?.matrix?.[base]?.[compare] ?? 0;
                  const highlight = Math.abs(value) >= 0.75 ? "bg-red-900/30" : "";
                  return (
                    <td
                      key={`${base}-${compare}`}
                      className={`border border-slate-700 px-2 py-1 font-mono ${highlight}`}
                      data-testid={`correlation-cell-${base}-${compare}`}
                    >
                      {value}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
};
