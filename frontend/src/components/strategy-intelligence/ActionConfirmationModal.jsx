import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export const ActionConfirmationModal = ({
  open,
  onOpenChange,
  onConfirm,
  isSubmitting,
  title,
  description,
  details = [],
}) => {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="border border-slate-700 bg-slate-950" data-testid="strategy-intelligence-confirm-modal">
        <DialogHeader>
          <DialogTitle data-testid="strategy-intelligence-confirm-modal-title">{title}</DialogTitle>
          <DialogDescription data-testid="strategy-intelligence-confirm-modal-description">{description}</DialogDescription>
        </DialogHeader>

        <div className="space-y-1" data-testid="strategy-intelligence-confirm-modal-details">
          {details.map((item, index) => (
            <p key={`${item.label}-${index}`} className="text-xs text-slate-300" data-testid={`strategy-intelligence-confirm-modal-detail-${index}`}>
              {item.label}: {item.value}
            </p>
          ))}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isSubmitting}
            data-testid="strategy-intelligence-confirm-modal-cancel-button"
          >
            Vazgeç
          </Button>
          <Button
            onClick={onConfirm}
            disabled={isSubmitting}
            className="border border-rose-500 bg-rose-700 text-white"
            data-testid="strategy-intelligence-confirm-modal-confirm-button"
          >
            {isSubmitting ? "Uygulanıyor..." : "Onayla ve Uygula"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
