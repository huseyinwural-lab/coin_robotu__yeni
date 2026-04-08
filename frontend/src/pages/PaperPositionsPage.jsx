import { Link } from "react-router-dom";

export const PaperPositionsPage = () => {
  return (
    <section className="space-y-4" data-testid="paper-positions-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="paper-positions-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="paper-positions-title">Pure Live Notice</h2>
        <p className="mt-2 text-sm text-slate-300" data-testid="paper-positions-description">
          Bu ekran Pure Live geçişi kapsamında kaldırıldı. Runtime işlemler için canlı dashboard kullanın.
        </p>
      </header>
      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="paper-positions-removed-panel">
        <Link to="/user/dashboard" className="text-sm text-cyan-300 underline" data-testid="paper-positions-removed-go-dashboard-link">
          User Dashboard'a dön
        </Link>
      </div>
    </section>
  );
};