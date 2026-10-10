import unittest

from app.services.jev_client import parse_intent_response


class JevIntentResponseTests(unittest.TestCase):
    def test_accepts_each_supported_intent(self):
        for intent in ("exhaustive", "comparative", "targeted"):
            with self.subTest(intent=intent):
                self.assertEqual(
                    parse_intent_response({"answers": {"query_intent": {"choice": intent}}}),
                    intent,
                )

    def test_rejects_unknown_intent(self):
        self.assertIsNone(
            parse_intent_response({"answers": {"query_intent": {"choice": "legal_advice"}}})
        )

    def test_rejects_malformed_payloads(self):
        for payload in ({}, {"answers": {}}, {"answers": {"query_intent": None}}, None):
            with self.subTest(payload=payload):
                self.assertIsNone(parse_intent_response(payload))


if __name__ == "__main__":
    unittest.main()
