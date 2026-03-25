import time

from core.execution_engine import consume_execution_queue_once
from db import SessionLocal
from services.runtime_execution_service import process_submission_event_once


def run_worker_forever(worker_name: str = "execution-worker", poll_interval: float = 0.5):
    while True:
        db = SessionLocal()
        try:
            result = consume_execution_queue_once(db)
            if result is None:
                result = process_submission_event_once(db, worker_name=worker_name)
            if result is None:
                time.sleep(poll_interval)
        finally:
            db.close()


if __name__ == "__main__":
    run_worker_forever()
