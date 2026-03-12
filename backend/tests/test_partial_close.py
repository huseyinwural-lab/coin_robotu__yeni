import requests
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

from _execution_action_helpers import (
    create_and_release_open_position,
    preview_submit_approve_position_action,
    provision_user,
)


def test_partial_close_reduces_position_size():
    base, user_headers, admin_headers = provision_user()
    position = create_and_release_open_position(base, user_headers, admin_headers)
    original_size = float(position["size"])
    partial_size = round(max(original_size / 2, 0.001), 6)

    preview_submit_approve_position_action(
        base,
        user_headers,
        admin_headers,
        intent_type="PARTIAL_CLOSE",
        position_id=position["position_id"],
        symbol=position["symbol"],
        size=partial_size,
    )

    positions = requests.get(f"{base}/api/user/execution/positions", headers=user_headers, timeout=20)
    positions.raise_for_status()
    rows = [row for row in positions.json() if row["position_id"] == position["position_id"]]
    assert rows
    assert float(rows[0]["size"]) < original_size
    assert rows[0]["status"] in {"open", "closed"}
