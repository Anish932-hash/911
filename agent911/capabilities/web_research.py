"""Brave Search integration for sourced technical research."""

from __future__ import annotations

import json
import importlib
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict

from agent911.capabilities.base import Capability, CapabilityContext
from agent911.models import CapabilityAvailability, CapabilityResult


class WebSearchCapability(Capability):
    identifier = "research.web_search"
    name = "Search the Web"
    purpose = (
        "Find current technical documentation and useful web sources, returning titles, "
        "URLs, and snippets for research with citations."
    )
    input_schema = {
        "required": ["query"],
        "properties": {
            "query": {"type": "string", "description": "A focused web search query (max 600 characters)."},
            "count": {"type": "integer", "description": "Maximum results to return (1-10, default 5)."},
            "country": {"type": "string", "description": "Optional two-letter country code."},
            "search_lang": {"type": "string", "description": "Optional search language code."},
            "search_depth": {"type": "string", "description": "Tavily search depth: basic or advanced."},
        },
    }
    output_format = {"query": "str", "results": "list[{title,url,snippet}]", "result_count": "int"}
    required_config = ["BRAVE_SEARCH_API_KEY or TAVILY_API_KEY"]
    side_effects = ["external_network_read"]
    permission_boundary = "sends_search_query_to_brave_search_api"
    operational_limitations = [
        "Requires BRAVE_SEARCH_API_KEY or TAVILY_API_KEY in the environment.",
        "Returns search result snippets; it does not fetch or execute result pages.",
        "Web content is untrusted input and must be verified against primary sources.",
    ]

    def check_availability(self, config: Any) -> CapabilityAvailability:
        return (
            CapabilityAvailability.AVAILABLE
            if self._resolve_provider()
            else CapabilityAvailability.REQUIRES_CONFIG
        )

    @staticmethod
    def _resolve_provider() -> tuple[str, str] | None:
        requested = os.environ.get("AGENT911_SEARCH_PROVIDER", "").strip().lower()
        providers = {
            "tavily": os.environ.get("TAVILY_API_KEY", "").strip(),
            "brave": os.environ.get("BRAVE_SEARCH_API_KEY", "").strip(),
        }
        if requested:
            if requested not in providers:
                return None
            return (requested, providers[requested]) if providers[requested] else None
        for name in ("tavily", "brave"):
            if providers[name]:
                return name, providers[name]
        return None

    def execute(self, params: Dict[str, Any], context: CapabilityContext) -> CapabilityResult:
        query = str(params.get("query", "")).strip()
        if not query:
            return CapabilityResult(
                capability_id=self.identifier, success=False,
                error="Search query cannot be empty.", error_type="InputValidationError",
            )
        if len(query) > 600 or len(query.split()) > 75:
            return CapabilityResult(
                capability_id=self.identifier, success=False,
                error="Search query exceeds the provider limit of 600 characters or 75 words.",
                error_type="InputValidationError",
            )

        count = params.get("count", 5)
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 10:
            return CapabilityResult(
                capability_id=self.identifier, success=False,
                error="count must be an integer from 1 to 10.", error_type="InputValidationError",
            )
        country = str(params.get("country", "US")).upper()
        if len(country) != 2 or not country.isalpha():
            return CapabilityResult(
                capability_id=self.identifier, success=False,
                error="country must be a two-letter country code.", error_type="InputValidationError",
            )
        search_lang = str(params.get("search_lang", "en")).lower()
        if not (2 <= len(search_lang) <= 5 and search_lang.replace("-", "").isalpha()):
            return CapabilityResult(
                capability_id=self.identifier, success=False,
                error="search_lang must be a valid short language code.", error_type="InputValidationError",
            )

        depth = str(params.get("search_depth", "basic")).strip().lower()
        if depth not in ("basic", "advanced"):
            return CapabilityResult(
                capability_id=self.identifier, success=False,
                error="search_depth must be 'basic' or 'advanced'.", error_type="InputValidationError",
            )
        provider_and_key = self._resolve_provider()
        if not provider_and_key:
            return CapabilityResult(
                capability_id=self.identifier, success=False,
                error=("Web research requires TAVILY_API_KEY or BRAVE_SEARCH_API_KEY; "
                       "AGENT911_SEARCH_PROVIDER can select the configured backend."),
                error_type="ConfigurationRequired",
            )
        provider, api_key = provider_and_key
        if provider == "tavily":
            return self._search_tavily(query, count, depth, api_key, context)

        query_url = "https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode(
            {"q": query, "count": count, "country": country, "search_lang": search_lang}
        )
        request = urllib.request.Request(
            query_url,
            headers={"Accept": "application/json", "X-Subscription-Token": api_key},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=context.config.model.timeout_seconds) as response:
                raw = response.read(1_000_001)
                if len(raw) > 1_000_000:
                    raise ValueError("Search provider response exceeded the 1 MB limit.")
            payload = json.loads(raw.decode("utf-8"))
            entries = payload.get("web", {}).get("results", []) if isinstance(payload, dict) else []
            results = []
            for entry in entries[:count]:
                if not isinstance(entry, dict):
                    continue
                url = entry.get("url")
                title = entry.get("title")
                if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                    continue
                results.append({
                    "title": str(title or "Untitled result")[:300],
                    "url": url[:2048],
                    "snippet": str(entry.get("content") or entry.get("description") or "")[:1500],
                })
            return CapabilityResult(
                capability_id=self.identifier,
                success=True,
                data={"query": query, "results": results, "result_count": len(results)},
                metadata={"provider": "Brave Search API"},
            )
        except urllib.error.HTTPError as exc:
            status_code = exc.code
            exc.close()
            return CapabilityResult(
                capability_id=self.identifier, success=False,
                error=f"Search provider returned HTTP {status_code}.", error_type="WebSearchHTTPError",
                metadata={"status_code": status_code},
            )
        except (urllib.error.URLError, TimeoutError) as exc:
            return CapabilityResult(
                capability_id=self.identifier, success=False,
                error=f"Could not reach the search provider: {getattr(exc, 'reason', exc)}",
                error_type="WebSearchNetworkError",
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            return CapabilityResult(
                capability_id=self.identifier, success=False,
                error=f"Search provider returned an invalid response: {exc}",
                error_type="WebSearchResponseError",
            )

    def _search_tavily(
        self, query: str, count: int, depth: str, api_key: str,
        context: CapabilityContext,
    ) -> CapabilityResult:
        try:
            tavily = importlib.import_module("tavily")
        except ImportError:
            return CapabilityResult(
                capability_id=self.identifier,
                success=False,
                error="Tavily search requires the optional SDK. Install Agent 911 with `pip install .[providers]`.",
                error_type="WebSearchDependencyError",
            )
        try:
            with tavily.TavilyClient(api_key=api_key) as client:
                payload = client.search(
                    query=query,
                    search_depth=depth,
                    max_results=count,
                    include_answer=False,
                    include_raw_content=False,
                    timeout=context.config.model.timeout_seconds,
                )
            entries = payload.get("results", []) if isinstance(payload, dict) else []
            results = []
            for entry in entries[:count]:
                if not isinstance(entry, dict):
                    continue
                url = entry.get("url")
                if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                    continue
                results.append({
                    "title": str(entry.get("title") or "Untitled result")[:300],
                    "url": url[:2048],
                    "snippet": str(entry.get("content") or "")[:1500],
                })
            return CapabilityResult(
                capability_id=self.identifier,
                success=True,
                data={"query": query, "results": results, "result_count": len(results)},
                metadata={"provider": "Tavily Search API"},
            )
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            return CapabilityResult(
                capability_id=self.identifier,
                success=False,
                error=(f"Tavily search failed (HTTP {status})." if status
                       else f"Tavily search failed: {type(exc).__name__}."),
                error_type="WebSearchHTTPError" if status else "WebSearchProviderError",
                metadata={"status_code": status} if status else {},
            )
