import requests
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

from _execution_action_helpers import (
    create_and_release_open_position,
    preview_submit_approve_position_action,
    provision_user,
)


def test_reverse_position_creates_new_open_position():
    base, user_headers, admin_headers = provision_user()
    position = create_and_release_open_position(base, user_headers, admin_headers)

    preview_submit_approve_position_action(
        base,
        user_headers,
        admin_headers,
        intent_type="REVERSE_POSITION",
        position_id=position["position_id"],
        symbol=position["symbol"],
        size=float(position["size"]),
    )

    positions = requests.get(f"{base}/api/user/execution/positions", headers=user_headers, timeout=20)
    positions.raise_for_status()
    open_positions = positions.json()
    assert open_positions
    assert all(row["position_id"] != position["position_id"] or row["status"] != "open" for row in open_positions)
