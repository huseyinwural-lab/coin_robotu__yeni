import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

const backendBase = process.env.REACT_APP_BACKEND_URL;

export const AdminBrandSettingsPage = () => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [appName, setAppName] = useState("");
  const [logoUrl, setLogoUrl] = useState(null);
  const [updatedAt, setUpdatedAt] = useState(null);

  const effectiveLogoUrl = useMemo(() => {
    if (!logoUrl) {
      return "/xilo-logo.png";
    }
    if (String(logoUrl).startsWith("http")) {
      return logoUrl;
    }
    const cacheBuster = updatedAt ? `?v=${encodeURIComponent(updatedAt)}` : "";
    return `${backendBase}${logoUrl}${cacheBuster}`;
  }, [logoUrl, updatedAt]);

  const loadSettings = async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/admin/brand-settings");
      setAppName(data?.app_name || "");
      setLogoUrl(data?.logo_url || null);
      setUpdatedAt(data?.updated_at || null);
    } catch {
      toast.error("Brand ayarları alınamadı");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const saveAppName = async () => {
    setSaving(true);
    try {
      const { data } = await apiClient.put("/admin/brand-settings", { app_name: appName });
      setAppName(data?.app_name || appName);
      setLogoUrl(data?.logo_url || null);
      setUpdatedAt(data?.updated_at || null);
      toast.success("Brand ismi güncellendi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Brand ismi güncellenemedi");
    } finally {
      setSaving(false);
    }
  };

  const uploadLogo = async (event) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    const formData = new FormData();
    formData.append("file", file);

    setUploading(true);
    try {
      const { data } = await apiClient.post("/admin/brand-settings/logo-upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setLogoUrl(data?.logo_url || null);
      setUpdatedAt(data?.updated_at || null);
      toast.success("Logo kaydedildi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Logo yüklenemedi");
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  };

  if (loading) {
    return (
      <section className="border border-slate-800 bg-slate-900 p-4" data-testid="admin-brand-settings-loading-state">
        <p className="text-sm text-slate-300" data-testid="admin-brand-settings-loading-text">Brand ayarları yükleniyor...</p>
      </section>
    );
  }

  return (
    <section className="space-y-4" data-testid="admin-brand-settings-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="admin-brand-settings-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="admin-brand-settings-title">Brand Settings</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="admin-brand-settings-description">Logo ve uygulama adını kalıcı olarak yönet.</p>
      </header>

      <div className="grid gap-4 lg:grid-cols-2" data-testid="admin-brand-settings-grid">
        <section className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-brand-settings-form-card">
          <label className="space-y-1" data-testid="admin-brand-settings-app-name-field">
            <span className="text-xs uppercase tracking-widest text-slate-400" data-testid="admin-brand-settings-app-name-label">App Name</span>
            <Input value={appName} onChange={(event) => setAppName(event.target.value)} data-testid="admin-brand-settings-app-name-input" />
          </label>

          <div className="space-y-2" data-testid="admin-brand-settings-upload-field">
            <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="admin-brand-settings-upload-label">Logo Upload (png/jpeg/webp)</p>
            <Input type="file" accept="image/png,image/jpeg,image/webp" onChange={uploadLogo} data-testid="admin-brand-settings-logo-upload-input" />
            <p className="text-xs text-slate-500" data-testid="admin-brand-settings-upload-hint">Maksimum 2MB.</p>
          </div>

          <Button type="button" onClick={saveAppName} disabled={saving || uploading} data-testid="admin-brand-settings-save-button">
            {saving ? "Kaydediliyor..." : "Brand Ayarlarını Kaydet"}
          </Button>
          {uploading && <p className="text-xs text-cyan-300" data-testid="admin-brand-settings-uploading-text">Logo yükleniyor...</p>}
        </section>

        <section className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-brand-settings-preview-card">
          <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="admin-brand-settings-preview-title">Preview</p>
          <div className="rounded border border-slate-700 bg-white p-3" data-testid="admin-brand-settings-preview-logo-wrap">
            <img src={effectiveLogoUrl} alt="Brand logo preview" className="h-auto w-[220px]" data-testid="admin-brand-settings-preview-logo" />
          </div>
          <p className="text-sm text-slate-200" data-testid="admin-brand-settings-preview-app-name">{appName || "-"}</p>
          <p className="text-xs text-slate-500" data-testid="admin-brand-settings-preview-updated-at">updated_at: {updatedAt || "-"}</p>
        </section>
      </div>
    </section>
  );
};
