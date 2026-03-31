import asyncio
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.security import decode_access_token
from db import SessionLocal
from models import UserRole
from services.auth_session_security_service import DEVICE_HEADER_NAME
from services.user_live_dashboard_service import build_user_live_runtime_snapshot


router = APIRouter()


def _extract_token(websocket: WebSocket) -> str | None:
    token = websocket.query_params.get("token")
    if token:
        return token
    auth_header = websocket.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return auth_header.strip() if auth_header else None


@router.websocket("/user/live/ws/stream")
async def user_live_stream(websocket: WebSocket):
    token = _extract_token(websocket)
    if not token:
        await websocket.close(code=1008)
        return
    try:
        payload = decode_access_token(token)
    except ValueError:
        await websocket.close(code=1008)
        return
    subject = str(payload.get("sub") or "").strip()
    role = str(payload.get("role") or "").strip().lower()
    token_device_id = str(payload.get("device_id") or "").strip()
    provided_device_id = str(websocket.query_params.get("device_id") or websocket.headers.get(DEVICE_HEADER_NAME) or "").strip()
    if not subject or role != UserRole.USER.value or not token_device_id or token_device_id != provided_device_id:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    try:
        while True:
            db = SessionLocal()
            try:
                snapshot = build_user_live_runtime_snapshot(db, subject, window="1h")
            finally:
                db.close()
            await websocket.send_json({"event_type": "user_live_snapshot", **snapshot})
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=8)
                if str(message).strip().lower() == "ping":
                    await websocket.send_json({"event_type": "pong"})
            except asyncio.TimeoutError:
                continue
    except WebSocketDisconnect:
        return
    except Exception:
        return
