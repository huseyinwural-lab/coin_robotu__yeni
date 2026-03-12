import requests
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

from _execution_action_helpers import (
    create_and_release_open_position,
    preview_submit_approve_position_action,
    provision_user,
)


def test_move_stop_updates_position_stop_loss():
    base, user_headers, admin_headers = provision_user()
    position = create_and_release_open_position(base, user_headers, admin_headers)
    stop_price = round(float(position["entry_price"]) * 0.98, 4)

    preview_submit_approve_position_action(
        base,
        user_headers,
        admin_headers,
        intent_type="MOVE_STOP",
        position_id=position["position_id"],
        symbol=position["symbol"],
        size=float(position["size"]),
        stop_price=stop_price,
    )

    paper_rows_resp = requests.get(f"{base}/api/paper-positions", headers=user_headers, timeout=20)
    paper_rows_resp.raise_for_status()
    paper_rows = [row for row in paper_rows_resp.json() if row["id"] == position["position_id"]]
    assert paper_rows
    assert round(float(paper_rows[0]["stop_loss"]), 4) == stop_price
