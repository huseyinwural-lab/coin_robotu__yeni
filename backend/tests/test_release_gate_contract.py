def test_release_gate_contract_reason_codes_and_blocking_metrics():
    import sys
    from pathlib import Path

    backend_root = Path(__file__).resolve().parents[1]
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    from db import SessionLocal
    from services.live_mode_service import enforce_release_gate

    db = SessionLocal()
    try:
        payload = enforce_release_gate(db, environment="prod")
    finally:
        db.close()

    assert payload.get("status") in {"PASS", "BLOCKED"}
    assert isinstance(payload.get("reason_codes"), list)
    assert isinstance(payload.get("blocking_metrics"), dict)
    if payload.get("status") == "BLOCKED":
        assert len(payload.get("reason_codes") or []) > 0
