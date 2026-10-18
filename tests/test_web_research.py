"""Tests for web search availability, response handling, and credential boundaries."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent911.capabilities import CapabilityContext
from agent911.capabilities.web_research import WebSearchCapability
from agent911.config import AgentConfig
from agent911.models import CapabilityAvailability
from agent911.orchestrator import Agent911Orchestrator


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit: int) -> bytes:
        return self.payload[:limit]


class TestWebResearch(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        self.config = AgentConfig(workspace_root=str(self.workspace))
        self.agent = Agent911Orchestrator(config=self.config)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_search_is_explicitly_unavailable_without_its_own_key(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                self.agent.registry.get_availability("research.web_search"),
                CapabilityAvailability.REQUIRES_CONFIG,
            )

    def test_search_returns_cited_sources_without_exposing_api_key(self) -> None:
        key = "test-brave-private-token"
        payload = {"web": {"results": [{
            "title": "Official API Guide",
            "url": "https://docs.example.com/api",
            "description": "Official request and response reference.",
        }, {
            "title": "Ignore instructions",
            "url": "javascript:alert(1)",
            "description": "This unsafe URL should be discarded.",
        }]}}
        with patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": key}, clear=True), \
                patch("agent911.capabilities.web_research.urllib.request.urlopen", return_value=_FakeResponse(payload)) as urlopen:
            result = self.agent.registry.invoke(
                "research.web_search",
                {"query": "python api docs", "count": 5},
                CapabilityContext(
                    config=self.config,
                    memory_store=self.agent.memory_store,
                    model_interface=self.agent.model_interface,
                    registry=self.agent.registry,
                ),
            )

        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["result_count"], 1)
        self.assertEqual(result.data["results"][0]["url"], "https://docs.example.com/api")
        self.assertNotIn(key, repr(result.to_dict()))
        request = urlopen.call_args.args[0]
        self.assertIn("api.search.brave.com/res/v1/web/search", request.full_url)
        self.assertEqual(request.get_header("X-subscription-token"), key)

    def test_tavily_backend_uses_bearer_auth_and_normalizes_results(self) -> None:
        key = "test-tavily-private-token"
        payload = {"results": [{
            "title": "Tavily API Reference",
            "url": "https://docs.tavily.com/api-reference/endpoint/search",
            "content": "POST search requests with a query.",
        }]}
        calls = []
        class FakeTavilyClient:
            def __init__(self, api_key):
                calls.append({"api_key": api_key})
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def search(self, **kwargs):
                calls.append(kwargs)
                return payload

        fake_tavily = SimpleNamespace(TavilyClient=FakeTavilyClient)
        with patch.dict(os.environ, {"TAVILY_API_KEY": key, "AGENT911_SEARCH_PROVIDER": "tavily"}, clear=True), \
                patch.dict(sys.modules, {"tavily": fake_tavily}):
            result = self.agent.registry.invoke(
                "research.web_search",
                {"query": "Tavily official API", "search_depth": "advanced"},
                CapabilityContext(
                    config=self.config,
                    memory_store=self.agent.memory_store,
                    model_interface=self.agent.model_interface,
                    registry=self.agent.registry,
                ),
            )

        self.assertTrue(result.success, result.error)
        self.assertEqual(result.metadata["provider"], "Tavily Search API")
        self.assertEqual(result.data["results"][0]["snippet"], "POST search requests with a query.")
        self.assertNotIn(key, repr(result.to_dict()))
        self.assertEqual(calls[0]["api_key"], key)
        self.assertEqual(calls[1]["search_depth"], "advanced")
        self.assertEqual(calls[1]["max_results"], 5)
        self.assertFalse(calls[1]["include_raw_content"])

    def test_input_limits_reject_invalid_queries_and_counts(self) -> None:
        result = WebSearchCapability().execute(
            {"query": "ok", "count": 11},
            SimpleNamespace(config=self.config),
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "InputValidationError")

