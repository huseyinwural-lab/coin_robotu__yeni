import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

export const AdminUserApprovalsPage = () => {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("requested_at");
  const [sortDir, setSortDir] = useState("asc");
  const [selectedIds, setSelectedIds] = useState([]);
  const [rejectReason, setRejectReason] = useState("");

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
      setRequests(data);
      setSelectedIds((prev) => prev.filter((id) => data.some((item) => item.id === id)));
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Onay talepleri alınamadı");
    } finally {
      setLoading(false);
    }
  }, [search, sortBy, sortDir]);

  useEffect(() => {
    loadRequests();
  }, [loadRequests]);

  const allSelected = useMemo(
    () => requests.length > 0 && selectedIds.length === requests.length,
    [requests, selectedIds],
  );

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelectedIds([]);
    } else {
      setSelectedIds(requests.map((item) => item.id));
    }
  };

  const toggleSelection = (userId) => {
    setSelectedIds((prev) => (prev.includes(userId) ? prev.filter((id) => id !== userId) : [...prev, userId]));
  };

  const handleBulkApprove = async () => {
    if (selectedIds.length === 0) {
      toast.error("En az bir kullanıcı seçin");
      return;
    }
    try {
      await apiClient.post("/admin/user-approvals/bulk-approve", { ids: selectedIds });
      toast.success("Seçili kullanıcılar onaylandı");
      setSelectedIds([]);
      loadRequests();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bulk approve başarısız");
    }
  };

  const handleBulkReject = async () => {
    if (selectedIds.length === 0) {
      toast.error("En az bir kullanıcı seçin");
      return;
    }
    if (!rejectReason.trim()) {
      toast.error("Reject reason zorunlu");
      return;
    }
    try {
      await apiClient.post("/admin/user-approvals/bulk-reject", { ids: selectedIds, reason: rejectReason });
      toast.success("Seçili kullanıcılar reddedildi");
      setSelectedIds([]);
      setRejectReason("");
      loadRequests();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bulk reject başarısız");
    }
  };

  const handleSingleApprove = async (userId) => {
    try {
      await apiClient.post("/admin/user-approvals/bulk-approve", { ids: [userId] });
      toast.success("Kullanıcı onaylandı");
      loadRequests();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Onay işlemi başarısız");
    }
  };

  const handleSingleReject = async (userId) => {
    const reason = rejectReason.trim() || "manual_reject";
    try {
      await apiClient.post("/admin/user-approvals/bulk-reject", { ids: [userId], reason });
      toast.success("Kullanıcı reddedildi");
      loadRequests();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Reddetme işlemi başarısız");
    }
  };

  return (
    <section className="space-y-4" data-testid="admin-user-approvals-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="admin-user-approvals-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-black" data-testid="admin-user-approvals-title">
          Kullanıcı Onay Merkezi
        </h2>
        <p className="mt-2 text-sm text-black/70" data-testid="admin-user-approvals-description">
          Yeni kayıt olan kullanıcılar burada bekler. Onay sonrası user panel girişine izin verilir.
        </p>
      </header>

      <div className="border border-black/30 bg-orange-100 p-4" data-testid="admin-user-approvals-toolbar">
        <div className="grid gap-2 md:grid-cols-3" data-testid="admin-user-approvals-filter-grid">
          <Input
            placeholder="Search email"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            data-testid="admin-user-approvals-search-input"
          />
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
          <Button
            className="border border-black bg-black text-orange-400 hover:bg-zinc-800"
            onClick={handleBulkApprove}
            data-testid="admin-user-approvals-bulk-approve-button"
          >
            Bulk Approve
          </Button>
          <Button
            className="border border-black bg-red-600 text-white hover:bg-red-700"
            onClick={handleBulkReject}
            data-testid="admin-user-approvals-bulk-reject-button"
          >
            Bulk Reject
          </Button>
          <Input
            placeholder="Reject reason (zorunlu)"
            value={rejectReason}
            onChange={(event) => setRejectReason(event.target.value)}
            className="max-w-[320px]"
            data-testid="admin-user-approvals-reject-reason-input"
          />
        </div>
        <p className="mt-2 text-sm text-black" data-testid="admin-user-approvals-count">
          Bekleyen Talep: {requests.length} · Seçili: {selectedIds.length}
        </p>
      </div>

      <div className="border border-black/30 bg-orange-100" data-testid="admin-user-approvals-table-wrapper">
        <Table data-testid="admin-user-approvals-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="admin-approvals-head-select">
                <Checkbox
                  checked={allSelected}
                  onCheckedChange={toggleSelectAll}
                  data-testid="admin-approvals-select-all"
                />
              </TableHead>
              <TableHead data-testid="admin-approvals-head-email">E-posta</TableHead>
              <TableHead data-testid="admin-approvals-head-status">Durum</TableHead>
              <TableHead data-testid="admin-approvals-head-requested">Talep Zamanı</TableHead>
              <TableHead data-testid="admin-approvals-head-action">Aksiyon</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {requests.map((item) => (
              <TableRow key={item.id} data-testid={`admin-approval-row-${item.id}`}>
                <TableCell data-testid={`admin-approval-select-${item.id}`}>
                  <Checkbox
                    checked={selectedIds.includes(item.id)}
                    onCheckedChange={() => toggleSelection(item.id)}
                    data-testid={`admin-approval-checkbox-${item.id}`}
                  />
                </TableCell>
                <TableCell data-testid={`admin-approval-email-${item.id}`}>{item.email}</TableCell>
                <TableCell data-testid={`admin-approval-status-${item.id}`}>{item.approval_status}</TableCell>
                <TableCell data-testid={`admin-approval-requested-at-${item.id}`}>
                  {new Date(item.approval_requested_at).toLocaleString()}
                </TableCell>
                <TableCell data-testid={`admin-approval-actions-${item.id}`}>
                  <div className="flex flex-wrap gap-2" data-testid={`admin-approval-action-buttons-${item.id}`}>
                    <Button
                      size="sm"
                      className="border border-black bg-black text-orange-400 hover:bg-zinc-800"
                      onClick={() => handleSingleApprove(item.id)}
                      data-testid={`admin-approval-approve-button-${item.id}`}
                    >
                      Approve
                    </Button>
                    <Button
                      size="sm"
                      className="border border-black bg-red-600 text-white hover:bg-red-700"
                      onClick={() => handleSingleReject(item.id)}
                      data-testid={`admin-approval-reject-button-${item.id}`}
                    >
                      Reject
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {!loading && requests.length === 0 && (
              <TableRow data-testid="admin-approval-empty-row">
                <TableCell colSpan={5} className="text-center text-sm text-black/70" data-testid="admin-approval-empty-text">
                  Bekleyen kullanıcı talebi bulunmuyor.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </section>
  );
};
