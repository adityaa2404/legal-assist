import os
import unittest
from unittest.mock import AsyncMock, patch

# Supply only the required settings for import-time configuration in isolated tests.
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")

from app.api.v1 import chat


class QueryUnderstandingIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_codiv_overrides_intent_but_preserves_gemini_expansion(self):
        gemini = unittest.mock.Mock()
        gemini.generate_json = AsyncMock(return_value={
            "intent": "targeted",
            "expanded_query": "lease termination early cancellation notice period",
            "key_terms": ["termination", "notice", "lease"],
        })

        with (
            patch.object(chat.settings, "TYPESAFE_API_KEY", "test-key"),
            patch.object(
                chat,
                "classify_query_intent",
                new=AsyncMock(return_value="comparative"),
            ) as classify,
        ):
            result = await chat._understand_query(
                "Compare early termination options", gemini, "gemini"
            )

        self.assertEqual(result, {
            "intent": "comparative",
            "expanded_query": "lease termination early cancellation notice period",
            "key_terms": ["termination", "notice", "lease"],
        })
        classify.assert_awaited_once_with(
            "Compare early termination options", "test-key"
        )

    async def test_codiv_failure_preserves_gemini_intent_and_expansion(self):
        gemini = unittest.mock.Mock()
        gemini.generate_json = AsyncMock(return_value={
            "intent": "exhaustive",
            "expanded_query": "all termination rights and notice periods",
            "key_terms": ["termination", "rights", "notice"],
        })

        with (
            patch.object(chat.settings, "TYPESAFE_API_KEY", "test-key"),
            patch.object(
                chat,
                "classify_query_intent",
                new=AsyncMock(return_value=None),
            ),
        ):
            result = await chat._understand_query(
                "List all termination rights", gemini, "gemini"
            )

        self.assertEqual(result, {
            "intent": "exhaustive",
            "expanded_query": "all termination rights and notice periods",
            "key_terms": ["termination", "rights", "notice"],
        })

    async def test_missing_codiv_key_keeps_existing_gemini_result(self):
        gemini = unittest.mock.Mock()
        gemini.generate_json = AsyncMock(return_value={
            "intent": "targeted",
            "expanded_query": "assignment consent requirements",
            "key_terms": ["assignment", "consent"],
        })

        with (
            patch.object(chat.settings, "TYPESAFE_API_KEY", None),
            patch.object(
                chat,
                "classify_query_intent",
                new=AsyncMock(return_value=None),
            ) as classify,
        ):
            result = await chat._understand_query(
                "Is consent needed for assignment?", gemini, "gemini"
            )

        self.assertEqual(result["intent"], "targeted")
        self.assertEqual(result["expanded_query"], "assignment consent requirements")
        self.assertEqual(result["key_terms"], ["assignment", "consent"])
        classify.assert_awaited_once_with(
            "Is consent needed for assignment?", None
        )


if __name__ == "__main__":
    unittest.main()
