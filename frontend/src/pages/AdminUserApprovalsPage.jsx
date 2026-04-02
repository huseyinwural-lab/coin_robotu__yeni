import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

const formatDateTime = (value) => {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString();
};

export const AdminUserApprovalsPage = () => {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(false);
  const [activeActionKey, setActiveActionKey] = useState(null);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("requested_at");
  const [sortDir, setSortDir] = useState("desc");
  const [emailSuggestions, setEmailSuggestions] = useState([]);
  const [lastFetchAt, setLastFetchAt] = useState(null);

  const loadRequests = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/admin/user-approvals", {
        params: {
          status: "pending",
          search: search || undefined,
          sort_by: sortBy,
          sort_dir: sortDir,
        },
      });
      const list = data || [];
      setRequests(list);
      setLastFetchAt(new Date().toISOString());
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Onay talepleri alınamadı");
    } finally {
      setLoading(false);
    }
  }, [search, sortBy, sortDir]);

  useEffect(() => {
    loadRequests();
  }, [loadRequests]);

  useEffect(() => {
    const timer = setTimeout(async () => {
      try {
        const { data } = await apiClient.get("/admin/user-approvals/email-suggestions", {
          params: { query: search || "", limit: 8 },
        });
        setEmailSuggestions(data?.suggestions || []);
      } catch {
        setEmailSuggestions([]);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [search]);

  const handleSingleApprove = async (userId) => {
    const confirmed = window.confirm("Kullanıcıyı onaylamak istiyor musunuz?");
    if (!confirmed) return;

    setActiveActionKey(`approve-${userId}`);
    try {
      await apiClient.post(`/auth/admin/user-approval-requests/${userId}/approve`, null);
      toast.success("Kullanıcı onaylandı");
      await loadRequests();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Approve işlemi başarısız");
    } finally {
      setActiveActionKey(null);
    }
  };

  const handleSingleReject = async (userId) => {
    const confirmed = window.confirm("Kullanıcıyı reddetmek istiyor musunuz?");
    if (!confirmed) return;

    setActiveActionKey(`reject-${userId}`);
    try {
      await apiClient.post(`/auth/admin/user-approval-requests/${userId}/reject`, null);
      toast.success("Kullanıcı reject edildi");
      await loadRequests();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Reject işlemi başarısız");
    } finally {
      setActiveActionKey(null);
    }
  };

  return (
    <section className="space-y-4" data-testid="admin-user-approvals-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="admin-user-approvals-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-black" data-testid="admin-user-approvals-title">
          Kullanıcı Onay Merkezi
        </h2>
        <p className="mt-2 text-sm text-black/70" data-testid="admin-user-approvals-description">
          Bekleyen kullanıcıları tek tık ile onaylayın veya reddedin.
        </p>
      </header>

      <div className="border border-black/30 bg-orange-100 p-4" data-testid="admin-user-approvals-toolbar">
        <div className="grid gap-2 md:grid-cols-3" data-testid="admin-user-approvals-filter-grid">
          <Input
            placeholder="Search email"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            list="admin-user-approvals-email-suggestions"
            data-testid="admin-user-approvals-search-input"
          />
          <datalist id="admin-user-approvals-email-suggestions" data-testid="admin-user-approvals-email-suggestions-list">
            {emailSuggestions.map((item, index) => (
              <option key={item} value={item} data-testid={`admin-user-approvals-email-suggestion-${index}`}>
                {item}
              </option>
            ))}
          </datalist>
          <select
            className="border border-black/40 bg-white px-3 py-2 text-sm"
            value={sortBy}
            onChange={(event) => setSortBy(event.target.value)}
            data-testid="admin-user-approvals-sort-by"
          >
            <option value="requested_at">requested_at</option>
            <option value="email">email</option>
          </select>
          <select
            className="border border-black/40 bg-white px-3 py-2 text-sm"
            value={sortDir}
            onChange={(event) => setSortDir(event.target.value)}
            data-testid="admin-user-approvals-sort-dir"
          >
            <option value="asc">asc</option>
            <option value="desc">desc</option>
          </select>
        </div>
        <div className="mt-3 flex flex-wrap gap-2" data-testid="admin-user-approvals-bulk-actions">
          <Button
            className="border border-black bg-orange-500 text-black hover:bg-orange-600"
            onClick={loadRequests}
            data-testid="admin-user-approvals-refresh-button"
          >
            Yenile
          </Button>
        </div>
        <p className="mt-2 text-sm text-black" data-testid="admin-user-approvals-count">
          Bekleyen Talep: {requests.length} · Last fetch: {lastFetchAt ? new Date(lastFetchAt).toLocaleString() : "-"}
        </p>
      </div>

      {!loading && requests.length === 0 && (
        <div className="border border-black/40 bg-orange-50 p-6" data-testid="admin-user-approvals-empty-blocking-panel">
          <p className="mt-2 text-sm text-black/80" data-testid="admin-user-approvals-empty-message">
            Bekleyen kullanıcı talebi bulunmuyor.
          </p>
          <p className="mt-2 text-xs text-black/70" data-testid="admin-user-approvals-empty-last-fetch-time">
            last_fetch_time: {lastFetchAt ? new Date(lastFetchAt).toLocaleString() : "-"}
          </p>
          <div className="mt-3 flex gap-2" data-testid="admin-user-approvals-empty-actions">
            <Button onClick={loadRequests} data-testid="admin-user-approvals-empty-retry-button">Retry</Button>
          </div>
        </div>
      )}

      {requests.length > 0 && (
        <div className="border border-black/30 bg-orange-100" data-testid="admin-user-approvals-table-wrapper">
        <Table data-testid="admin-user-approvals-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="admin-approvals-head-email">E-posta</TableHead>
              <TableHead data-testid="admin-approvals-head-status">Durum</TableHead>
              <TableHead data-testid="admin-approvals-head-requested">Talep Zamanı</TableHead>
              <TableHead data-testid="admin-approvals-head-action">Aksiyon</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {requests.map((item) => (
              <TableRow key={item.id} data-testid={`admin-approval-row-${item.id}`}>
                <TableCell data-testid={`admin-approval-email-${item.id}`}>{item.email}</TableCell>
                <TableCell data-testid={`admin-approval-status-${item.id}`}>{item.approval_status}</TableCell>
                <TableCell data-testid={`admin-approval-requested-at-${item.id}`}>
                  {formatDateTime(item.approval_requested_at)}
                </TableCell>
                <TableCell data-testid={`admin-approval-actions-${item.id}`}>
                  <div className="flex flex-wrap gap-2" data-testid={`admin-approval-actions-group-${item.id}`}>
                    <Button
                      size="sm"
                      className="border border-black bg-black text-orange-400 hover:bg-zinc-800"
                      onClick={() => handleSingleApprove(item.id)}
                      disabled={activeActionKey === `approve-${item.id}`}
                      data-testid={`admin-approval-approve-button-${item.id}`}
                    >
                      {activeActionKey === `approve-${item.id}` ? "Onaylanıyor..." : "Kabul"}
                    </Button>
                    <Button
                      size="sm"
                      className="border border-black bg-red-600 text-white hover:bg-red-700"
                      onClick={() => handleSingleReject(item.id)}
                      disabled={activeActionKey === `reject-${item.id}`}
                      data-testid={`admin-approval-reject-button-${item.id}`}
                    >
                      {activeActionKey === `reject-${item.id}` ? "Reddediliyor..." : "Reddet"}
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {!loading && requests.length === 0 && (
              <TableRow data-testid="admin-approval-empty-row">
                <TableCell colSpan={4} className="text-center text-sm text-black/70" data-testid="admin-approval-empty-text">
                  Bekleyen kullanıcı talebi bulunmuyor.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      )}
    </section>
  );
};
