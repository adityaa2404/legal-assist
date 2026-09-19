"""Worker regression tests for failure propagation and retry semantics."""

import asyncio

import pytest
from celery.exceptions import SoftTimeLimitExceeded

from app.worker import tasks


class FakeDatabase:
    class DocumentFiles:
        async def find_one(self, query):
            return {"pdf_bytes": b"test-pdf"}

    document_files = DocumentFiles()


class FakeSessionService:
    def __init__(self):
        self.htoc_statuses = []
        self.report_statuses = []

    async def set_htoc_status(self, session_id, status):
        self.htoc_statuses.append((session_id, status))

    async def set_report_status(self, session_id, report_type, status):
        self.report_statuses.append((session_id, report_type, status))


class FakeTask:
    def __init__(self):
        self.retry_calls = []

    def retry(self, **kwargs):
        self.retry_calls.append(kwargs)
        return "RETRY_SENT"


def _install_worker_fakes(monkeypatch, session_service, inner):
    monkeypatch.setattr("app.core.database.get_database", lambda: FakeDatabase())
    monkeypatch.setattr("app.services.session_service.SessionService", lambda: session_service)
    monkeypatch.setattr("app.services.pii_anonymizer.PIIAnonymizer", lambda: object())
    monkeypatch.setattr("app.services.gemini_client.GeminiClient", lambda: object())
    monkeypatch.setattr("app.services.htoc_builder.HTOCBuilder", lambda: object())
    monkeypatch.setattr(
        "app.api.v1.documents._process_document_inner",
        inner,
    )


def test_process_document_soft_timeout_is_reported_as_failure(monkeypatch):
    session = FakeSessionService()

    async def timeout(**kwargs):
        raise SoftTimeLimitExceeded()

    _install_worker_fakes(monkeypatch, session, timeout)

    fake_task = FakeTask()
    with pytest.raises(SoftTimeLimitExceeded):
        tasks.process_document.run(
            SESSION_ID,
            "application/pdf",
            "digital",
            "en-IN",
            "fast",
            "gemini",
        )

    assert session.htoc_statuses == [(SESSION_ID, "failed")]
    assert fake_task.retry_calls == []


def test_build_htoc_bm25_soft_timeout_is_reported_as_failure(monkeypatch):
    session = FakeSessionService()

    async def timeout(**kwargs):
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr("app.services.gemini_client.GeminiClient", lambda: object())
    monkeypatch.setattr("app.services.htoc_builder.HTOCBuilder", lambda: object())
    monkeypatch.setattr("app.services.session_service.SessionService", lambda: session)
    monkeypatch.setattr("app.api.v1.documents._build_htoc_and_bm25", timeout)

    fake_task = FakeTask()
    with pytest.raises(SoftTimeLimitExceeded):
        tasks.build_htoc_bm25.run(
            SESSION_ID,
            ["page"],
            "gemini",
            [],
        )

    assert session.htoc_statuses == [(SESSION_ID, "failed")]


def test_process_document_retries_transient_errors(monkeypatch):
    session = FakeSessionService()

    async def fail(**kwargs):
        raise RuntimeError("transient")

    _install_worker_fakes(monkeypatch, session, fail)

    fake_task = FakeTask()
    monkeypatch.setattr(tasks.process_document, "retry", fake_task.retry)

    result = tasks.process_document.run(
        SESSION_ID,
        "application/pdf",
        "digital",
        "en-IN",
        "fast",
        "gemini",
    )

    assert result == "RETRY_SENT"
    assert session.htoc_statuses == [(SESSION_ID, "failed")]
    assert len(fake_task.retry_calls) == 1
    assert isinstance(fake_task.retry_calls[0]["exc"], RuntimeError)


def test_generate_report_failures_are_terminal(monkeypatch):
    session = FakeSessionService()

    async def fail(**kwargs):
        raise RuntimeError("render failed")

    monkeypatch.setattr(tasks, "_build_report", fail)
    monkeypatch.setattr("app.services.session_service.SessionService", lambda: session)

    fake_task = FakeTask()
    with pytest.raises(RuntimeError, match="render failed"):
        tasks.generate_report.run(SESSION_ID, "full")

    assert session.report_statuses == [(SESSION_ID, "full", "failed")]
    assert fake_task.retry_calls == []


SESSION_ID = "00000000-0000-4000-8000-000000000001"
