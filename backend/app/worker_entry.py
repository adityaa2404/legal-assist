import os
import subprocess
import sys
import threading
import platform
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

LOCK_FILE = Path(__file__).resolve().parent / ".worker.lock"


def _pid_is_alive(pid: int) -> bool:
    if platform.system().lower().startswith("win"):
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True,
        )
        return str(pid) in out.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _acquire_worker_lock_or_exit() -> None:
    """
    Refuse to start a second worker process against the same code checkout.

    Two worker_entry.py instances consuming the same Celery queue causes tasks
    to be picked up and orphaned mid-flight if either instance dies or is
    killed without the other — indistinguishable from "uploads randomly get
    stuck" from the outside. On HF Spaces this can't happen (one container is
    one process), so this guard mainly protects local dev, where it's easy to
    forget a background worker from an earlier session is still running.
    """
    if LOCK_FILE.exists():
        try:
            old_pid = int(LOCK_FILE.read_text().strip())
        except (ValueError, OSError):
            old_pid = None
        if old_pid and _pid_is_alive(old_pid):
            print(
                f"Another worker is already running (PID {old_pid}, lock file {LOCK_FILE}). "
                f"Kill it first (Windows: taskkill /F /T /PID {old_pid}) before starting a new one — "
                f"two workers on the same queue causes orphaned/stuck tasks.",
                file=sys.stderr,
            )
            sys.exit(1)
        # Stale lock from a process that's no longer alive — safe to reclaim.

    LOCK_FILE.write_text(str(os.getpid()))
    import atexit
    atexit.register(lambda: LOCK_FILE.unlink(missing_ok=True))


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Celery worker is running")

    def log_message(self, format, *args):
        # Silence default HTTP request logs to keep Render logs focused on worker output.
        pass


def start_dummy_server():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


if __name__ == "__main__":
    _acquire_worker_lock_or_exit()

    threading.Thread(target=start_dummy_server, daemon=True).start()

    celery_args = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "app.worker.celery_app:celery",
        "worker",
        "--loglevel=info",
        # Single-worker deployment (PID lock above enforces this) — gossip/mingle
        # exist to let workers discover and sync with peers, which never happens
        # here. They were generating a steady stream of PUBLISH commands against
        # Redis for no benefit.
        "--without-gossip",
        "--without-mingle",
        "--without-heartbeat",
    ]

    # Celery prefork is flaky on Windows for this OCR-heavy workload.
    # Use a single-process pool locally so tasks actually complete.
    if platform.system().lower().startswith("win"):
        celery_args.extend(["--pool=solo", "--concurrency=1"])
    else:
        celery_args.extend(["--concurrency=2"])

    # Start Celery as the foreground process so Render can monitor lifecycle/exit code.
    proc = subprocess.Popen(celery_args)
    proc.wait()
    sys.exit(proc.returncode)
