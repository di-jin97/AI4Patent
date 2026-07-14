from .base import SearchProvider, SearchRequest, SearchResponse, SearchResult, FetchRequest, FetchResponse, FetchResult
from .exa import ExaAdapter
from .google_patents import GooglePatentsAdapter
from .fake import FakeSearchProvider
from .opencode_mcp_bridge import OpenCodeMCPBridge

__all__ = [
    "SearchProvider",
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
    "FetchRequest",
    "FetchResponse",
    "FetchResult",
    "ExaAdapter",
    "GooglePatentsAdapter",
    "FakeSearchProvider",
    "OpenCodeMCPBridge",
]
