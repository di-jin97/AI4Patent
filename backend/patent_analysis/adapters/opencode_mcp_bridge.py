"""Direct Streamable HTTP bridge for remote MCP tools.

The earlier implementation attempted to execute ``opencode mcp call``.  That
subcommand does not exist in the installed OpenCode CLI, so a new workflow
could never perform a real search.  This bridge is intentionally independent
from OpenCode: it talks to the configured MCP endpoint using the official MCP
Python client and can therefore be reused by other search providers.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import timedelta
from typing import Any

import httpx


DEFAULT_EXA_MCP_URL = "https://mcp.exa.ai/mcp"


class OpenCodeMCPBridgeError(RuntimeError):
    """Raised when a remote MCP tool request cannot be completed."""


class OpenCodeMCPBridge:
    """Execute a remote MCP tool through Streamable HTTP.

    The legacy class name is retained to avoid breaking the existing
    ``ExaAdapter`` API.  It no longer starts an OpenCode subprocess.
    """

    def __init__(
        self,
        url: str | None = None,
        *,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.url = url or os.environ.get("EXA_MCP_URL", DEFAULT_EXA_MCP_URL)
        self.headers = dict(headers or self._headers_from_environment())
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _headers_from_environment() -> dict[str, str]:
        """Use an optional Exa key without putting it in versioned config."""
        api_key = os.environ.get("EXA_API_KEY", "").strip()
        return {"x-api-key": api_key} if api_key else {}

    async def execute(self, tool_name: str, payload: dict[str, Any]) -> Any:
        """Call an MCP tool and return structured data or decoded text."""
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client

            timeout = httpx.Timeout(self.timeout_seconds)
            async with httpx.AsyncClient(
                headers=self.headers,
                timeout=timeout,
                follow_redirects=True,
            ) as client:
                async with streamable_http_client(
                    self.url, http_client=client
                ) as (read_stream, write_stream, _):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        result = await session.call_tool(
                            tool_name,
                            arguments=payload,
                            read_timeout_seconds=timedelta(seconds=self.timeout_seconds),
                        )
        except asyncio.TimeoutError as exc:
            raise OpenCodeMCPBridgeError(
                f"MCP tool {tool_name} timed out after {self.timeout_seconds:g} seconds"
            ) from exc
        except Exception as exc:
            raise OpenCodeMCPBridgeError(
                f"MCP tool {tool_name} failed via {self.url}: {type(exc).__name__}: {exc}"
            ) from exc

        if getattr(result, "isError", False):
            raise OpenCodeMCPBridgeError(
                f"MCP tool {tool_name} returned an error: {_tool_error_text(result)}"
            )
        return decode_tool_result(result)


def decode_tool_result(result: Any) -> Any:
    """Convert an MCP ``CallToolResult`` into Python data for adapters."""
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return structured

    texts: list[str] = []
    for content in getattr(result, "content", []) or []:
        text = getattr(content, "text", None)
        if isinstance(text, str):
            texts.append(text)
    if not texts:
        return None

    combined = "\n".join(texts)
    try:
        return json.loads(combined)
    except json.JSONDecodeError:
        return combined


def _tool_error_text(result: Any) -> str:
    value = decode_tool_result(result)
    if isinstance(value, str):
        return value[:500]
    return json.dumps(value, ensure_ascii=False, default=str)[:500]
