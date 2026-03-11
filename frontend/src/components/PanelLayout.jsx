import {
  Activity,
  AlertTriangle,
  BarChart3,
  BarChartBig,
  ClipboardList,
  CircuitBoard,
  Cpu,
  Globe,
  History,
  KeyRound,
  LineChart,
  ListChecks,
  Radio,
  Settings2,
  ShieldAlert,
  ShieldCheck,
  TestTube2,
  TrendingUp,
  UserCog,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

const userNavItems = [
  { to: "/user/dashboard", label: "User Dashboard", icon: BarChart3, testId: "nav-user-dashboard-link" },
  { to: "/user/bots", label: "Bot Profilleri", icon: TrendingUp, testId: "nav-bot-profiles-link" },
  { to: "/user/risk-policies", label: "Risk Policy", icon: ShieldAlert, testId: "nav-risk-policies-link" },
  { to: "/user/strategies", label: "Strategy Template", icon: ClipboardList, testId: "nav-strategy-templates-link" },
  { to: "/user/backtest-insights", label: "Backtest Insights", icon: LineChart, testId: "nav-backtest-insights-link" },
  { to: "/user/exchange-settings", label: "Exchange Settings", icon: KeyRound, testId: "nav-user-exchange-settings-link" },
  { to: "/user/positions", label: "Paper Positions", icon: Activity, testId: "nav-paper-positions-link" },
  { to: "/user/exchange-mock", label: "Exchange Mock", icon: TestTube2, testId: "nav-exchange-mock-link" },
];

const adminOnlyItems = [
  { to: "/admin/dashboard", label: "Admin Dashboard", icon: UserCog, testId: "nav-admin-dashboard-link" },
  { to: "/admin/user-approvals", label: "Kullanıcı Onayları", icon: ListChecks, testId: "nav-admin-user-approvals-link" },
  { to: "/admin/exchanges", label: "Exchanges", icon: Globe, testId: "nav-admin-exchanges-link" },
  { to: "/admin/proofs", label: "Proof Panel", icon: ShieldCheck, testId: "nav-admin-proofs-link" },
  { to: "/admin/strategies", label: "Strategies", icon: ClipboardList, testId: "nav-admin-strategies-link" },
  { to: "/admin/risk-orchestrator", label: "Risk Orchestrator", icon: ShieldAlert, testId: "nav-risk-orchestrator-link" },
  { to: "/admin/risk-orchestrator/analytics", label: "Risk Analytics", icon: BarChart3, testId: "nav-risk-analytics-link" },
  { to: "/admin/runtime/quarantine", label: "Runtime Quarantine", icon: AlertTriangle, testId: "nav-runtime-quarantine-link" },
  { to: "/admin/runtime/recovery", label: "Runtime Recovery", icon: History, testId: "nav-runtime-recovery-link" },
  { to: "/admin/market-universe", label: "Market Universe", icon: Globe, testId: "nav-market-universe-link" },
  { to: "/admin/execution-policies", label: "Execution Policies", icon: Settings2, testId: "nav-execution-policies-link" },
  { to: "/admin/exposure-groups", label: "Exposure Groups", icon: ShieldAlert, testId: "nav-exposure-groups-link" },
  { to: "/admin/correlation-matrix", label: "Correlation Matrix", icon: CircuitBoard, testId: "nav-correlation-matrix-link" },
  { to: "/admin/execution-states", label: "Execution States", icon: Cpu, testId: "nav-execution-states-link" },
  { to: "/admin/hardening-checklist", label: "Hardening Checklist", icon: ShieldCheck, testId: "nav-hardening-checklist-link" },
  { to: "/admin/failed-events", label: "Failed Events", icon: AlertTriangle, testId: "nav-failed-events-link" },
  { to: "/admin/state-rebuild", label: "State Rebuild Logs", icon: History, testId: "nav-state-rebuild-link" },
  { to: "/admin/backtest-cards", label: "Backtest Cards", icon: BarChartBig, testId: "nav-backtest-cards-link" },
  { to: "/admin/monitoring", label: "Monitoring", icon: Activity, testId: "nav-monitoring-link" },
  { to: "/admin/phase4-live", label: "Phase-4 Live Control", icon: Radio, testId: "nav-phase4-live-link" },
  { to: "/admin/audit-logs", label: "Audit Logs", icon: ClipboardList, testId: "nav-audit-logs-link" },
];

export const PanelLayout = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [gateBadge, setGateBadge] = useState(null);
  const [nowTick, setNowTick] = useState(Date.now());
  const navItems = user?.role === "admin" ? adminOnlyItems : userNavItems;
  const isAdmin = user?.role === "admin";
  const roleThemeClass = isAdmin ? "admin-ops-theme" : "user-theme";
  const sidebarClass = isAdmin ? "border-orange-700 bg-orange-300" : "border-slate-800 bg-slate-900";
  const brandTitleClass = isAdmin ? "text-black" : "text-orange-500";
  const activeNavClass = isAdmin
    ? "border-black bg-orange-400 text-black"
    : "border-orange-500 bg-slate-800 text-orange-400";
  const logoutButtonClass = isAdmin
    ? "border-black bg-orange-400 text-black hover:bg-orange-500"
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
      <div className="grid h-full grid-cols-1 md:grid-cols-[240px_1fr]">
        <aside className={`flex h-full flex-col border-r p-4 ${sidebarClass}`} data-testid="sidebar-panel">
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

          <nav className="flex-1 space-y-2 overflow-y-auto pr-1" data-testid="sidebar-navigation">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  data-testid={item.testId}
                  className={({ isActive }) =>
                    `flex items-center gap-2 border px-3 py-2 text-sm transition-colors ${
                      isActive
                        ? activeNavClass
                        : "border-slate-700 text-slate-200 hover:border-slate-500 hover:text-white"
                    }`
                  }
                >
                  <Icon size={16} />
                  <span>{item.label}</span>
                </NavLink>
              );
            })}
          </nav>

          <Button
            variant="outline"
            className={`mt-8 w-full ${logoutButtonClass}`}
            onClick={() => {
              logout();
              navigate(isAdmin ? "/admin/login" : "/user/login");
            }}
            data-testid="logout-button"
          >
            Çıkış Yap
          </Button>
        </aside>

        <main className="h-full overflow-y-auto p-4 md:p-5" data-testid="panel-content-area">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
