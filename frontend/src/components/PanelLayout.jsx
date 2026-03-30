import {
  Activity,
  BarChart3,
  BarChartBig,
  ChevronDown,
  ChevronRight,
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

const userMenuGroups = [
  { id: "dashboard", label: "Dashboard", items: [{ to: "/user/dashboard", label: "Global Dashboard", icon: BarChart3, testId: "nav-user-dashboard-link" }] },
  { id: "market", label: "Market", items: [{ to: "/user/scanner", label: "Scanner", icon: Gauge, testId: "nav-user-scanner-link" }] },
  {
    id: "execution",
    label: "Execution",
    items: [
      { to: "/user/execution", label: "Execution View", icon: Activity, testId: "nav-user-execution-link" },
      { to: "/user/positions", label: "Positions", icon: Activity, testId: "nav-user-positions-link" },
      { to: "/user/trades", label: "History", icon: Activity, testId: "nav-user-trades-link" },
    ],
  },
  {
    id: "portfolio",
    label: "Portfolio",
    items: [
      { to: "/user/portfolio", label: "PnL", icon: BarChartBig, testId: "nav-user-portfolio-link" },
      { to: "/user/reports", label: "Reports", icon: FileText, testId: "nav-user-reports-link" },
    ],
  },
  {
    id: "strategy",
    label: "Strategy",
    items: [
      { to: "/user/bot-profiles", label: "Bot Profiles", icon: TrendingUp, testId: "nav-bot-profiles-link" },
      { to: "/user/backtest-insights", label: "Backtests", icon: LineChart, testId: "nav-backtest-insights-link" },
    ],
  },
  {
    id: "monitoring",
    label: "Monitoring",
    items: [
      { to: "/user/alerts", label: "Alerts", icon: ShieldAlert, testId: "nav-user-alerts-link" },
      { to: "/user/activity-log", label: "Activity Log", icon: FileText, testId: "nav-user-activity-log-link" },
      { to: "/user/exchange-diagnostics", label: "Diagnostics", icon: Activity, testId: "nav-user-diagnostics-link" },
      { to: "/user/signals", label: "Audit Signals", icon: Radio, testId: "nav-user-signals-link" },
    ],
  },
  {
    id: "settings",
    label: "Settings",
    items: [
      { to: "/user/settings", label: "Profile / API Keys / Risk", icon: Settings2, testId: "nav-user-settings-link" },
      { to: "/user/mfa-settings", label: "MFA", icon: ShieldAlert, testId: "nav-user-mfa-settings-link" },
    ],
  },
];

const adminOnlyItems = [
  {
    id: "core",
    label: "CORE",
    defaultOpen: true,
    items: [
      { to: "/admin/dashboard", label: "Dashboard", icon: UserCog, testId: "nav-admin-dashboard-link" },
      { to: "/admin/live-trading-dashboard", label: "Live Trading Dashboard", icon: Activity, testId: "nav-admin-live-trading-dashboard-link" },
      { to: "/admin/system-status", label: "System Status", icon: Activity, testId: "nav-admin-system-status-link" },
      { to: "/admin/audit-logs", label: "Logs", icon: FileText, testId: "nav-admin-logs-link" },
      { to: "/admin/universe-monitor", label: "Scanner Monitor", icon: Gauge, testId: "nav-admin-scanner-monitor-link" },
      { to: "/admin/futures/strategy-control", label: "Strategy Control", icon: BarChart3, testId: "nav-admin-strategy-control-link" },
    ],
  },
  {
    id: "strategy",
    label: "STRATEGY",
    defaultOpen: true,
    items: [
      { to: "/admin/strategy/allocation", label: "Strategy Allocation", icon: BarChart3, testId: "nav-admin-strategy-allocation-link" },
      { to: "/admin/strategy/intelligence", label: "Strategy Intelligence", icon: BarChart3, testId: "nav-admin-strategy-intelligence-link" },
      { to: "/admin/strategy/canonical-registry", label: "Canonical Strategy Registry", icon: ClipboardList, testId: "nav-admin-strategy-canonical-registry-link" },
      { to: "/admin/strategy/execution-state-machine", label: "Execution State Machine", icon: Activity, testId: "nav-admin-strategy-execution-state-machine-link" },
      { to: "/admin/strategy/observability", label: "Strategy Observability", icon: Gauge, testId: "nav-admin-strategy-observability-link" },
    ],
  },
  {
    id: "risk-execution",
    label: "RISK & EXECUTION",
    defaultOpen: true,
    items: [
      { to: "/admin/risk-orchestrator", label: "Risk Engine", icon: ShieldAlert, testId: "nav-admin-risk-engine-link" },
      { to: "/admin/execution-queue", label: "Execution Monitor", icon: Wrench, testId: "nav-admin-execution-queue-link" },
      { to: "/admin/execution-readiness", label: "Execution Readiness", icon: Activity, testId: "nav-admin-execution-readiness-link" },
      { to: "/admin/execution/operator-center", label: "Operator Center", icon: Activity, testId: "nav-admin-execution-operator-center-link" },
      { to: "/admin/incident-intelligence", label: "Incident Intelligence", icon: ShieldAlert, testId: "nav-admin-incident-intelligence-link" },
      { to: "/admin/unified-control-room", label: "Unified Control Room", icon: ShieldAlert, testId: "nav-admin-unified-control-room-link" },
      { to: "/admin/execution/states", label: "Execution States", icon: Activity, testId: "nav-admin-execution-states-control-link" },
      { to: "/admin/execution/analytics", label: "Execution Analytics", icon: LineChart, testId: "nav-admin-execution-analytics-control-link" },
      { to: "/admin/execution/failures", label: "Execution Failures", icon: ShieldAlert, testId: "nav-admin-execution-failures-control-link" },
      { to: "/admin/execution/idempotency", label: "Idempotency Control", icon: KeyRound, testId: "nav-admin-execution-idempotency-control-link" },
      { to: "/admin/execution/trace", label: "Execution Trace", icon: FileText, testId: "nav-admin-execution-trace-control-link" },
      { to: "/admin/execution/alerts", label: "Execution Alerts Delivery", icon: Activity, testId: "nav-admin-execution-alerts-delivery-link" },
      { to: "/admin/execution/rebuild", label: "Execution Rebuild", icon: Settings2, testId: "nav-admin-execution-rebuild-control-link" },
    ],
  },
  {
    id: "operations",
    label: "OPERATIONS",
    defaultOpen: true,
    items: [
      { to: "/admin/strategies", label: "Bots", icon: ClipboardList, testId: "nav-admin-bots-link" },
      { to: "/admin/users/customers", label: "Users", icon: UserCog, testId: "nav-admin-users-link" },
      { to: "/admin/commercial-ops", label: "Commercial Ops", icon: BarChartBig, testId: "nav-admin-commercial-ops-link", superAdminOnly: true },
      { to: "/admin/revenue", label: "Revenue Engine", icon: TrendingUp, testId: "nav-admin-revenue-link", superAdminOnly: true },
      { to: "/admin/users/economics", label: "User Economics", icon: BarChart3, testId: "nav-admin-user-economics-link", superAdminOnly: true },
      { to: "/admin/snapshots", label: "Analytics Snapshots", icon: LineChart, testId: "nav-admin-analytics-snapshots-link", superAdminOnly: true },
      { to: "/admin/credential-orchestration", label: "Credential Orchestration", icon: KeyRound, testId: "nav-admin-credential-orchestration-link" },
      { to: "/admin/user-approvals", label: "User Approvals", icon: UserCog, testId: "nav-admin-user-approvals-link" },
      { to: "/admin/onboarding-observability", label: "Onboarding Observability", icon: LineChart, testId: "nav-admin-onboarding-observability-link" },
      { to: "/admin/pipeline-operations", label: "Pipeline Operations", icon: Activity, testId: "nav-admin-pipeline-operations-link" },
      { to: "/admin/exchanges", label: "Exchange Settings", icon: Globe, testId: "nav-admin-exchange-settings-link" },
      { to: "/admin/mfa-settings", label: "MFA Settings", icon: ShieldAlert, testId: "nav-admin-mfa-settings-link" },
      { to: "/admin/brand-settings", label: "Brand Settings", icon: Settings2, testId: "nav-admin-brand-settings-link" },
    ],
  },
  {
    id: "system",
    label: "SYSTEM",
    defaultOpen: false,
    items: [
      { to: "/admin/execution-policies", label: "System Config", icon: Settings2, testId: "nav-admin-system-config-link" },
      { to: "/admin/system-readiness", label: "System Readiness", icon: Gauge, testId: "nav-admin-system-readiness-link" },
      { to: "/admin/anomaly-timeline", label: "Anomaly Timeline", icon: Activity, testId: "nav-admin-anomaly-timeline-link" },
    ],
  },
  {
    id: "research",
    label: "RESEARCH",
    defaultOpen: false,
    items: [
      { to: "/admin/futures/risk-monitor", label: "futures/risk-monitor", icon: LineChart, testId: "nav-admin-advanced-futures-risk-monitor-link" },
      { to: "/admin/futures/liquidation-protection", label: "futures/liquidation-protection", icon: LineChart, testId: "nav-admin-advanced-futures-liquidation-protection-link" },
      { to: "/admin/futures/cluster-risk", label: "futures/cluster-risk", icon: LineChart, testId: "nav-admin-advanced-futures-cluster-risk-link" },
      { to: "/admin/futures/strategy-control", label: "futures/strategy-control", icon: LineChart, testId: "nav-admin-advanced-futures-strategy-control-link" },
      { to: "/admin/futures/tail-risk", label: "futures/tail-risk", icon: LineChart, testId: "nav-admin-advanced-futures-tail-risk-link" },
      { to: "/admin/futures/live-readiness", label: "futures/live-readiness", icon: LineChart, testId: "nav-admin-advanced-futures-live-readiness-link" },
      { to: "/admin/futures/scaling-validation", label: "futures/scaling-validation", icon: LineChart, testId: "nav-admin-advanced-futures-scaling-validation-link" },
      { to: "/admin/futures/microstructure-guard", label: "futures/microstructure-guard", icon: LineChart, testId: "nav-admin-advanced-futures-microstructure-guard-link" },
      { to: "/admin/futures/testnet-control", label: "futures/testnet-control", icon: LineChart, testId: "nav-admin-advanced-futures-testnet-control-link" },
      { to: "/admin/proofs", label: "proofs", icon: FileText, testId: "nav-admin-advanced-proofs-link" },
      { to: "/admin/reports/archive", label: "reports/archive", icon: FileText, testId: "nav-admin-advanced-reports-archive-link" },
      { to: "/admin/runtime/quarantine", label: "runtime/quarantine", icon: ShieldAlert, testId: "nav-admin-advanced-runtime-quarantine-link" },
      { to: "/admin/runtime/recovery", label: "runtime/recovery", icon: ShieldAlert, testId: "nav-admin-advanced-runtime-recovery-link" },
      { to: "/admin/learning-panel", label: "learning-panel", icon: ClipboardList, testId: "nav-admin-advanced-learning-panel-link" },
      { to: "/admin/learning-impact-simulator", label: "learning-impact-simulator", icon: ClipboardList, testId: "nav-admin-advanced-learning-impact-simulator-link" },
      { to: "/admin/freshness-heatmap", label: "freshness-heatmap", icon: Gauge, testId: "nav-admin-advanced-freshness-heatmap-link" },
    ],
  },
];

export const PanelLayout = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const adminRoles = new Set(["super_admin", "admin", "ops"]);
  const [gateBadge, setGateBadge] = useState(null);
  const [sanityBadge, setSanityBadge] = useState(null);
  const [nowTick, setNowTick] = useState(Date.now());
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarSearch, setSidebarSearch] = useState("");
  const [adminGroupOpen, setAdminGroupOpen] = useState(() =>
    Object.fromEntries(adminOnlyItems.map((group) => [group.id, group.defaultOpen])),
  );
  const isAdmin = adminRoles.has(user?.role);
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
      setSanityBadge(null);
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

    const fetchSanity = async () => {
      try {
        const { data } = await apiClient.get("/venues/admin/control-plane-sanity-last");
        setSanityBadge(data || null);
      } catch {
        setSanityBadge(null);
      }
    };

    fetchGate();
    fetchSanity();
    const timer = setInterval(() => {
      fetchGate();
      fetchSanity();
    }, 15000);
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
    const ms = new Date(gateBadge.override_expires_at).getTime() - nowTick;
    if (ms <= 0) {
      return "expired";
    }
    const min = Math.floor(ms / 60000);
    const sec = Math.floor((ms % 60000) / 1000);
    return `expires in ${min}m ${sec}s`;
  }, [gateBadge, nowTick]);

  const normalizedSearch = useMemo(() => sidebarSearch.trim().toLocaleLowerCase("tr-TR"), [sidebarSearch]);

  const filteredAdminGroups = useMemo(() => {
    if (!normalizedSearch) return adminOnlyItems;
    return adminOnlyItems
      .map((group) => ({
        ...group,
        items: group.items.filter((item) => item.label.toLocaleLowerCase("tr-TR").includes(normalizedSearch)),
      }))
      .filter((group) => group.items.length > 0);
  }, [normalizedSearch]);

  const filteredUserGroups = useMemo(() => {
    if (!normalizedSearch) return userMenuGroups;
    return userMenuGroups
      .map((group) => ({
        ...group,
        items: group.items.filter((item) => item.label.toLocaleLowerCase("tr-TR").includes(normalizedSearch)),
      }))
      .filter((group) => group.items.length > 0);
  }, [normalizedSearch]);

  const hasAnySidebarMatch = useMemo(() => {
    if (isAdmin) {
      return filteredAdminGroups.some((group) => (group.items || []).length > 0);
    }
    return filteredUserGroups.length > 0;
  }, [filteredAdminGroups, filteredUserGroups, isAdmin]);

  const renderNavLink = (item) => {
    if (item.superAdminOnly && user?.role !== "super_admin") {
      return null;
    }
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
  };

  const toggleAdminGroup = (groupId) => {
    setAdminGroupOpen((prev) => ({
      ...prev,
      [groupId]: !prev[groupId],
    }));
  };

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
            {isAdmin && gateBadge?.status === "BLOCKED" && (
              <div className="mt-2 rounded border border-red-700 bg-red-700/20 px-2 py-2 text-[11px] text-black" data-testid="navbar-release-gate-blocked-actionable">
                <p className="font-semibold" data-testid="navbar-release-gate-blocked-title">Release Gate BLOCKED</p>
                <p className="mt-1" data-testid="navbar-release-gate-blocked-message">
                  Deploy kapalı. Aksiyon: Blokajı Çöz ekranında prod config girip yeniden doğrula.
                </p>
                <p className="mt-1 font-mono" data-testid="navbar-release-gate-blocked-reasons">
                  {(gateBadge?.reason_codes || gateBadge?.reasons || []).slice(0, 2).join(", ") || "reason_code_missing"}
                </p>
                <NavLink
                  to="/admin/execution-policies"
                  className="mt-2 inline-flex rounded border border-emerald-700 bg-emerald-100 px-2 py-1 text-[10px] font-semibold text-emerald-900 hover:bg-emerald-200"
                  data-testid="navbar-release-gate-open-remediation-link"
                >
                  Blokajı Çöz
                </NavLink>
              </div>
            )}
            {isAdmin && gateBadge?.override_active && (
              <div className="mt-2 rounded border border-red-700 bg-red-700/20 px-2 py-1 text-[11px] font-semibold text-black" data-testid="navbar-override-countdown-badge">
                active override · {countdownLabel}
              </div>
            )}
            {isAdmin && (
              <div className="mt-2 rounded border border-black/40 bg-white/60 px-2 py-1 text-[11px]" data-testid="navbar-control-plane-sanity-badge">
                sanity: {sanityBadge?.net_status || "WARN"}
              </div>
            )}
          </div>

          <nav className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1 pb-2" data-testid="sidebar-navigation" aria-label="Sidebar linkleri">
            <div className="mb-2" data-testid="sidebar-search-wrapper">
              <input
                type="text"
                value={sidebarSearch}
                onChange={(event) => setSidebarSearch(event.target.value)}
                placeholder="Menüde ara..."
                className="w-full rounded border border-black/30 bg-white/70 px-2 py-1 text-xs text-black placeholder:text-slate-500"
                data-testid="sidebar-search-input"
              />
            </div>

            {!hasAnySidebarMatch && (
              <p className="rounded border border-black/20 bg-black/5 px-2 py-2 text-xs text-black" data-testid="sidebar-search-no-results">
                Eşleşme bulunamadı
              </p>
            )}

            {isAdmin ? (
              <div className="space-y-3" data-testid="admin-menu-groups">
                {filteredAdminGroups.map((group) => {
                  const isOpen = normalizedSearch ? true : (adminGroupOpen[group.id] ?? group.defaultOpen);

                  return (
                    <section key={group.id} className="rounded border border-black/30 bg-black/10 p-2" data-testid={`admin-menu-group-${group.id}`}>
                      <button
                        type="button"
                        className="flex w-full items-center justify-between gap-2 rounded border border-black/20 bg-black/5 px-2 py-1 text-xs font-semibold uppercase tracking-wider text-black hover:bg-black/10"
                        onClick={() => toggleAdminGroup(group.id)}
                        data-testid={`admin-menu-group-toggle-${group.id}`}
                        aria-expanded={isOpen}
                        aria-controls={`admin-menu-group-items-${group.id}`}
                      >
                        <span>{group.label}</span>
                        {isOpen ? <ChevronDown size={14} data-testid={`admin-menu-group-icon-open-${group.id}`} /> : <ChevronRight size={14} data-testid={`admin-menu-group-icon-closed-${group.id}`} />}
                      </button>

                      {isOpen && (
                        <div className="mt-2 space-y-2" id={`admin-menu-group-items-${group.id}`} data-testid={`admin-menu-group-items-${group.id}`}>
                          {group.items.map(renderNavLink)}
                        </div>
                      )}
                    </section>
                  );
                })}
              </div>
            ) : (
              <div className="space-y-3" data-testid="user-menu-groups">
                {filteredUserGroups.map((group) => (
                  <section key={group.id} className="rounded border border-black/20 bg-black/5 p-2" data-testid={`user-menu-group-${group.id}`}>
                    <p className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-black" data-testid={`user-menu-group-label-${group.id}`}>{group.label}</p>
                    <div className="mt-2 space-y-2" data-testid={`user-menu-group-items-${group.id}`}>
                      {group.items.map(renderNavLink)}
                    </div>
                  </section>
                ))}
              </div>
            )}
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

        <main className={`h-full overflow-y-auto p-4 md:p-5 ${isAdmin ? "admin-light-panels" : ""}`} data-testid="panel-content-area" aria-label="Panel içerik alanı">
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
