export const PURE_LIVE_BLOCKED_ADMIN_PATHS = [
  "/admin/execution-policies",
  "/admin/learning-impact-simulator",
  "/admin/strategy/execution-state-machine",
  "/admin/execution/states",
  "/admin/execution/analytics",
  "/admin/monitoring",
  "/admin/system-status",
  "/admin/phase4-live",
  "/admin/futures/strategy-control",
  "/admin/futures/live-control",
  "/admin/learning-panel",
  "/admin/strategy/intelligence",
  "/admin/execution-readiness",
];

export const PURE_LIVE_BLOCKED_USER_PATHS = [
  "/user/paper-positions",
];

export const PURE_LIVE_BLOCKED_KEYWORDS = ["simulation", "dry-run", "dry_run", "paper", "execution-mode"];

export const isPureLiveBlockedPath = (pathname = "", isAdmin = false) => {
  const normalized = String(pathname || "").trim().toLowerCase();
  const exactBlocked = isAdmin ? PURE_LIVE_BLOCKED_ADMIN_PATHS : PURE_LIVE_BLOCKED_USER_PATHS;
  if (exactBlocked.some((path) => normalized === path)) {
    return true;
  }
  return PURE_LIVE_BLOCKED_KEYWORDS.some((keyword) => normalized.includes(keyword));
};
