from routers.admin_phase3_modules.alerts import router as alerts_router
from routers.admin_phase3_modules.analytics import router as analytics_router
from routers.admin_phase3_modules.export import router as export_router
from routers.admin_phase3_modules.recovery import router as recovery_router

__all__ = [
    "analytics_router",
    "export_router",
    "recovery_router",
    "alerts_router",
]
