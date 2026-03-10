import logging

import socketio

logger = logging.getLogger(__name__)

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")


@sio.event
async def connect(sid, environ):
    logger.info("Socket client connected: %s", sid)


@sio.event
async def disconnect(sid):
    logger.info("Socket client disconnected: %s", sid)


@sio.event
async def join_room(sid, data):
    room_id = (data or {}).get("room_id")
    if not room_id:
        await sio.emit("join_room_error", {"message": "room_id missing"}, to=sid)
        return
    await sio.enter_room(sid, room_id)
    await sio.emit("join_room_ok", {"room_id": room_id}, to=sid)


async def broadcast_update(room_id: str, payload: dict):
    await sio.emit("update", payload, room=room_id)


def create_socket_app(fastapi_app):
    return socketio.ASGIApp(sio, other_asgi_app=fastapi_app, socketio_path="/api/socket.io")