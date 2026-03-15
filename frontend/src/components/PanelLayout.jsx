import {
  Activity,
  BarChart3,
  BarChartBig,
  ClipboardList,
  FileText,
  Gauge,
  Globe,
  KeyRound,
  LineChart,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Radio,
  Settings2,
  ShieldAlert,
  TrendingUp,
  UserCog,
  Wrench,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

const userNavItems = [
  { to: "/user/dashboard", label: "User Dashboard", icon: BarChart3, testId: "nav-user-dashboard-link" },
  { to: "/user/exchange-settings", label: "Exchange Settings", icon: KeyRound, testId: "nav-user-exchange-settings-link" },
  { to: "/user/risk-policy", label: "Risk Policy", icon: ShieldAlert, testId: "nav-risk-policies-link" },
  { to: "/user/bot-profiles", label: "Bot Profilleri", icon: TrendingUp, testId: "nav-bot-profiles-link" },
  { to: "/user/scanner", label: "Scanner", icon: Gauge, testId: "nav-user-scanner-link" },
  { to: "/user/signals", label: "Signals", icon: Radio, testId: "nav-user-signals-link" },
  { to: "/user/trades", label: "Trades", icon: Activity, testId: "nav-user-trades-link" },
  { to: "/user/positions", label: "Positions", icon: Activity, testId: "nav-user-positions-link" },
  { to: "/user/strategies", label: "Strategy Template", icon: ClipboardList, testId: "nav-strategy-templates-link" },
  { to: "/user/indicator-screener", label: "Indicator Screener", icon: LineChart, testId: "nav-user-indicator-screener-link" },
  { to: "/user/portfolio", label: "Portfolio", icon: BarChartBig, testId: "nav-user-portfolio-link" },
  { to: "/user/reports", label: "Reports", icon: FileText, testId: "nav-user-reports-link" },
  { to: "/user/execute", label: "Execute", icon: Wrench, testId: "nav-user-execute-link" },
  { to: "/user/paper-positions", label: "Paper Positions", icon: Activity, testId: "nav-paper-positions-link" },
  { to: "/user/backtest-insights", label: "Backtest Insights", icon: LineChart, testId: "nav-backtest-insights-link" },
];

const adminOnlyItems = [
  { to: "/admin/dashboard", label: "Dashboard", icon: UserCog, testId: "nav-admin-dashboard-link" },
  { to: "/admin/monitoring", label: "System Status", icon: Activity, testId: "nav-admin-system-status-link" },
  { to: "/admin/universe-monitor", label: "Scanner Monitor", icon: Gauge, testId: "nav-admin-scanner-monitor-link" },
  { to: "/admin/futures/strategy-analytics", label: "Strategy Analytics", icon: BarChart3, testId: "nav-admin-strategy-analytics-link" },
  { to: "/admin/risk-orchestrator", label: "Risk Engine", icon: ShieldAlert, testId: "nav-admin-risk-engine-link" },
  { to: "/admin/execution-queue", label: "Execution Monitor", icon: Wrench, testId: "nav-admin-execution-monitor-link" },
  { to: "/admin/users/customers", label: "Users", icon: UserCog, testId: "nav-admin-users-link" },
  { to: "/admin/strategies", label: "Bots", icon: ClipboardList, testId: "nav-admin-bots-link" },
  { to: "/admin/exchanges", label: "Exchange Settings", icon: Globe, testId: "nav-admin-exchange-settings-link" },
  { to: "/admin/execution-policies", label: "System Config", icon: Settings2, testId: "nav-admin-system-config-link" },
  { to: "/admin/audit-logs", label: "Logs", icon: FileText, testId: "nav-admin-logs-link" },
];

export const PanelLayout = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const adminRoles = new Set(["super_admin", "admin", "ops"]);
  const [gateBadge, setGateBadge] = useState(null);
  const [nowTick, setNowTick] = useState(Date.now());
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const isAdmin = adminRoles.has(user?.role);
  const navItems = isAdmin ? adminOnlyItems : userNavItems;
  const roleThemeClass = isAdmin ? "admin-ops-theme" : "user-theme";
  const sidebarClass = isAdmin ? "border-orange-700 bg-orange-300" : "border-slate-800 bg-slate-900";
  const brandTitleClass = isAdmin ? "text-black" : "text-orange-500";
  const activeNavClass = isAdmin
    ? "border-black bg-orange-400 text-black"
    : "border-orange-500 bg-slate-800 text-orange-400";
  const logoutButtonClass = isAdmin
    ? "border-black bg-[#4CAF50] text-white hover:bg-[#43a047]"
    : "border-slate-700 bg-transparent text-slate-200 hover:border-orange-500 hover:text-orange-500";

  useEffect(() => {
    if (!isAdmin) {
      setGateBadge(null);
      return;
    }

    const fetchGate = async () => {
      try {
        const { data } = await apiClient.get("/phase4/admin/release-gate?environment=prod");
        setGateBadge(data);
      } catch {
        setGateBadge(null);
      }
    };

    fetchGate();
    const timer = setInterval(fetchGate, 15000);
    return () => clearInterval(timer);
  }, [isAdmin]);

  useEffect(() => {
    if (!isAdmin) {
      return;
    }
    const timer = setInterval(() => setNowTick(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [isAdmin]);

  const countdownLabel = useMemo(() => {
    if (!gateBadge?.override_active || !gateBadge?.override_expires_at) {
      return "";
    }
    const ms = new Date(gateBadge.override_expires_at).getTime() - Date.now();
    if (ms <= 0) {
      return "expired";
    }
    const min = Math.floor(ms / 60000);
    const sec = Math.floor((ms % 60000) / 1000);
    return `expires in ${min}m ${sec}s`;
  }, [gateBadge, nowTick]);

  return (
    <div className={`${roleThemeClass} h-screen overflow-hidden bg-slate-950 text-slate-100`} data-testid="panel-layout-wrapper">
      <div className="sticky top-0 z-40 flex items-center justify-between gap-3 border-b border-emerald-300 bg-emerald-100/95 px-4 py-3 text-slate-900 backdrop-blur" data-testid="panel-sticky-header" aria-label="Panel üst navigasyon">
        <div className="flex items-center gap-2" data-testid="panel-sticky-header-left">
          <Button
            type="button"
            variant="outline"
            className="md:hidden"
            onClick={() => setSidebarOpen((previous) => !previous)}
            data-testid="mobile-sidebar-toggle-button"
            aria-label="Mobil menüyü aç/kapat"
          >
            {sidebarOpen ? <X size={16} /> : <Menu size={16} />}
          </Button>
          <p className="text-sm font-semibold uppercase tracking-widest" data-testid="panel-sticky-header-title">Trading Panel</p>
        </div>

        <Button
          type="button"
          variant="outline"
          className="hidden md:inline-flex"
          onClick={() => setSidebarCollapsed((previous) => !previous)}
          data-testid="desktop-sidebar-collapse-button"
          aria-label="Sidebar daralt/genişlet"
        >
          {sidebarCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </Button>
      </div>

      <div className="grid h-[calc(100vh-57px)] grid-cols-1 md:grid-cols-[var(--sidebar-width)_1fr]" style={{ "--sidebar-width": sidebarCollapsed ? "92px" : "260px" }}>
        <aside
          className={`fixed inset-y-[57px] left-0 z-50 flex w-64 -translate-x-full flex-col overflow-y-auto overflow-x-hidden border-r p-4 transition-transform md:static md:inset-auto md:z-auto md:h-full md:min-h-0 md:w-auto md:translate-x-0 ${sidebarClass} ${sidebarOpen ? "translate-x-0" : ""}`}
          data-testid="sidebar-panel"
          aria-label="Ana gezinme menüsü"
        >
          <div className="mb-6">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400" data-testid="brand-kicker">Trading Engine</p>
            <h1 className={`text-xl font-bold uppercase tracking-tight ${brandTitleClass}`} data-testid="brand-title">Industrial Cockpit</h1>
            <p className="mt-2 text-xs text-slate-300" data-testid="active-user-role">Aktif Rol: {user?.role}</p>
            {isAdmin && gateBadge?.override_active && (
              <div className="mt-2 rounded border border-red-700 bg-red-700/20 px-2 py-1 text-[11px] font-semibold text-black" data-testid="navbar-override-countdown-badge">
                active override · {countdownLabel}
              </div>
            )}
          </div>

          <nav className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1 pb-2" data-testid="sidebar-navigation" aria-label="Sidebar linkleri">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  data-testid={item.testId}
                  aria-label={`${item.label} sayfasına git`}
                  className={({ isActive }) =>
                    `flex items-center gap-2 border px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 ${
                      isActive
                        ? activeNavClass
                        : "border-slate-700 text-slate-200 hover:border-slate-500 hover:text-white"
                    }`
                  }
                  onClick={() => setSidebarOpen(false)}
                >
                  <Icon size={16} />
                  <span className={sidebarCollapsed ? "hidden md:inline" : "inline"}>{item.label}</span>
                </NavLink>
              );
            })}
          </nav>

          <Button
            variant="outline"
            className={`mt-auto w-full shrink-0 sticky bottom-0 ${logoutButtonClass}`}
            onClick={() => {
              logout();
              navigate(isAdmin ? "/admin/login" : "/user/login");
            }}
            data-testid="logout-button"
            aria-label="Çıkış yap"
          >
            Çıkış Yap
          </Button>
        </aside>

        <main className="h-full overflow-y-auto p-4 md:p-5" data-testid="panel-content-area" aria-label="Panel içerik alanı">
          <Outlet />
        </main>
      </div>

      {sidebarOpen && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={() => setSidebarOpen(false)}
          data-testid="mobile-sidebar-overlay"
          aria-label="Menüyü kapat"
        />
      )}
    </div>
  );
};
