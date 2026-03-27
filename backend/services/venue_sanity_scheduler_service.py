import asyncio
import os

from services.venue_control_plane_service import run_and_cache_venue_control_plane_sanity


async def run_venue_sanity_scheduler_loop(session_factory):
    interval_seconds = max(30, int(os.environ.get("VENUE_SANITY_CRON_SECONDS") or "300"))
    while True:
        def _job():
            db = session_factory()
            try:
                run_and_cache_venue_control_plane_sanity(db)
            finally:
                db.close()

        await asyncio.to_thread(_job)
        await asyncio.sleep(interval_seconds)
