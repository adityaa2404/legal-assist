"""Shared test fixtures.

Tests use local CI service containers for Mongo/Redis and replace external
identity/LLM services with deterministic fakes. Environment is seeded before
the application is imported so a developer's .env cannot redirect tests to a
real production service.
"""

import os
from datetime import datetime, timezone
from types import SimpleNamespace

os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("MONGO_DB_NAME", "legal-assist-test")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CORS_ORIGINS", '["http://localhost:5173"]')

import pytest
from fastapi.testclient import TestClient

from app.core import dependencies
from app.main import app

TEST_USER = "ci-user@example.com"
SESSION_ID = "00000000-0000-4000-8000-000000000001"


def make_session(**overrides):
    values = {
        "session_id": SESSION_ID,
        "user_email": TEST_USER,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc),
        "pii_mapping": {},
        "anonymized_text": "This is a test legal document.",
        "page_texts": ["This is a test legal document."],
        "page_chunks": [],
        "htoc_tree": None,
        "bm25_data": None,
        "htoc_status": "ready",
        "ai_provider": "gemini",
        "document_metadata": {
            "filename": "contract.pdf",
            "page_count": 1,
            "size_bytes": 123,
        },
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakePIIService:
    async def anonymize_with_known_mapping(self, text, mapping):
        return text

    def deanonymize(self, text, mapping):
        result = text
        for original, replacement in mapping.items():
            result = result.replace(replacement, original)
        return result


class FakeSessionService:
    def __init__(self, session=None, cached=None):
        self.session = session or make_session()
        self.cached = cached
        self.report_status = None
        self.report_status_calls = 0

    async def get_for_user(self, session_id, user_email):
        if session_id != self.session.session_id:
            return None
        if self.session.user_email and self.session.user_email != user_email:
            return None
        return self.session

    async def get(self, session_id):
        return self.session if session_id == self.session.session_id else None

    async def get_cached_chat(self, session_id, query_hash):
        return self.cached

    async def set_report_status(self, session_id, report_type, status):
        self.report_status = status
        self.report_status_calls += 1

    async def get_report_status(self, session_id, report_type):
        return self.report_status


@pytest.fixture
def anonymous_client():
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def authenticated_client():
    app.dependency_overrides[dependencies.get_current_user] = lambda: TEST_USER
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
