import logging
import subprocess
import threading


logger = logging.getLogger(__name__)


def spawn_shell_and_reap(*, command: str, cwd: str = "/app") -> int:
    process = subprocess.Popen(
        ["bash", "-lc", command],
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )

    def _reap_child() -> None:
        try:
            process.wait()
        except Exception as exc:  # noqa: BLE001
            logger.warning("spawn_shell_and_reap_wait_failed pid=%s error=%s", process.pid, exc)

    threading.Thread(target=_reap_child, daemon=True).start()
    return process.pid
