"""Small regression tests for security and infrastructure invariants."""

from app.core import observability
from app.worker.celery_app import celery
from app.worker_entry import build_celery_command


def test_sensitive_fields_are_redacted_recursively():
    payload = observability._safe(
        {
            "prompt": "secret prompt",
            "nested": {
                "token": "secret token",
                "safe": "visible",
            },
            "items": [{"password": "secret password"}],
        }
    )

    assert payload["prompt"] == "[REDACTED]"
    assert payload["nested"]["token"] == "[REDACTED]"
    assert payload["nested"]["safe"] == "visible"
    assert payload["items"][0]["password"] == "[REDACTED]"


def test_celery_uses_command_sparing_redis_polling():
    transport = celery.conf.broker_transport_options

    assert transport["polling_interval"] == 30
    assert transport["health_check_interval"] == 30


def test_worker_runs_without_celery_heartbeat():
    command = build_celery_command()

    assert "--without-heartbeat" in command
    assert "--without-gossip" in command
    assert "--without-mingle" in command
