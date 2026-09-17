#!/bin/sh
set -u

PROM_CONFIG="/tmp/prometheus.yml"
PROM_DATA_DIR="${PROMETHEUS_DATA_DIR:-/tmp/prometheus-data}"
PROM_RETENTION="${PROMETHEUS_RETENTION:-24h}"

mkdir -p "$PROM_DATA_DIR"

python - <<'PY'
from pathlib import Path
from urllib.parse import urlparse
import os

src = Path("/app/prometheus.yml.template").read_text()

worker_target = os.getenv("WORKER_METRICS_TARGET", "").strip()
worker_block = ""

if worker_target:
    raw = (
        worker_target
        if "://" in worker_target
        else f"https://{worker_target}"
    )

    parsed = urlparse(raw)

    if not parsed.hostname:
        raise SystemExit(
            "WORKER_METRICS_TARGET must be a hostname or URL"
        )

    scheme = parsed.scheme or "https"
    path = parsed.path or "/metrics"

    if parsed.query:
        path += "?" + parsed.query

    port = f":{parsed.port}" if parsed.port else ""

    worker_block = f"""  - job_name: legal-assist-worker
    scheme: {scheme}
    metrics_path: {path}
    static_configs:
      - targets:
          - {parsed.hostname}{port}
"""

remote_url = os.getenv(
    "GRAFANA_CLOUD_REMOTE_WRITE_URL",
    ""
).strip()

remote_user = os.getenv(
    "GRAFANA_CLOUD_USERNAME",
    ""
).strip()

remote_password = os.getenv(
    "GRAFANA_CLOUD_API_KEY",
    ""
).strip()

remote_block = ""

if any((remote_url, remote_user, remote_password)):
    if not all((remote_url, remote_user, remote_password)):
        raise SystemExit(
            "Grafana Cloud remote_write requires "
            "GRAFANA_CLOUD_REMOTE_WRITE_URL, "
            "GRAFANA_CLOUD_USERNAME, and "
            "GRAFANA_CLOUD_API_KEY together"
        )

    def q(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    remote_block = f"""remote_write:
  - url: {q(remote_url)}
    basic_auth:
      username: {q(remote_user)}
      password: {q(remote_password)}
"""

out = src.replace(
    "__WORKER_SCRAPE_BLOCK__",
    worker_block.rstrip()
)

out = out.replace(
    "__REMOTE_WRITE_BLOCK__",
    remote_block.rstrip()
)

Path("/tmp/prometheus.yml").write_text(out)
PY

prometheus \
  --config.file="$PROM_CONFIG" \
  --storage.tsdb.path="$PROM_DATA_DIR" \
  --storage.tsdb.retention.time="$PROM_RETENTION" \
  --web.listen-address=127.0.0.1:9090 &

PROM_PID=$!

echo "Starting Prometheus..."

PROM_READY=false

for i in $(seq 1 20); do
    if curl -fsS \
        http://127.0.0.1:9090/-/ready \
        >/dev/null 2>&1
    then
        PROM_READY=true
        echo "Prometheus is ready"
        break
    fi

    if ! kill -0 "$PROM_PID" 2>/dev/null; then
        echo "Prometheus exited unexpectedly"
        exit 1
    fi

    sleep 1
done

if [ "$PROM_READY" != "true" ]; then
    echo "Prometheus failed to become ready"
    exit 1
fi

cleanup() {
    kill -TERM "$PROM_PID" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-7860}" &

API_PID=$!

wait "$API_PID"
STATUS=$?

kill -TERM "$PROM_PID" 2>/dev/null || true

wait "$PROM_PID" 2>/dev/null || true

exit "$STATUS"