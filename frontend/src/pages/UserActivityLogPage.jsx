import { useEffect, useState } from "react";
import { toast } from "sonner";

import { apiClient } from "@/lib/api";

export const UserActivityLogPage = () => {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const { data } = await apiClient.get("/user/activity-log", { params: { limit: 100 } });
        setRows(data || []);
      } catch (error) {
        toast.error(error?.response?.data?.detail || "Activity log yüklenemedi");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  return (
    <section className="space-y-4" data-testid="user-activity-log-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="user-activity-log-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-activity-log-title">Activity & Audit</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-activity-log-description">İşlem, karar ve risk müdahaleleri kullanıcı görünürlüğüyle listelenir.</p>
      </header>
      <div className="overflow-x-auto border border-slate-800 bg-slate-900" data-testid="user-activity-log-table-wrapper">
        <table className="min-w-full text-sm" data-testid="user-activity-log-table">
          <thead>
            <tr className="text-left text-slate-400"><th className="px-2 py-2">Time</th><th className="px-2 py-2">Action</th><th className="px-2 py-2">Entity</th><th className="px-2 py-2">Severity</th><th className="px-2 py-2">Details</th></tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr key={row.id} className="border-t border-slate-800 align-top" data-testid={`user-activity-log-row-${idx}`}>
                <td className="px-2 py-2 font-mono">{String(row.created_at || "-")}</td>
                <td className="px-2 py-2">{row.action}</td>
                <td className="px-2 py-2">{row.entity_type}:{row.entity_id}</td>
                <td className="px-2 py-2">{row.severity}</td>
                <td className="px-2 py-2"><pre className="max-w-[380px] overflow-x-auto bg-slate-50 p-2 text-[11px] text-slate-700">{JSON.stringify(row.details || {}, null, 2)}</pre></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {loading && <p className="text-xs text-slate-500" data-testid="user-activity-log-loading-state">loading...</p>}
    </section>
  );
};
