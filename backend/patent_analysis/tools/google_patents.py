"""Google Patents fact provider with conservative access controls.

This module does not bypass robots, authentication, bot detection, or source
limits.  Production callers must explicitly opt in to direct access; tests use
an injected transport and never make a network request.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from html import unescape
from typing import Protocol
from urllib.parse import quote, quote_plus
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from .contracts import (
    BiblioRequest, BiblioResponse, PassageMatch, PassageSearchRequest,
    PassageSearchResponse, PatentBiblio, PatentSearchRequest, RelationsRequest,
    RelationsResponse, PatentRelations,
    PatentSearchResponse, PatentSearchResult, SectionRequest, SectionResponse,
    TextSection, ToolError,
)


BASE_URL = "https://patents.google.com"
USER_AGENT = "AI4Patent-Research/1.0 (+contact: local-admin)"


class GooglePatentsAccessError(RuntimeError):
    pass


class AsyncTransport(Protocol):
    async def __call__(self, url: str) -> str: ...


class GooglePatentsProvider:
    """Independent ToolCall provider for Google Patents source facts."""

    source = "google_patents"

    def __init__(
        self,
        *,
        direct_access_enabled: bool | None = None,
        min_interval_seconds: float = 1.0,
        transport: AsyncTransport | None = None,
    ) -> None:
        self.direct_access_enabled = (
            direct_access_enabled
            if direct_access_enabled is not None
            else os.environ.get("GOOGLE_PATENTS_DIRECT_ACCESS_ENABLED", "false").lower() == "true"
        )
        self.min_interval_seconds = min_interval_seconds
        self._transport = transport
        self._cache: dict[str, str] = {}
        self._last_request = 0.0
        self._lock = asyncio.Lock()
        self._robots: RobotFileParser | None = None

    async def search(self, request: PatentSearchRequest) -> PatentSearchResponse:
        query = _build_query(request)
        # The document page is a JavaScript shell.  Its own same-origin query
        # endpoint returns the rendered result facts as JSON; it is still
        # subject to the identical robots/rate/cache policy in ``_get``.
        presentation_url = f"{BASE_URL}/?q={quote_plus(query)}"
        encoded_query = quote(f"q={query}", safe="")
        url = f"{BASE_URL}/xhr/query?url={encoded_query}"
        if request.cursor:
            url += f"&page={quote(str(request.cursor), safe='')}"
        try:
            body = await self._get(url)
            try:
                results, next_cursor = parse_search_payload(json.loads(body))
            except (json.JSONDecodeError, TypeError, KeyError):
                # Kept for fixture compatibility and source layout changes.
                results, next_cursor = parse_search_html(body)
            return PatentSearchResponse(
                request_id=request.request_id, source=self.source, source_url=presentation_url,
                content_hash=_hash(body), results=results[:request.limit],
                next_cursor=next_cursor, query_echo=query,
            )
        except GooglePatentsAccessError as exc:
            return _failed_search(request.request_id, url, str(exc), "ACCESS_DISABLED")
        except httpx.HTTPStatusError as exc:
            return _failed_search(request.request_id, url, str(exc), f"HTTP_{exc.response.status_code}", exc.response.status_code in {429, 500, 502, 503, 504})
        except Exception as exc:
            return _failed_search(request.request_id, url, str(exc), "SOURCE_ERROR", True)

    async def get_biblio(self, request: BiblioRequest) -> BiblioResponse:
        url = patent_url(request.publication_number)
        try:
            html = await self._get(url)
            biblio = parse_biblio_html(html, request.publication_number, url)
            return BiblioResponse(request_id=request.request_id, source=self.source, source_url=url, content_hash=_hash(html), biblio=biblio)
        except GooglePatentsAccessError as exc:
            return BiblioResponse(request_id=request.request_id, status="failed", source=self.source, source_url=url, error=ToolError(code="ACCESS_DISABLED", message=str(exc)))
        except Exception as exc:
            return BiblioResponse(request_id=request.request_id, status="failed", source=self.source, source_url=url, error=ToolError(code="SOURCE_ERROR", message=str(exc), retryable=True))

    async def get_sections(self, request: SectionRequest) -> SectionResponse:
        url = patent_url(request.publication_number)
        try:
            html = await self._get(url)
            sections = parse_sections_html(html, request)
            return SectionResponse(
                request_id=request.request_id, source=self.source, source_url=url,
                content_hash=_hash(html), publication_number=request.publication_number,
                sections=sections, raw_artifact_id=f"sha256:{_hash(html)}",
                status="success" if sections else "partial",
                error=None if sections else ToolError(code="NO_SECTIONS", message="Source page returned no requested text sections"),
            )
        except GooglePatentsAccessError as exc:
            return SectionResponse(request_id=request.request_id, status="failed", source=self.source, source_url=url, publication_number=request.publication_number, error=ToolError(code="ACCESS_DISABLED", message=str(exc)))
        except Exception as exc:
            return SectionResponse(request_id=request.request_id, status="failed", source=self.source, source_url=url, publication_number=request.publication_number, error=ToolError(code="SOURCE_ERROR", message=str(exc), retryable=True))

    async def find_passages(self, request: PassageSearchRequest) -> PassageSearchResponse:
        sections = await self.get_sections(SectionRequest(
            request_id=request.request_id,
            publication_number=request.publication_number,
            sections=request.section_scope,
            max_characters=100_000,
        ))
        if sections.status == "failed":
            return PassageSearchResponse(request_id=request.request_id, status="failed", source=self.source, source_url=sections.source_url, publication_number=request.publication_number, error=sections.error)
        matches: list[PassageMatch] = []
        for feature in request.feature_texts:
            terms = _keywords(feature)
            scored = []
            for section in sections.sections:
                score = _keyword_score(terms, section.text)
                if score:
                    scored.append((score, section))
            for score, section in sorted(scored, key=lambda item: item[0], reverse=True)[:request.max_passages_per_feature]:
                matches.append(PassageMatch(feature_text=feature, locator=section.locator, text=section.text, score=score, content_hash=section.content_hash))
        return PassageSearchResponse(request_id=request.request_id, source=self.source, source_url=sections.source_url, publication_number=request.publication_number, matches=matches)

    async def get_relations(self, request: RelationsRequest) -> RelationsResponse:
        """Return only relations explicitly present in source HTML.

        Relation markup varies by jurisdiction/page version. Missing markup is
        reported as unavailable instead of being inferred.
        """
        url = patent_url(request.publication_number)
        try:
            html = await self._get(url)
            relations = parse_relations_html(html)
            return RelationsResponse(request_id=request.request_id, source=self.source, source_url=url, content_hash=_hash(html), publication_number=request.publication_number, relations=relations, status="success" if relations.completeness != "unavailable" else "partial")
        except GooglePatentsAccessError as exc:
            return RelationsResponse(request_id=request.request_id, status="failed", source=self.source, source_url=url, publication_number=request.publication_number, error=ToolError(code="ACCESS_DISABLED", message=str(exc)))
        except Exception as exc:
            return RelationsResponse(request_id=request.request_id, status="failed", source=self.source, source_url=url, publication_number=request.publication_number, error=ToolError(code="SOURCE_ERROR", message=str(exc), retryable=True))

    async def _get(self, url: str) -> str:
        if url in self._cache:
            return self._cache[url]
        if self._transport is not None:
            content = await self._transport(url)
            self._cache[url] = content
            return content
        if not self.direct_access_enabled:
            raise GooglePatentsAccessError("Direct Google Patents access is disabled; set GOOGLE_PATENTS_DIRECT_ACCESS_ENABLED=true after confirming source access policy")
        await self._respect_access_policy(url)
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            self._cache[url] = response.text
            return response.text

    async def _respect_access_policy(self, url: str) -> None:
        async with self._lock:
            if self._robots is None:
                async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=15) as client:
                    robots = await client.get(f"{BASE_URL}/robots.txt")
                    robots.raise_for_status()
                parser = RobotFileParser()
                parser.parse(robots.text.splitlines())
                self._robots = parser
            if not self._robots.can_fetch(USER_AGENT, url):
                raise GooglePatentsAccessError("robots.txt disallows this request for the configured user agent")
            delay = self.min_interval_seconds - (time.monotonic() - self._last_request)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request = time.monotonic()


def patent_url(publication_number: str) -> str:
    normalized = re.sub(r"[\s,]", "", publication_number).upper()
    return f"{BASE_URL}/patent/{normalized}/en"


def parse_search_html(html: str) -> tuple[list[PatentSearchResult], str | None]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[PatentSearchResult] = []
    for item in soup.select("article.search-result-item, search-result-item"):
        link = item.select_one("a[href*='/patent/']")
        if not link or not link.get("href"):
            continue
        href = str(link["href"])
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        title = _text(item.select_one("h3, .title, [itemprop='title']")) or _text(link)
        publication_number = _text(item.select_one("span[itemprop='publicationNumber'], .publication-number")) or _publication_from_url(url)
        results.append(PatentSearchResult(
            publication_number=publication_number,
            title=title,
            url=url,
            snippet=_text(item.select_one(".snippet, [itemprop='snippet'], .abstract")),
            publication_date=_text(item.select_one("time[itemprop='publicationDate'], .publication-date")) or None,
            assignee=_text(item.select_one("[itemprop='assigneeOriginal'], .assignee")) or None,
            inventors=_texts(item.select("[itemprop='inventor'], .inventor")),
            cpc=_texts(item.select("[itemprop='cpc'], .cpc")),
        ))
    next_link = soup.select_one("a[rel='next'], a.next")
    next_cursor = str(next_link.get("href")) if next_link and next_link.get("href") else None
    return results, next_cursor


def parse_search_payload(payload: dict) -> tuple[list[PatentSearchResult], str | None]:
    """Normalize the public page's result payload without adding conclusions."""
    result_root = payload.get("results", {})
    clusters = result_root.get("cluster", []) if isinstance(result_root, dict) else []
    results: list[PatentSearchResult] = []
    for cluster in clusters:
        for item in cluster.get("result", []) if isinstance(cluster, dict) else []:
            patent = item.get("patent", {}) if isinstance(item, dict) else {}
            identifier = str(item.get("id", ""))
            number = str(patent.get("publication_number", "")).strip() or _publication_from_url(identifier)
            if not number:
                continue
            path = identifier.lstrip("/") or f"patent/{number}/en"
            results.append(PatentSearchResult(
                publication_number=number,
                title=unescape(str(patent.get("title", "")).strip()),
                url=f"{BASE_URL}/{path}",
                snippet=unescape(re.sub(r"<[^>]+>", "", str(patent.get("snippet", "")).strip())),
                publication_date=str(patent.get("publication_date", "")).strip() or None,
                assignee=str(patent.get("assignee", "")).strip() or None,
                inventors=[str(patent["inventor"]).strip()] if patent.get("inventor") else [],
            ))
    page = result_root.get("num_page") if isinstance(result_root, dict) else None
    total_pages = result_root.get("total_num_pages") if isinstance(result_root, dict) else None
    next_cursor = str(int(page) + 1) if isinstance(page, int) and isinstance(total_pages, int) and page + 1 < total_pages else None
    return results, next_cursor


