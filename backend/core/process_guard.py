import logging
import subprocess
import threading
import time


logger = logging.getLogger(__name__)

_CHILDREN_LOCK = threading.Lock()
_ACTIVE_CHILDREN: dict[int, subprocess.Popen] = {}
_REAPER_THREAD: threading.Thread | None = None


def _reap_finished_children_loop() -> None:
    while True:
        with _CHILDREN_LOCK:
            items = list(_ACTIVE_CHILDREN.items())

        for pid, process in items:
            try:
                rc = process.poll()
                if rc is None:
                    continue
                process.wait(timeout=0)
            except Exception as exc:  # noqa: BLE001
                logger.warning("process_guard_reap_failed pid=%s error=%s", pid, exc)
            finally:
                with _CHILDREN_LOCK:
                    _ACTIVE_CHILDREN.pop(pid, None)

        time.sleep(0.5)


def _ensure_reaper_thread_started() -> None:
    global _REAPER_THREAD
    with _CHILDREN_LOCK:
        if _REAPER_THREAD is not None and _REAPER_THREAD.is_alive():
            return
        _REAPER_THREAD = threading.Thread(target=_reap_finished_children_loop, daemon=True, name="process-guard-reaper")
        _REAPER_THREAD.start()


def spawn_shell_and_reap(*, command: str, cwd: str = "/app") -> int:
    _ensure_reaper_thread_started()

    process = subprocess.Popen(
        ["bash", "-lc", command],
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )

    with _CHILDREN_LOCK:
        _ACTIVE_CHILDREN[process.pid] = process

    return process.pid
