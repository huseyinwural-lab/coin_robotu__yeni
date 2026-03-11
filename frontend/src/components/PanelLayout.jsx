import {
  Activity,
  AlertTriangle,
  BarChart3,
  BarChartBig,
  ClipboardList,
  Cpu,
  Globe,
  History,
  Settings2,
  ShieldAlert,
  ShieldCheck,
  TestTube2,
  TrendingUp,
  UserCog,
} from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";

const userNavItems = [
  { to: "/app/user", label: "User Dashboard", icon: BarChart3, testId: "nav-user-dashboard-link" },
  { to: "/app/bots", label: "Bot Profilleri", icon: TrendingUp, testId: "nav-bot-profiles-link" },
  { to: "/app/risk-policies", label: "Risk Policy", icon: ShieldAlert, testId: "nav-risk-policies-link" },
  { to: "/app/strategies", label: "Strategy Template", icon: ClipboardList, testId: "nav-strategy-templates-link" },
  { to: "/app/positions", label: "Paper Positions", icon: Activity, testId: "nav-paper-positions-link" },
  { to: "/app/exchange-mock", label: "Exchange Mock", icon: TestTube2, testId: "nav-exchange-mock-link" },
];

const adminOnlyItems = [
  { to: "/app/admin", label: "Admin Dashboard", icon: UserCog, testId: "nav-admin-dashboard-link" },
  { to: "/app/market-universe", label: "Market Universe", icon: Globe, testId: "nav-market-universe-link" },
  { to: "/app/execution-policies", label: "Execution Policies", icon: Settings2, testId: "nav-execution-policies-link" },
  { to: "/app/exposure-groups", label: "Exposure Groups", icon: ShieldAlert, testId: "nav-exposure-groups-link" },
  { to: "/app/execution-states", label: "Execution States", icon: Cpu, testId: "nav-execution-states-link" },
  { to: "/app/hardening-checklist", label: "Hardening Checklist", icon: ShieldCheck, testId: "nav-hardening-checklist-link" },
  { to: "/app/failed-events", label: "Failed Events", icon: AlertTriangle, testId: "nav-failed-events-link" },
  { to: "/app/state-rebuild", label: "State Rebuild Logs", icon: History, testId: "nav-state-rebuild-link" },
  { to: "/app/backtest-cards", label: "Backtest Cards", icon: BarChartBig, testId: "nav-backtest-cards-link" },
  { to: "/app/monitoring", label: "Monitoring", icon: Activity, testId: "nav-monitoring-link" },
  { to: "/app/audit-logs", label: "Audit Logs", icon: ClipboardList, testId: "nav-audit-logs-link" },
];

export const PanelLayout = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const navItems = user?.role === "admin" ? [...adminOnlyItems, ...userNavItems] : userNavItems;
  const isAdmin = user?.role === "admin";

  return (
    <div
      className={`h-screen overflow-hidden bg-slate-950 text-slate-100 ${isAdmin ? "admin-theme" : ""}`}
      data-testid="panel-layout-wrapper"
    >
      <div className="grid h-full grid-cols-1 md:grid-cols-[240px_1fr]">
        <aside className="border-r border-slate-800 bg-slate-900 p-4" data-testid="sidebar-panel">
          <div className="mb-6">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400" data-testid="brand-kicker">Trading Engine</p>
            <h1 className="text-xl font-bold uppercase tracking-tight text-orange-500" data-testid="brand-title">Industrial Cockpit</h1>
            <p className="mt-2 text-xs text-slate-300" data-testid="active-user-role">Aktif Rol: {user?.role}</p>
          </div>

          <nav className="space-y-2" data-testid="sidebar-navigation">
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
                        ? "border-orange-500 bg-slate-800 text-orange-400"
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
            className="mt-8 w-full border-slate-700 bg-transparent text-slate-200 hover:border-orange-500 hover:text-orange-500"
            onClick={() => {
              logout();
              navigate("/login");
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