def parse_biblio_html(html: str, publication_number: str, url: str) -> PatentBiblio:
    soup = BeautifulSoup(html, "html.parser")
    number = _meta(soup, "DC.publication") or _text(soup.select_one("dd[itemprop='publicationNumber'], meta[itemprop='publicationNumber']")) or publication_number
    fields = {
        "title": _meta(soup, "DC.title") or _text(soup.select_one("meta[itemprop='title'], [itemprop='title']")),
        "application_number": _text(soup.select_one("dd[itemprop='applicationNumber']")) or None,
        "priority_date": _text(soup.select_one("time[itemprop='priorityDate']")) or None,
        "filing_date": _text(soup.select_one("time[itemprop='filingDate']")) or None,
        "publication_date": _text(soup.select_one("time[itemprop='publicationDate']")) or None,
        "grant_date": _text(soup.select_one("time[itemprop='grantDate']")) or None,
        "abstract": _text(soup.select_one("section[itemprop='abstract'], div.abstract, [itemprop='abstract']")),
    }
    provenance = {key: url for key, value in fields.items() if value}
    return PatentBiblio(
        publication_number=number, title=fields["title"], application_number=fields["application_number"],
        priority_date=fields["priority_date"], filing_date=fields["filing_date"], publication_date=fields["publication_date"], grant_date=fields["grant_date"],
        assignees=_texts(soup.select("dd[itemprop='assigneeOriginal'], [itemprop='assigneeOriginal']")),
        inventors=_texts(soup.select("dd[itemprop='inventor'], [itemprop='inventor']")),
        ipc=_texts(soup.select("dd[itemprop='ipc'], [itemprop='ipc']")),
        cpc=_texts(soup.select("dd[itemprop='cpc'], [itemprop='cpc']")),
        abstract=fields["abstract"], url=url, field_provenance=provenance,
    )


