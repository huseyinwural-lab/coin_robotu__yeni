"""Socket.IO retest suite for implemented realtime features (connection + join_room)."""

import os
import uuid

import pytest
import socketio


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL is required for public endpoint testing", allow_module_level=True)


def _client():
    return socketio.AsyncClient(reconnection=False, logger=False, engineio_logger=False)


@pytest.mark.anyio
async def test_socket_connection_lifecycle_success_and_disconnect():
    # module: connection lifecycle (connect/status/disconnect)
    client = _client()
    events = {"connected": False, "disconnected": False}

    @client.event
    async def connect():
        events["connected"] = True

    @client.event
    async def disconnect():
        events["disconnected"] = True

    await client.connect(BASE_URL, socketio_path="/api/socket.io", wait_timeout=15)
    assert client.connected is True
    assert events["connected"] is True

    await client.disconnect()
    assert client.connected is False
    assert events["disconnected"] is True


@pytest.mark.anyio
async def test_socket_connection_fails_with_wrong_path():
    # module: negative connect test with wrong socket path
    client = _client()
    with pytest.raises(Exception):
        await client.connect(BASE_URL, socketio_path="/api/socket.io-wrong", wait_timeout=8)


@pytest.mark.anyio
async def test_join_room_valid_and_missing_room_id():
    # module: room management (valid room + missing room_id)
    client = _client()
    result = {"ok": None, "error": None}

    @client.on("join_room_ok")
    async def on_join_ok(payload):
        result["ok"] = payload

    @client.on("join_room_error")
    async def on_join_error(payload):
        result["error"] = payload

    await client.connect(BASE_URL, socketio_path="/api/socket.io", wait_timeout=15)

    room_id = f"room_{uuid.uuid4().hex[:8]}"
    await client.emit("join_room", {"room_id": room_id})
    await client.sleep(0.4)
    assert result["ok"] == {"room_id": room_id}

    await client.emit("join_room", {})
    await client.sleep(0.4)
    assert result["error"] == {"message": "room_id missing"}

    await client.disconnect()


@pytest.mark.anyio
async def test_join_room_multiple_clients_same_and_different_rooms():
    # module: multiple clients room join behavior (join ack validation)
    c1 = _client()
    c2 = _client()
    room_a = f"room_a_{uuid.uuid4().hex[:6]}"
    room_b = f"room_b_{uuid.uuid4().hex[:6]}"

    state = {"c1_ok": None, "c2_ok": None}

    @c1.on("join_room_ok")
    async def c1_join_ok(payload):
        state["c1_ok"] = payload

    @c2.on("join_room_ok")
    async def c2_join_ok(payload):
        state["c2_ok"] = payload

    await c1.connect(BASE_URL, socketio_path="/api/socket.io", wait_timeout=15)
    await c2.connect(BASE_URL, socketio_path="/api/socket.io", wait_timeout=15)

    await c1.emit("join_room", {"room_id": room_a})
    await c2.emit("join_room", {"room_id": room_a})
    await c1.sleep(0.4)
    assert state["c1_ok"] == {"room_id": room_a}
    assert state["c2_ok"] == {"room_id": room_a}

    await c2.emit("join_room", {"room_id": room_b})
    await c2.sleep(0.4)
    assert state["c2_ok"] == {"room_id": room_b}

    await c1.disconnect()
    await c2.disconnect()


@pytest.mark.anyio
async def test_rapid_connect_disconnect_cycles_and_emit_after_disconnect():
    # module: error handling cycles + emit while disconnected behavior
    client = _client()

    for _ in range(3):
        await client.connect(BASE_URL, socketio_path="/api/socket.io", wait_timeout=15)
        assert client.connected is True
        await client.disconnect()
        assert client.connected is False

    with pytest.raises(Exception):
        await client.emit("join_room", {"room_id": "after_disconnect"})


@pytest.mark.anyio
async def test_update_broadcast_and_reconnection_items_not_applicable():
    # module: explicit non-applicable coverage for playbook items not implemented in current app
    pytest.skip(
        "Server has no inbound 'update' event handler or broadcast trigger endpoint; "
        "reconnection backoff policy is client-side and not app-defined for deterministic verification."
    )
