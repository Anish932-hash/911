"""SDK routing and response normalization tests for Groq."""

from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agent911.config import ModelConfig
from agent911.model_provider import ModelInterface


class TestGroqSDKRouting(unittest.TestCase):
    def test_groq_endpoint_uses_official_sdk_and_normalizes_completion(self) -> None:
        instances = []

        class FakeCompletion:
            def model_dump(self, exclude_none=False):
                return {
                    "choices": [{"message": {"content": '{"ok": true}'}}],
                    "usage": {"total_tokens": 7},
                }

        class FakeClient:
            def __init__(self, **kwargs):
                self.options = kwargs
                self.closed = False
                self.chat = SimpleNamespace(completions=SimpleNamespace(
                    create=lambda **body: self._create(body)
                ))
                instances.append(self)

            def _create(self, body):
                self.body = body
                return FakeCompletion()

            def close(self):
                self.closed = True

        cfg = ModelConfig(
            provider="openai_compatible",
            endpoint="https://api.groq.com/openai/v1/chat/completions",
            model_id="openai/gpt-oss-120b",
            api_key_env="GROQ_API_KEY",
        )
        interface = ModelInterface(cfg)
        fake_groq = SimpleNamespace(Groq=FakeClient)
        with patch.dict(sys.modules, {"groq": fake_groq}):
            response, status = interface._execute_http_request_with_config(
                cfg, "system", "user", "test-secret", True
            )

        self.assertEqual(status, 200)
        self.assertEqual(response.structured_data, {"ok": True})
        self.assertEqual(response.usage["total_tokens"], 7)
        self.assertEqual(instances[0].options["base_url"], "https://api.groq.com")
        self.assertEqual(instances[0].options["api_key"], "test-secret")
        self.assertEqual(instances[0].options["max_retries"], 0)
        self.assertEqual(instances[0].body["messages"][-1]["content"], "user")
        self.assertTrue(instances[0].closed)


if __name__ == "__main__":
    unittest.main()
