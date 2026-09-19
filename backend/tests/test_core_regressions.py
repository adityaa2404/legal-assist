"""Small regression tests for security and infrastructure invariants."""

import asyncio

from app.api.v1 import health as health_api
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


def test_worker_health_status_is_cached_between_checks(monkeypatch):
    calls = 0

    async def fake_check_worker():
        nonlocal calls
        calls += 1
        return True

    monkeypatch.setattr(health_api, "_check_worker", fake_check_worker)
    monkeypatch.setattr(health_api.time, "monotonic", lambda: 100.0)
    monkeypatch.setitem(health_api._worker_status_cache, "checked_at", 50.0)
    monkeypatch.setitem(health_api._worker_status_cache, "healthy", False)

    assert asyncio.run(health_api.get_worker_status()) is True
    assert asyncio.run(health_api.get_worker_status()) is True
    assert calls == 1


def test_forced_worker_health_check_bypasses_cache(monkeypatch):
    calls = 0

    async def fake_check_worker():
        nonlocal calls
        calls += 1
        return calls > 1

    monkeypatch.setattr(health_api, "_check_worker", fake_check_worker)
    monkeypatch.setattr(health_api.time, "monotonic", lambda: 100.0)
    monkeypatch.setitem(health_api._worker_status_cache, "checked_at", 50.0)
    monkeypatch.setitem(health_api._worker_status_cache, "healthy", False)

    assert asyncio.run(health_api.get_worker_status()) is False
    assert asyncio.run(health_api.get_worker_status(force=True)) is True
    assert calls == 2


def test_worker_runs_without_celery_heartbeat():
    command = build_celery_command()

    assert "--without-heartbeat" in command
    assert "--without-gossip" in command
    assert "--without-mingle" in command
