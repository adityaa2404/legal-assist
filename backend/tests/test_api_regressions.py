"""API-level regression tests that avoid real LLM/identity calls."""

from unittest.mock import Mock

import pytest

from app.core import dependencies
from app.main import app
from app.api.v1 import analysis as analysis_api
from app.api.v1 import documents as documents_api

from .conftest import FakePIIService, FakeSessionService, SESSION_ID, make_session


def _override_session_service(service):
    app.dependency_overrides[dependencies.get_session_service] = lambda: service


def _clear_overrides():
    app.dependency_overrides.pop(dependencies.get_session_service, None)
    app.dependency_overrides.pop(dependencies.get_pii_service, None)
    app.dependency_overrides.pop(dependencies.get_gemini_client, None)
    app.dependency_overrides.pop(dependencies.get_tree_search, None)


def test_health_contract(authenticated_client):
    response = authenticated_client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert set(("status", "api_status", "worker_status")).issubset(body)
    assert body["api_status"] == "ok"
    assert body["worker_status"] != "healthy"


@pytest.mark.parametrize("path", ["/api/v1/history", "/api/v1/clause-library"])
def test_protected_endpoints_reject_anonymous(anonymous_client, path):
    response = anonymous_client.get(path)

    assert response.status_code in (401, 403)


def test_htoc_status_rejects_missing_session(authenticated_client):
    service = FakeSessionService()
    service.session = make_session(session_id="missing")

    # The requested id must not match the stored session.
    _override_session_service(service)
    try:
        response = authenticated_client.get(
            "/api/v1/htoc-status",
            headers={"X-Session-ID": SESSION_ID},
        )
    finally:
        _clear_overrides()

    assert response.status_code == 404
    assert response.json()["detail"] == "Session expired or not found"


def test_chat_rejects_session_still_processing(authenticated_client):
    service = FakeSessionService(
        session=make_session(
            anonymized_text="",
            page_texts=[],
            htoc_status="processing",
        )
    )

    _override_session_service(service)
    app.dependency_overrides[dependencies.get_pii_service] = FakePIIService()
    try:
        response = authenticated_client.post(
            "/api/v1/chat",
            headers={"X-Session-ID": SESSION_ID},
            json={"message": "What is the notice period?", "history": []},
        )
    finally:
        _clear_overrides()

    assert response.status_code == 202
    assert "still being processed" in response.json()["detail"]


def test_chat_cached_response_is_deanonymized(authenticated_client):
    token = "[PERSON_1]"
    service = FakeSessionService(
        session=make_session(pii_mapping={"Alice": token}),
        cached={
            "response": f"{token} signed the agreement.",
            "source_sections": [],
            "retrieval_confidence": "high",
        },
    )

    _override_session_service(service)
    app.dependency_overrides[dependencies.get_pii_service] = FakePIIService()
    try:
        response = authenticated_client.post(
            "/api/v1/chat",
            headers={"X-Session-ID": SESSION_ID},
            json={"message": "Who signed it?", "history": []},
        )
    finally:
        _clear_overrides()

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "Alice signed the agreement."
    assert body["retrieval_confidence"] == "high"


def test_upload_rejects_unsupported_file_type_before_processing(authenticated_client):
    response = authenticated_client.post(
        "/api/v1/upload",
        files={"file": ("malware.exe", b"not a pdf", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only PDF and DOCX supported"


def test_report_generation_is_idempotent_while_pending(authenticated_client, monkeypatch):
    service = FakeSessionService()
    _override_session_service(service)
    try:
        delay = Mock()
        monkeypatch.setattr(analysis_api.generate_report, "delay", delay)

        first = authenticated_client.post(
            "/api/v1/analyze/report/generate",
            headers={"X-Session-ID": SESSION_ID},
        )
        second = authenticated_client.post(
            "/api/v1/analyze/report/generate",
            headers={"X-Session-ID": SESSION_ID},
        )
    finally:
        _clear_overrides()

    assert first.status_code == 200
    assert first.json() == {"status": "pending"}
    assert second.status_code == 200
    assert second.json() == {"status": "pending"}
    delay.assert_called_once_with(SESSION_ID, "full")
    assert service.report_status_calls == 1


def test_analysis_risk_score_floor_prevents_zero_for_real_risks():
    # Exercise the same normalization logic used before the API model is built.
    from app.api.v1.analysis import _normalize_result

    result = _normalize_result(
        {
            "summary": "summary",
            "document_type": "contract",
            "parties": [],
            "key_clauses": [],
            "risks": [
                {
                    "risk_title": "Termination",
                    "severity": "high",
                    "description": "Risk",
                    "recommendation": "Review",
                }
            ],
            "obligations": "Pay on time",
            "missing_clauses": "Notice",
            "overall_risk_score": 0,
        }
    )

    assert result["obligations"] == [{"description": "Pay on time"}]
    assert result["missing_clauses"] == ["Notice"]
