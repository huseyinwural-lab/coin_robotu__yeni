import asyncio
import json
from datetime import datetime, timezone

from fastapi import WebSocket

from db import redis_client


TIMELINE_KEY = "runtime:execution_timeline"


class RuntimeStreamHub:
    def __init__(self):
        self._clients: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def connect(self, *, client_id: str, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self._clients[client_id] = websocket

    async def disconnect(self, *, client_id: str):
        async with self._lock:
            self._clients.pop(client_id, None)

    def record_event(self, event: dict) -> dict:
        payload = dict(event)
        payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        redis_client.rpush(TIMELINE_KEY, json.dumps(payload, ensure_ascii=False, default=str))
        if hasattr(redis_client, "ltrim"):
            redis_client.ltrim(TIMELINE_KEY, -500, -1)
        else:
            all_items = redis_client.lrange(TIMELINE_KEY, 0, -1) or []
            recent = all_items[-500:]
            if hasattr(redis_client, "delete"):
                redis_client.delete(TIMELINE_KEY)
            if recent:
                for item in recent:
                    redis_client.rpush(TIMELINE_KEY, item)

        return payload

    async def publish_event(self, event: dict):
        payload = self.record_event(event)

        async with self._lock:
            clients = list(self._clients.items())

        stale_clients: list[str] = []
        for client_id, websocket in clients:
            try:
                await websocket.send_json(payload)
            except Exception:  # noqa: BLE001
                stale_clients.append(client_id)

        for client_id in stale_clients:
            await self.disconnect(client_id=client_id)

    def get_recent_events(self, *, limit: int = 50) -> list[dict]:
        all_rows = redis_client.lrange(TIMELINE_KEY, 0, -1) or []
        rows = all_rows[-max(1, min(limit, 500)):]
        events: list[dict] = []
        for row in rows:
            raw = row.decode("utf-8") if isinstance(row, bytes) else row
            if not raw:
                continue
            try:
                events.append(json.loads(raw))
            except Exception:  # noqa: BLE001
                continue
        return events


runtime_stream_hub = RuntimeStreamHub()