def parse_sections_html(html: str, request: SectionRequest) -> list[TextSection]:
    soup = BeautifulSoup(html, "html.parser")
    output: list[TextSection] = []
    remaining = request.max_characters
    if "abstract" in request.sections:
        text = _text(soup.select_one("section[itemprop='abstract'], div.abstract, [itemprop='abstract']"))
        if text:
            output.append(_section("abstract", "abstract", text))
            remaining -= len(text)
    if "claims" in request.sections and remaining > 0:
        claims = soup.select("div[itemprop='claims'] claim, section[itemprop='claims'] claim, [itemprop='claim'], [itemprop='claims'] .claim-text")
        for index, claim in enumerate(claims, start=1):
            number = str(claim.get("num") or claim.get("data-claim-number") or index)
            if request.claim_numbers and number not in request.claim_numbers:
                continue
            text = _text(claim)[:remaining]
            if text:
                output.append(_section("claims", f"claim:{number}", text, number))
                remaining -= len(text)
            if remaining <= 0:
                break
    if "description" in request.sections and remaining > 0:
        paragraphs = soup.select("section[itemprop='description'] div.description-paragraph, [itemprop='description'] p, section.description p")
        for index, paragraph in enumerate(paragraphs, start=1):
            text = _text(paragraph)[:remaining]
            if text:
                output.append(_section("description", f"paragraph:{index}", text))
                remaining -= len(text)
            if remaining <= 0:
                break
    return output


