import re

# Central Pure Live manifest for Stage-7 lock.
PURE_LIVE_BLOCKED_PATH_PREFIXES: tuple[str, ...] = (
    "/api/paper-positions",
    "/api/execution-safety/execution/dry-run",
    "/api/execution-safety/execution/shadow",
    "/api/runtime-execution/go-live/dry-run",
    "/api/runtime/go-live/dry-run",
    "/api/admin/futures-strategy-status/run-paper-cycle",
    "/api/admin/futures/strategy/run-paper-cycle",
    "/api/admin/live-trading-dashboard/control-layer/execution-mode",
    "/api/admin/strategy-allocation/what-if-simulation",
    "/api/admin/production-gate/mode-transition",
    "/api/user/signal-mode",
    "/api/user/scanner/automation",
    "/api/user/scanner/automation-profiles",
)

PURE_LIVE_BLOCKED_REGEX: tuple[re.Pattern[str], ...] = (
    re.compile(r"^/api/admin/strategies/.*/dry-run$", re.IGNORECASE),
    re.compile(r"^/api/admin/strategies/bulk/dry-run$", re.IGNORECASE),
)

PURE_LIVE_BLOCKED_KEYWORDS: tuple[str, ...] = (
    "/simulate",
    "simulation",
    "dry-run",
    "dry_run",
    "paper",
    "/execution-mode",
)
