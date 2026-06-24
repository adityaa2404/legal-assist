import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


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
    threading.Thread(target=start_dummy_server, daemon=True).start()

    # Start Celery as the foreground process so Render can monitor lifecycle/exit code.
    proc = subprocess.Popen([
        "celery",
        "-A",
        "app.worker.celery_app:celery",
        "worker",
        "--loglevel=info",
        "--concurrency=2",
    ])
    proc.wait()
    sys.exit(proc.returncode)
