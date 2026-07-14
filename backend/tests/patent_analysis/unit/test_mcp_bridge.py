from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from backend.patent_analysis.adapters.opencode_mcp_bridge import (
    OpenCodeMCPBridge,
    OpenCodeMCPBridgeError,
    decode_tool_result,
)


def test_bridge_uses_environment_key_without_hard_coding(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-exa-key")

    bridge = OpenCodeMCPBridge()

    assert bridge.url == "https://mcp.exa.ai/mcp"
    assert bridge.headers == {"x-api-key": "test-exa-key"}


def test_decode_tool_result_prefers_structured_content():
    result = SimpleNamespace(
        structuredContent={"results": [{"title": "Patent"}]},
        content=[SimpleNamespace(text='{"ignored": true}')],
    )

    assert decode_tool_result(result) == {"results": [{"title": "Patent"}]}


def test_decode_tool_result_decodes_json_text_and_plain_text():
    json_result = SimpleNamespace(
        structuredContent=None,
        content=[SimpleNamespace(text='{"results": [{"url": "https://example.test"}]}')],
    )
    text_result = SimpleNamespace(
        structuredContent=None,
        content=[SimpleNamespace(text="plain result")],
    )

    assert decode_tool_result(json_result)["results"][0]["url"] == "https://example.test"
    assert decode_tool_result(text_result) == "plain result"


@pytest.mark.asyncio
async def test_bridge_wraps_transport_errors_without_leaking_headers(monkeypatch):
    bridge = OpenCodeMCPBridge(url="https://unreachable.example/mcp", headers={"x-api-key": "secret"})

    @asynccontextmanager
    async def failing_transport(*args, **kwargs):
        raise RuntimeError("network down")
        yield

    monkeypatch.setattr("mcp.client.streamable_http.streamable_http_client", failing_transport)

    with pytest.raises(OpenCodeMCPBridgeError) as raised:
        await bridge.execute("exa_web_search_exa", {"query": "cache"})

    assert "network down" in str(raised.value)
    assert "secret" not in str(raised.value)
