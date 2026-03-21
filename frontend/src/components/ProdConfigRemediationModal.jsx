import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiClient } from "@/lib/api";

const defaultForm = {
  database_url: "",
  redis_url: "",
  admin_bootstrap_email: "",
  admin_bootstrap_password: "",
  jwt_secret: "",
};

export const ProdConfigRemediationModal = ({
  open,
  onOpenChange,
  remediationState,
  onSaved,
  testIdPrefix,
}) => {
  const [form, setForm] = useState(defaultForm);
  const [validationErrors, setValidationErrors] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!open) {
      setForm(defaultForm);
      setValidationErrors({});
    }
  }, [open]);

  const remediationItems = useMemo(() => remediationState?.remediation_items || [], [remediationState]);
  const reasonCodes = useMemo(() => remediationState?.release_gate_reason_codes || [], [remediationState]);

  const updateField = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setValidationErrors((prev) => ({ ...prev, [key]: undefined }));
  };

  const submitRemediation = async () => {
    setIsSubmitting(true);
    setValidationErrors({});
    const payload = Object.entries(form).reduce((acc, [key, value]) => {
      const normalized = String(value || "").trim();
      if (normalized) {
        acc[key] = normalized;
      }
      return acc;
    }, {});

    try {
      const { data } = await apiClient.post("/admin/system/remediate-config", payload);
      toast.success("Konfigürasyon kaydedildi, preflight yeniden çalıştı");
      onSaved?.(data);
      onOpenChange(false);
    } catch (error) {
      const details = error?.response?.data?.detail;
      const fieldErrorMap = details?.validation_errors;
      if (fieldErrorMap && typeof fieldErrorMap === "object") {
        setValidationErrors(fieldErrorMap);
      }
      toast.error(error?.response?.data?.detail?.message || "Konfigürasyon doğrulama başarısız");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl border border-red-800 bg-slate-950 text-slate-100" data-testid={`${testIdPrefix}-prod-remediation-modal`}>
        <DialogHeader>
          <DialogTitle className="text-xl text-red-300" data-testid={`${testIdPrefix}-prod-remediation-title`}>Blokajı Çöz</DialogTitle>
          <DialogDescription className="text-slate-300" data-testid={`${testIdPrefix}-prod-remediation-description`}>
            Production endpoint ve bootstrap bilgilerini gir, ardından “Kaydet ve Yeniden Doğrula”.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4" data-testid={`${testIdPrefix}-prod-remediation-content`}>
          <div className="rounded border border-red-700/60 bg-red-900/20 p-3" data-testid={`${testIdPrefix}-prod-remediation-reason-panel`}>
            <p className="text-xs uppercase tracking-wider text-red-300" data-testid={`${testIdPrefix}-prod-remediation-reason-title`}>Aktif Blokaj Reason Codes</p>
            <div className="mt-2 space-y-1" data-testid={`${testIdPrefix}-prod-remediation-reason-list`}>
              {reasonCodes.length === 0 && <p className="text-xs text-slate-300" data-testid={`${testIdPrefix}-prod-remediation-reason-empty`}>Aktif reason_code yok.</p>}
              {reasonCodes.map((item, index) => (
                <p key={`${item}-${index}`} className="font-mono text-xs text-red-200" data-testid={`${testIdPrefix}-prod-remediation-reason-item-${index}`}>{item}</p>
              ))}
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2" data-testid={`${testIdPrefix}-prod-remediation-form-grid`}>
            <div data-testid={`${testIdPrefix}-prod-remediation-database-field`}>
              <Label className="text-slate-200" data-testid={`${testIdPrefix}-prod-remediation-database-label`}>DATABASE_URL</Label>
              <Input
                value={form.database_url}
                onChange={(event) => updateField("database_url", event.target.value)}
                placeholder="postgresql+psycopg2://user:pass@prod-host:5432/db"
                className="mt-1 bg-slate-900"
                data-testid={`${testIdPrefix}-prod-remediation-database-input`}
              />
              {validationErrors.database_url && <p className="mt-1 text-xs text-red-300" data-testid={`${testIdPrefix}-prod-remediation-database-error`}>{validationErrors.database_url}</p>}
            </div>

            <div data-testid={`${testIdPrefix}-prod-remediation-redis-field`}>
              <Label className="text-slate-200" data-testid={`${testIdPrefix}-prod-remediation-redis-label`}>REDIS_URL</Label>
              <Input
                value={form.redis_url}
                onChange={(event) => updateField("redis_url", event.target.value)}
                placeholder="redis://prod-redis:6379/0"
                className="mt-1 bg-slate-900"
                data-testid={`${testIdPrefix}-prod-remediation-redis-input`}
              />
              {validationErrors.redis_url && <p className="mt-1 text-xs text-red-300" data-testid={`${testIdPrefix}-prod-remediation-redis-error`}>{validationErrors.redis_url}</p>}
            </div>

            <div data-testid={`${testIdPrefix}-prod-remediation-admin-email-field`}>
              <Label className="text-slate-200" data-testid={`${testIdPrefix}-prod-remediation-admin-email-label`}>ADMIN_BOOTSTRAP_EMAIL</Label>
              <Input
                value={form.admin_bootstrap_email}
                onChange={(event) => updateField("admin_bootstrap_email", event.target.value)}
                placeholder="admin@your-domain.com"
                className="mt-1 bg-slate-900"
                data-testid={`${testIdPrefix}-prod-remediation-admin-email-input`}
              />
              {validationErrors.admin_bootstrap_email && <p className="mt-1 text-xs text-red-300" data-testid={`${testIdPrefix}-prod-remediation-admin-email-error`}>{validationErrors.admin_bootstrap_email}</p>}
            </div>

            <div data-testid={`${testIdPrefix}-prod-remediation-admin-password-field`}>
              <Label className="text-slate-200" data-testid={`${testIdPrefix}-prod-remediation-admin-password-label`}>ADMIN_BOOTSTRAP_PASSWORD</Label>
              <Input
                type="password"
                value={form.admin_bootstrap_password}
                onChange={(event) => updateField("admin_bootstrap_password", event.target.value)}
                placeholder="minimum 10 karakter"
                className="mt-1 bg-slate-900"
                data-testid={`${testIdPrefix}-prod-remediation-admin-password-input`}
              />
              {validationErrors.admin_bootstrap_password && <p className="mt-1 text-xs text-red-300" data-testid={`${testIdPrefix}-prod-remediation-admin-password-error`}>{validationErrors.admin_bootstrap_password}</p>}
            </div>

            <div className="md:col-span-2" data-testid={`${testIdPrefix}-prod-remediation-jwt-field`}>
              <Label className="text-slate-200" data-testid={`${testIdPrefix}-prod-remediation-jwt-label`}>JWT_SECRET (opsiyonel güncelleme)</Label>
              <Input
                type="password"
                value={form.jwt_secret}
                onChange={(event) => updateField("jwt_secret", event.target.value)}
                placeholder="minimum 32 karakter"
                className="mt-1 bg-slate-900"
                data-testid={`${testIdPrefix}-prod-remediation-jwt-input`}
              />
              {validationErrors.jwt_secret && <p className="mt-1 text-xs text-red-300" data-testid={`${testIdPrefix}-prod-remediation-jwt-error`}>{validationErrors.jwt_secret}</p>}
            </div>
          </div>

          <div className="rounded border border-slate-700 bg-slate-900/70 p-3" data-testid={`${testIdPrefix}-prod-remediation-item-panel`}>
            <p className="text-xs uppercase tracking-wider text-slate-300" data-testid={`${testIdPrefix}-prod-remediation-item-title`}>Remediation Checklist</p>
            <div className="mt-2 space-y-1" data-testid={`${testIdPrefix}-prod-remediation-item-list`}>
              {remediationItems.length === 0 && <p className="text-xs text-slate-400" data-testid={`${testIdPrefix}-prod-remediation-item-empty`}>Açık remediation maddesi yok.</p>}
              {remediationItems.map((item, index) => (
                <p key={`${item.code}-${index}`} className="text-xs text-slate-200" data-testid={`${testIdPrefix}-prod-remediation-item-${index}`}>
                  {item.title} {item.target_field ? `(${item.target_field})` : ""}
                </p>
              ))}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            data-testid={`${testIdPrefix}-prod-remediation-cancel-button`}
          >
            Vazgeç
          </Button>
          <Button
            className="bg-red-600 text-white hover:bg-red-700"
            onClick={submitRemediation}
            disabled={isSubmitting}
            data-testid={`${testIdPrefix}-prod-remediation-save-button`}
          >
            {isSubmitting ? "Kaydediliyor..." : "Kaydet ve Yeniden Doğrula"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