def parse_relations_html(html: str) -> PatentRelations:
    soup = BeautifulSoup(html, "html.parser")

    def numbers(selector: str) -> list[str]:
        return list(dict.fromkeys(filter(None, (_publication_from_url(str(link.get("href", ""))) for link in soup.select(selector)))))

    family = numbers("section.family a[href*='/patent/'], [itemprop='family'] a[href*='/patent/']")
    citations = numbers("section[itemprop='referencesCited'] a[href*='/patent/'], [itemprop='referencesCited'] a[href*='/patent/']")
    cited_by = numbers("section[itemprop='forwardReferences'] a[href*='/patent/'], [itemprop='forwardReferences'] a[href*='/patent/']")
    return PatentRelations(family_members=family, citations=citations, cited_by=cited_by, completeness="partial" if family or citations or cited_by else "unavailable")


def _section(section: str, locator: str, text: str, claim_number: str | None = None) -> TextSection:
    return TextSection(section=section, locator=locator, text=text, content_hash=_hash(text), claim_number=claim_number)


def _build_query(request: PatentSearchRequest) -> str:
    terms = [request.query]
    if request.assignee:
        terms.append(f'assignee:"{request.assignee}"')
    if request.before:
        terms.append(f"before:{request.before}")
    if request.after:
        terms.append(f"after:{request.after}")
    terms.extend(request.cpc)
    return " ".join(terms)


def _failed_search(request_id: str, url: str, message: str, code: str, retryable: bool = False) -> PatentSearchResponse:
    return PatentSearchResponse(request_id=request_id, status="failed", source="google_patents", source_url=url, error=ToolError(code=code, message=message, retryable=retryable))


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _text(node) -> str:
    return " ".join(node.stripped_strings) if node else ""


def _texts(nodes) -> list[str]:
    return list(dict.fromkeys(text for node in nodes if (text := _text(node))))


def _meta(soup: BeautifulSoup, name: str) -> str:
    tag = soup.find("meta", attrs={"name": name})
    return str(tag.get("content", "")).strip() if tag else ""


def _publication_from_url(url: str) -> str | None:
    match = re.search(r"/patent/([^/?#]+)", url)
    return match.group(1) if match else None


def _keywords(text: str) -> set[str]:
    return {word.lower() for word in re.findall(r"[A-Za-z0-9]{3,}|[\u4e00-\u9fff]{2,}", text)}


def _keyword_score(keywords: set[str], text: str) -> float:
    if not keywords:
        return 0.0
    haystack = text.lower()
    hits = sum(1 for keyword in keywords if keyword in haystack)
    return hits / len(keywords)
