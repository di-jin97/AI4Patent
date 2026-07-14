from __future__ import annotations

import pytest

from backend.patent_analysis.tools import (
    BiblioRequest, GooglePatentsProvider, PassageSearchRequest,
    PatentSearchRequest, SectionRequest,
)


_SEARCH_HTML = """
<article class="search-result-item">
  <a href="/patent/US1234567A1/en"><h3>Thermal aware data migration</h3></a>
  <span itemprop="publicationNumber">US1234567A1</span>
  <time itemprop="publicationDate">2020-01-01</time>
  <span itemprop="assigneeOriginal">Example Storage Inc.</span>
  <span class="snippet">Moves hot data based on temperature and wear.</span>
</article>
"""

_PATENT_HTML = """
<html><head><meta name="DC.title" content="Thermal aware data migration" /></head><body>
  <dd itemprop="publicationNumber">US1234567A1</dd>
  <time itemprop="priorityDate">2018-01-02</time>
  <time itemprop="publicationDate">2020-01-01</time>
  <dd itemprop="assigneeOriginal">Example Storage Inc.</dd>
  <dd itemprop="inventor">Ada Inventor</dd>
  <dd itemprop="cpc">G06F3/06</dd>
  <section itemprop="abstract">A controller migrates hot data based on temperature and wear.</section>
  <section itemprop="claims"><claim num="1">A storage controller determines a risk score from temperature and erase count.</claim><claim num="2">The controller migrates hot data without interrupting host IO.</claim></section>
  <section itemprop="description"><p>Paragraph one describes a temperature sensor.</p><p>Paragraph two describes a wear counter.</p></section>
</body></html>
"""


@pytest.fixture
def provider():
    async def transport(url: str) -> str:
        return _SEARCH_HTML if "?q=" in url else _PATENT_HTML
    return GooglePatentsProvider(transport=transport)


@pytest.mark.asyncio
async def test_search_returns_normalized_source_facts(provider):
    response = await provider.search(PatentSearchRequest(request_id="search-1", query="thermal data migration"))

    assert response.status == "success"
    assert response.query_echo == "thermal data migration"
    assert response.results[0].publication_number == "US1234567A1"
    assert response.results[0].assignee == "Example Storage Inc."


@pytest.mark.asyncio
async def test_biblio_sections_and_passages_are_independent_toolcalls(provider):
    biblio = await provider.get_biblio(BiblioRequest(request_id="biblio-1", publication_number="US1234567A1"))
    sections = await provider.get_sections(SectionRequest(request_id="sections-1", publication_number="US1234567A1", claim_numbers=["1"]))
    passages = await provider.find_passages(PassageSearchRequest(request_id="passages-1", publication_number="US1234567A1", feature_texts=["temperature risk score"]))

    assert biblio.biblio is not None
    assert biblio.biblio.priority_date == "2018-01-02"
    assert biblio.biblio.cpc == ["G06F3/06"]
    assert [(item.locator, item.claim_number) for item in sections.sections if item.section == "claims"] == [("claim:1", "1")]
    assert passages.matches
    assert passages.matches[0].locator == "claim:1"


@pytest.mark.asyncio
async def test_direct_network_is_disabled_without_explicit_opt_in():
    provider = GooglePatentsProvider(direct_access_enabled=False)
    response = await provider.search(PatentSearchRequest(request_id="disabled", query="cache"))

    assert response.status == "failed"
    assert response.error is not None
    assert response.error.code == "ACCESS_DISABLED"
