import unittest
from unittest.mock import AsyncMock, patch

from app.services import jev_client


VALID_INTENTS = ("targeted", "comparative", "exhaustive")


class FakeResponse:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self.payload


class FakeAsyncClient:
    def __init__(self, response=None, error=None, **kwargs):
        self.response = response
        self.error = error
        self.kwargs = kwargs
        self.post = AsyncMock(side_effect=self._post)

    async def _post(self, *args, **kwargs):
        if self.error:
            raise self.error
        return self.response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class CodivIntentClientTests(unittest.IsolatedAsyncioTestCase):
    def test_parses_all_supported_intents(self):
        for intent in VALID_INTENTS:
            with self.subTest(intent=intent):
                self.assertEqual(
                    jev_client.parse_intent_response({
                        "answers": {"query_intent": {"choice": intent}}
                    }),
                    intent,
                )

    def test_rejects_invalid_or_malformed_responses(self):
        invalid_payloads = [
            {},
            {"answers": {}},
            {"answers": {"query_intent": None}},
            {"answers": {"query_intent": {"choice": "legal_advice"}}},
            {"answers": {"query_intent": {"choice": None}}},
            {"answers": {"query_intent": {"choice": ["targeted"]}}},
            None,
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                self.assertIsNone(jev_client.parse_intent_response(payload))

    async def test_missing_key_skips_network_call(self):
        with patch.object(jev_client.httpx, "AsyncClient") as client:
            result = await jev_client.classify_query_intent(
                "Compare the two clauses", None
            )
        self.assertIsNone(result)
        client.assert_not_called()

    async def test_blank_query_skips_network_call(self):
        with patch.object(jev_client.httpx, "AsyncClient") as client:
            result = await jev_client.classify_query_intent("   ", "test-key")
        self.assertIsNone(result)
        client.assert_not_called()

    async def test_sends_codiv_request_and_parses_result(self):
        response = FakeResponse({
            "model": "openjev-0.1",
            "answers": {
                "query_intent": {
                    "type": "choice",
                    "choice": "comparative",
                    "confidence": 0.9,
                    "probabilities": {
                        "targeted": 0.05,
                        "comparative": 0.9,
                        "exhaustive": 0.05,
                    },
                }
            },
        })
        fake_client = FakeAsyncClient(response=response)

        with patch.object(
            jev_client.httpx, "AsyncClient", return_value=fake_client
        ) as client_factory:
            result = await jev_client.classify_query_intent(
                "Compare clauses 4 and 7", "test-secret"
            )

        self.assertEqual(result, "comparative")
        client_factory.assert_called_once_with(timeout=8.0)
        fake_client.post.assert_awaited_once()
        args, kwargs = fake_client.post.await_args
        self.assertEqual(args[0], "https://api.codiv.ai/v1/systemone")
        self.assertEqual(
            kwargs["headers"]["Authorization"], "Bearer test-secret"
        )
        self.assertEqual(kwargs["json"]["model"], "openjev-latest")
        self.assertEqual(kwargs["json"]["state"], "Compare clauses 4 and 7")
        self.assertEqual(
            kwargs["json"]["questions"]["query_intent"]["type"], "choice"
        )

    async def test_api_failure_returns_none(self):
        fake_client = FakeAsyncClient(error=RuntimeError("simulated API failure"))
        with patch.object(
            jev_client.httpx, "AsyncClient", return_value=fake_client
        ):
            result = await jev_client.classify_query_intent(
                "What is the notice period?", "test-secret"
            )
        self.assertIsNone(result)

    async def test_invalid_api_response_returns_none(self):
        fake_client = FakeAsyncClient(
            response=FakeResponse({"unexpected": "payload"})
        )
        with patch.object(
            jev_client.httpx, "AsyncClient", return_value=fake_client
        ):
            result = await jev_client.classify_query_intent(
                "What is the notice period?", "test-secret"
            )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
