import asyncio
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.runtime_stream import runtime_stream_hub
from core.security import decode_access_token
from deps import is_admin_role
from db import SessionLocal
from models import User


router = APIRouter()


def _extract_token(websocket: WebSocket) -> str | None:
    token = websocket.query_params.get("token")
    if token:
        return token
    auth_header = websocket.headers.get("authorization")
    if not auth_header:
        return None
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return auth_header.strip()


def _resolve_admin_user(token: str | None) -> User | None:
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except ValueError:
        return None

    subject = payload.get("sub")
    if not subject:
        return None

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == subject).first()
        if user is None:
            return None
        if not user.is_active:
            return None
        if not is_admin_role(user.role):
            return None
        return user
    finally:
        db.close()


@router.websocket("/runtime/ws/execution-timeline")
async def runtime_execution_timeline_ws(websocket: WebSocket):
    token = _extract_token(websocket)
    user = _resolve_admin_user(token)
    if user is None:
        await websocket.close(code=4401)
        return

    client_id = f"{user.id}:{uuid.uuid4()}"
    try:
        heartbeat_seconds = max(10.0, float(os.environ.get("RUNTIME_WS_HEARTBEAT_SECONDS") or 25.0))
    except ValueError:
        heartbeat_seconds = 25.0
    await runtime_stream_hub.connect(client_id=client_id, websocket=websocket)
    try:
        await websocket.send_json(
            {
                "event_type": "runtime_stream_bootstrap",
                "status": "connected",
                "events": runtime_stream_hub.get_recent_events(limit=50),
            }
        )
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=heartbeat_seconds)
                if str(message).strip().lower() == "ping":
                    await websocket.send_json({"event_type": "pong"})
            except asyncio.TimeoutError:
                await websocket.send_json(
                    {
                        "event_type": "runtime_stream_ping",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        await runtime_stream_hub.disconnect(client_id=client_id)
