import atexit
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Load local .env before reading worker configuration.
# ---------------------------------------------------------------------------

load_dotenv()


# ---------------------------------------------------------------------------
# Import path support
# ---------------------------------------------------------------------------

if __package__ in (None, ""):
    sys.path.insert(
        0,
        str(Path(__file__).resolve().parents[1]),
    )


# ---------------------------------------------------------------------------
# Prometheus multiprocess directory
#
# IMPORTANT:
# PROMETHEUS_MULTIPROC_DIR must be set before prometheus_client is imported.
# ---------------------------------------------------------------------------

def _configure_prometheus_multiprocess() -> Path:
    configured_dir = os.getenv(
        "PROMETHEUS_MULTIPROC_DIR"
    )

    if configured_dir:
        metrics_dir = Path(configured_dir)
    else:
        metrics_dir = (
            Path(tempfile.gettempdir())
            / "legal-assist-prometheus"
        )

    metrics_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # The worker lock guarantees that another worker_entry.py instance is
    # not simultaneously using this directory.
    for path in metrics_dir.iterdir():
        try:
            if path.is_file() or path.is_symlink():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                shutil.rmtree(path)
        except OSError:
            # A stale file held by a dead process should normally not happen,
            # but do not prevent startup because of an observability artifact.
            pass

    os.environ["PROMETHEUS_MULTIPROC_DIR"] = str(
        metrics_dir
    )

    return metrics_dir


PROMETHEUS_DIR = _configure_prometheus_multiprocess()

# Import these only after PROMETHEUS_MULTIPROC_DIR has been configured.
from prometheus_client import CONTENT_TYPE_LATEST
from prometheus_client import CollectorRegistry
from prometheus_client import generate_latest
from prometheus_client import multiprocess


# ---------------------------------------------------------------------------
# Worker lock
# ---------------------------------------------------------------------------

LOCK_FILE = (
    Path(__file__).resolve().parent
    / ".worker.lock"
)


def _pid_is_alive(pid: int) -> bool:
    if platform.system().lower().startswith("win"):
        result = subprocess.run(
            [
                "tasklist",
                "/FI",
                f"PID eq {pid}",
                "/NH",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        return str(pid) in result.stdout

    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _acquire_worker_lock_or_exit() -> None:
    """
    Prevent multiple worker_entry.py processes from consuming the same queue.
    """

    if LOCK_FILE.exists():
        try:
            old_pid = int(
                LOCK_FILE.read_text().strip()
            )
        except (ValueError, OSError):
            old_pid = None

        if old_pid and _pid_is_alive(old_pid):
            print(
                (
                    f"Another worker is already running "
                    f"(PID {old_pid}, lock file {LOCK_FILE}). "
                    f"Kill it first. On Windows: "
                    f"taskkill /F /T /PID {old_pid}"
                ),
                file=sys.stderr,
            )
            sys.exit(1)

    LOCK_FILE.write_text(
        str(os.getpid())
    )

    atexit.register(
        lambda: LOCK_FILE.unlink(
            missing_ok=True
        )
    )


# ---------------------------------------------------------------------------
# Worker health + Prometheus metrics HTTP server
# ---------------------------------------------------------------------------

class MetricsHandler(BaseHTTPRequestHandler):
    """
    Worker HTTP endpoints:

        /
        /health
        /metrics
    """

    def do_GET(self) -> None:
        if self.path in ("/", "/health"):
            self._send_health_response()
            return

        if self.path == "/metrics":
            self._send_metrics_response()
            return

        self.send_response(404)
        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8",
        )
        self.end_headers()
        self.wfile.write(b"Not found")

    def _send_health_response(self) -> None:
        body = b"Celery worker is running"

        self.send_response(200)
        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8",
        )
        self.send_header(
            "Content-Length",
            str(len(body)),
        )
        self.end_headers()
        self.wfile.write(body)

    def _send_metrics_response(self) -> None:
        """
        Aggregate metrics written by all Prometheus-enabled worker
        processes using the multiprocess collector.
        """

        registry = CollectorRegistry()

        multiprocess.MultiProcessCollector(
            registry
        )

        body = generate_latest(registry)

        self.send_response(200)
        self.send_header(
            "Content-Type",
            CONTENT_TYPE_LATEST,
        )
        self.send_header(
            "Content-Length",
            str(len(body)),
        )
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Do not spam worker logs with Prometheus scrapes.
        pass


class MetricsHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def start_worker_server() -> MetricsHTTPServer:
    """
    Start worker health + Prometheus HTTP server.

    Local:
        WORKER_METRICS_PORT=9100

    Production:
        Uses the deployment platform's PORT.
    """

    port = int(
        os.getenv(
            "WORKER_METRICS_PORT",
            os.getenv(
                "PORT",
                "7860",
            ),
        )
    )

    server = MetricsHTTPServer(
        ("0.0.0.0", port),
        MetricsHandler,
    )

    print(
        f"Worker health endpoint available at "
        f"http://0.0.0.0:{port}/"
    )

    print(
        f"Worker health endpoint available at "
        f"http://0.0.0.0:{port}/health"
    )

    print(
        f"Worker metrics endpoint available at "
        f"http://0.0.0.0:{port}/metrics"
    )

    print(
        f"Prometheus multiprocess directory: "
        f"{PROMETHEUS_DIR}"
    )

    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
        name="worker-metrics-server",
    )

    thread.start()

    return server


# ---------------------------------------------------------------------------
# Celery startup
# ---------------------------------------------------------------------------

def build_celery_command() -> list[str]:
    """
    Build the Celery worker command.

    Heartbeat is disabled because this deployment does not use Celery
    heartbeat events for observability, avoiding unnecessary broker traffic.
    """

    celery_args = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "app.worker.celery_app:celery",
        "worker",
        "--loglevel=info",

        # Single-worker deployment does not need worker discovery traffic.
        "--without-gossip",
        "--without-mingle",

        # Queue/heartbeat observability does not require Celery heartbeats.
        "--without-heartbeat",
    ]

    # Keep the existing pool strategy.
    if platform.system().lower().startswith("win"):
        celery_args.extend(
            [
                "--pool=solo",
                "--concurrency=1",
            ]
        )
    else:
        celery_args.extend(
            [
                "--concurrency=2",
            ]
        )

    return celery_args


def main() -> None:
    _acquire_worker_lock_or_exit()

    metrics_server = start_worker_server()

    celery_args = build_celery_command()

    print(
        "Starting Celery worker..."
    )

    print(
        "Command:",
        " ".join(celery_args),
    )

    process = subprocess.Popen(
        celery_args
    )

    try:
        process.wait()

    except KeyboardInterrupt:
        print(
            "Shutdown requested. "
            "Stopping Celery worker..."
        )

        process.terminate()

        try:
            process.wait(
                timeout=30
            )

        except subprocess.TimeoutExpired:
            print(
                "Celery did not stop gracefully. "
                "Terminating forcefully."
            )

            process.kill()

    finally:
        try:
            metrics_server.shutdown()
            metrics_server.server_close()
        except Exception:
            pass

    sys.exit(
        process.returncode
    )


if __name__ == "__main__":
    main()
