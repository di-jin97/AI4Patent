"""Source-independent patent data ToolCall contracts and providers."""

from .contracts import (
    BiblioRequest,
    BiblioResponse,
    PassageSearchRequest,
    PassageSearchResponse,
    PatentBiblio,
    PatentSearchRequest,
    PatentSearchResponse,
    PatentSearchResult,
    SectionRequest,
    SectionResponse,
    TextSection,
)
from .google_patents import GooglePatentsProvider

__all__ = [
    "BiblioRequest", "BiblioResponse", "GooglePatentsProvider",
    "PassageSearchRequest", "PassageSearchResponse", "PatentBiblio",
    "PatentSearchRequest", "PatentSearchResponse", "PatentSearchResult",
    "SectionRequest", "SectionResponse", "TextSection",
]
