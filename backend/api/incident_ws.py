import asyncio
import os
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.incident_stream import incident_stream_hub
from core.security import decode_access_token
from deps import is_admin_role
from models import UserRole


router = APIRouter()


def _extract_token(websocket: WebSocket) -> str | None:
    auth_header = websocket.headers.get("authorization")
    if not auth_header:
        return None
    scheme, _, value = auth_header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    token = value.strip()
    return token or None


def _resolve_admin_user(token: str | None):
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except ValueError:
        return None
    subject = str(payload.get("sub") or "").strip()
    role = payload.get("role")
    if not subject or not role:
        return None
    try:
        resolved_role = role if isinstance(role, UserRole) else UserRole(str(role))
    except ValueError:
        return None
    if not is_admin_role(resolved_role):
        return None
    return SimpleNamespace(id=subject, role=resolved_role)


def _device_matches_token(websocket: WebSocket, user) -> bool:
    token = _extract_token(websocket)
    if not token:
        return False
    try:
        payload = decode_access_token(token)
    except ValueError:
        return False
    token_device_id = str(payload.get("device_id") or "").strip()
    provided_device_id = str(websocket.headers.get("x-session-device") or "").strip()
    return bool(token_device_id and provided_device_id and token_device_id == provided_device_id)


@router.websocket("/incident-intelligence/ws/stream")
async def incident_intelligence_stream_ws(websocket: WebSocket):
    token = _extract_token(websocket)
    user = _resolve_admin_user(token)
    if user is None or not _device_matches_token(websocket, user):
        await websocket.accept()
        await websocket.send_json({"event_type": "incident_stream_error", "detail": "unauthorized"})
        await asyncio.sleep(0.15)
        await websocket.close(code=4401)
        return

    client_id = f"{user.id}:{uuid.uuid4()}"
    try:
        heartbeat_seconds = max(10.0, float(os.environ.get("INCIDENT_WS_HEARTBEAT_SECONDS") or 25.0))
    except ValueError:
        heartbeat_seconds = 25.0
    await incident_stream_hub.connect(client_id=client_id, websocket=websocket)
    try:
        await websocket.send_json(
            {
                "event_type": "incident_stream_bootstrap",
                "status": "connected",
                "events": incident_stream_hub.get_recent_events(limit=50),
            }
        )
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=heartbeat_seconds)
                if str(message).strip().lower() == "ping":
                    await websocket.send_json({"event_type": "pong"})
            except asyncio.TimeoutError:
                await websocket.send_json({"event_type": "incident_stream_ping", "timestamp": datetime.now(timezone.utc).isoformat()})
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        await incident_stream_hub.disconnect(client_id=client_id)
