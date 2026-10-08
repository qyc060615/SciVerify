"""Offline source qualification regressions through real download/parse/cache code."""
from unittest.mock import Mock

import httpx
import pytest

from app.services import paper_retriever as retrieval
from app.services import document_retriever as transport
from app.services.document_parser import parse_document
from app.services.evidence_chunker import chunk_sections
from app.services.full_text_qualifier import discover_direct_full_text_links, is_full_text_document
from app.services.source_store import LocalSourceStore, AcceptedSourceArtifact
from app.schemas.paper import PaperRetrievalStatus, PaperMetadata
from app.tests.full_text_fixtures import FULL_TEXT_HTML, LANDING_HTML, PROSE
from app.tests.test_source_lifecycle import CITATION, DOI, pdf_bytes

BASE = 'https://repository.example/items/record'
PDF = 'https://repository.example/bitstreams/paper/download'


def configure(monkeypatch, urls=(BASE,)):
    resolver = Mock(return_value=CITATION)
    monkeypatch.setattr(retrieval, 'resolve_doi', resolver)
    monkeypatch.setattr(retrieval, '_fetch_openalex_work', Mock(return_value=None))
    monkeypatch.setattr(retrieval, '_discover_europe_pmc_candidates', Mock(return_value=[
        retrieval.FullTextCandidate(url, 'html', 'fixture') for url in urls]))
    for name in ('_discover_unpaywall_candidates', '_discover_semantic_scholar_candidates'):
        monkeypatch.setattr(retrieval, name, Mock(return_value=[]))
    return resolver


def run(routes):
    seen = []
    def handler(request):
        url = str(request.url)
        seen.append(url)
        value = routes[url]  # Unexpected requests fail rather than reaching the network.
        if isinstance(value, Exception):
            raise value
        if isinstance(value, httpx.Response):
            return value
        content, fmt = value
        return httpx.Response(200, content=content, headers={'Content-Type': 'application/' + fmt if fmt == 'pdf' else 'text/html'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = retrieval.retrieve_paper(DOI, client=client)
    return result, seen


def landing(link=''):
    return LANDING_HTML.replace(b'</body>', link.encode() + b'</body>')


def test_parseable_landing_is_not_evidence_or_cached(monkeypatch, caplog):
    configure(monkeypatch)
    caplog.set_level('INFO')
    assert chunk_sections(parse_document(LANDING_HTML, 'html'), DOI, BASE)
    result, seen = run({BASE: (LANDING_HTML, 'html')})
    assert result.status == PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE
    assert not result.chunks and not result.sections and not result.paper.full_text_available
    assert LocalSourceStore().get(DOI) is None and seen == [BASE]
    assert 'reason=landing_or_abstract' in caplog.text
    assert PROSE not in caplog.text


@pytest.mark.parametrize('link', [
    '<meta name="citation_pdf_url" content="/bitstreams/paper/download">',
    '<link type="application/pdf" href="/bitstreams/paper/download">',
    '<a href="/bitstreams/paper/download">Download PDF</a>',
    '<a href="/bitstreams/paper/download">Polack trial.pdf (756 KB)</a>',
])
def test_direct_pdf_is_downloaded_parsed_and_cached(monkeypatch, caplog, link):
    configure(monkeypatch)
    caplog.set_level('INFO')
    raw_pdf = pdf_bytes()
    result, seen = run({BASE: (landing(link), 'html'), PDF: (raw_pdf, 'pdf')})
    assert result.status == PaperRetrievalStatus.SUCCESS and result.chunks
    assert seen == [BASE, PDF]
    assert result.paper.full_text_format == 'pdf' and result.paper.full_text_url == PDF
    assert result.source.url == PDF and all(chunk.source_url == PDF for chunk in result.chunks)
    stored = LocalSourceStore().get(DOI)
    assert stored.content == raw_pdf and stored.format == 'pdf' and stored.source_url == PDF
    assert 'full_text_followup_discovered' in caplog.text and 'format=pdf' in caplog.text


def test_relative_pdf_uses_redirect_destination(monkeypatch):
    configure(monkeypatch)
    final = 'https://repository.example/new/item/'
    target = final + 'paper.pdf'
    result, seen = run({BASE: httpx.Response(302, headers={'Location': final}),
        final: (landing('<a href="paper.pdf">File</a>'), 'html'), target: (pdf_bytes(), 'pdf')})
    assert result.status == PaperRetrievalStatus.SUCCESS and seen == [BASE, final, target]
    assert result.paper.full_text_url == target


def test_empty_download_page_can_follow_pdf(monkeypatch):
    configure(monkeypatch)
    result, seen = run({BASE: (f'<html><head><meta name="citation_pdf_url" content="{PDF}"></head><body></body></html>'.encode(), 'html'), PDF: (pdf_bytes(), 'pdf')})
    assert result.status == PaperRetrievalStatus.SUCCESS and seen == [BASE, PDF]


def test_unqualified_page_falls_back_to_next_candidate(monkeypatch):
    other = BASE + '/full'
    configure(monkeypatch, [BASE, other])
    result, seen = run({BASE: (LANDING_HTML, 'html'), other: (FULL_TEXT_HTML, 'html')})
    assert result.status == PaperRetrievalStatus.SUCCESS and seen == [BASE, other]


@pytest.mark.parametrize('url', [BASE, 'https://pmc.ncbi.nlm.nih.gov/articles/PMC123/', 'https://europepmc.org/articles/PMC123'])
def test_scholarly_html_accepted_and_cache_reused_without_network(monkeypatch, url):
    resolver = configure(monkeypatch, [url])
    result, seen = run({url: (FULL_TEXT_HTML, 'html')})
    assert result.status == PaperRetrievalStatus.SUCCESS and result.chunks and seen == [url]
    resolver.side_effect = AssertionError('Cache must bypass discovery')
    cached, seen = run({})
    assert cached.source.cache_hit and cached.chunks == result.chunks and seen == []


def test_old_landing_cache_rejected_and_replaced_by_pdf(monkeypatch, caplog):
    configure(monkeypatch)
    caplog.set_level('INFO')
    old = AcceptedSourceArtifact.create(doi=DOI, content=LANDING_HTML, format='html',
        source_url=BASE, provider='fixture', origin='remote',
        paper=PaperMetadata(paper_id=DOI, doi=DOI, title=CITATION.title))
    LocalSourceStore().put(old)
    raw = pdf_bytes()
    result, seen = run({BASE: (landing(f'<meta name="citation_pdf_url" content="{PDF}">'), 'html'), PDF: (raw, 'pdf')})
    assert result.status == PaperRetrievalStatus.SUCCESS and not result.source.cache_hit
    assert seen == [BASE, PDF] and LocalSourceStore().get(DOI).content == raw
    assert 'source_cache_rejected' in caplog.text and 'reason=not_full_text' in caplog.text
    assert 'source_cache_hit' not in caplog.text
    configure(monkeypatch).side_effect = AssertionError('No provider on valid PDF cache')
    cached, seen = run({})
    assert cached.source.cache_hit and cached.chunks == result.chunks and not seen


def test_pdf_priority_dedupe_and_one_hop_cycle(monkeypatch):
    configure(monkeypatch)
    second = BASE + '/second'
    third = BASE + '/third'
    page = landing(f'<meta name="citation_fulltext_html_url" content="{second}"><meta name="citation_pdf_url" content="{PDF}"><a href="{PDF}#download">View PDF</a><a href="{BASE}#self">View full text</a>')
    result, seen = run({BASE: (page, 'html'), PDF: httpx.Response(404),
        second: (landing(f'<a href="{third}">View full text</a><a href="{BASE}">View full text</a>'), 'html')})
    assert seen == [BASE, PDF, second] and result.status == PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE


@pytest.mark.parametrize('marker', ['subscription required', 'Checking your browser'])
@pytest.mark.parametrize('where', ['parent', 'followup'])
def test_paywall_and_interstitial_are_never_bypassed(monkeypatch, marker, where):
    configure(monkeypatch)
    link = f'<meta name="citation_pdf_url" content="{PDF}">'
    blocked = landing(link + '<div>' + marker + '</div>')
    routes = {BASE: (blocked if where == 'parent' else landing(link), 'html')}
    if where == 'followup':
        routes[PDF] = (blocked, 'html')
    result, seen = run(routes)
    assert result.status == PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE and not result.chunks
    assert seen == ([BASE] if where == 'parent' else [BASE, PDF])
    assert LocalSourceStore().get(DOI) is None


@pytest.mark.parametrize('failure', ['timeout', 'oversize'])
def test_followup_reuses_transport_limits(monkeypatch, failure):
    configure(monkeypatch)
    page = landing(f'<meta name="citation_pdf_url" content="{PDF}">')
    if failure == 'oversize':
        monkeypatch.setattr(transport, 'MAX_DOCUMENT_SIZE', len(page) + 10)
        target = (pdf_bytes() + b' ' * len(page), 'pdf')
    else:
        target = httpx.ReadTimeout('offline fixture')
    result, seen = run({BASE: (page, 'html'), PDF: target})
    assert seen == [BASE, PDF] and result.status == PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE
    assert LocalSourceStore().get(DOI) is None


def test_link_bounds_and_unsafe_links():
    links = ''.join(f'<a href="/{i}.pdf">PDF</a>' for i in range(10))
    assert len(discover_direct_full_text_links(landing(links), BASE)) == 3
    unsafe = ['file:///paper.pdf', 'javascript:download.pdf', 'http://localhost/p.pdf',
              'http://127.0.0.1/p.pdf', 'http://10.1.2.3/p.pdf', 'https://user:secret@host.example/p.pdf', 'http://[bad/p.pdf']
    assert discover_direct_full_text_links(landing(''.join(f'<a href="{url}">PDF</a>' for url in unsafe)), BASE) == []


def test_global_request_and_followup_budgets(monkeypatch):
    urls = [BASE + f'/{i}' for i in range(30)]
    configure(monkeypatch, urls)
    routes = {}
    for url in urls:
        routes[url] = (landing(''.join(f'<a href="{url}/{i}.pdf">PDF</a>' for i in range(3))), 'html')
        for i in range(3):
            routes[url + f'/{i}.pdf'] = httpx.Response(404)
    result, seen = run(routes)
    assert result.status == PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE
    assert len(seen) == retrieval.MAX_SOURCE_CANDIDATE_VISITS
    assert len([url for url in seen if url.endswith('.pdf')]) == retrieval.MAX_SOURCE_FOLLOWUPS
    assert len(seen) == len(set(seen))


@pytest.mark.parametrize('content', [
    LANDING_HTML,
    ('<article><div class="abstract"><h2>Methods</h2><p>' + PROSE * 4 + '</p><h2>Results</h2><p>' + PROSE * 4 + '</p></div></article>').encode(),
    ('<article><h2>Abstract</h2><h3>Methods</h3><p>' + PROSE * 4 + '</p><h3>Results</h3><p>' + PROSE * 4 + '</p></article>').encode(),
    b'<html><body><nav><h2>Methods</h2><p>Navigation only</p></nav></body></html>',
    b'<meta name="citation_fulltext_html_url" content="https://example.org/full"><article><p>Metadata alone</p></article>',
])
def test_length_metadata_or_abstract_structure_alone_do_not_qualify(content):
    assert not is_full_text_document(content, 'html')


def test_plain_scholarly_html_and_explicit_html_followup(monkeypatch):
    plain = FULL_TEXT_HTML.replace(b'<article>', b'').replace(b'</article>', b'')
    assert is_full_text_document(plain, 'html')
    configure(monkeypatch)
    url = BASE + '/full'
    result, seen = run({BASE: (landing(f'<a href="{url}">View full text</a>'), 'html'), url: (plain, 'html')})
    assert result.status == PaperRetrievalStatus.SUCCESS and seen == [BASE, url]


def test_subsections_keep_canonical_parent_but_references_do_not_count():
    html = ('<article><h2>Methods</h2><h3>Participants</h3><p>' + PROSE
            + '</p><h2>Results</h2><h3>Primary endpoint</h3><p>' + PROSE
            + '</p><h2>References</h2><p>' + PROSE * 10 + '</p></article>').encode()
    assert is_full_text_document(html, 'html')
    assert not is_full_text_document(html.replace(b'<h2>Results</h2>', b'<h2>References</h2>'), 'html')


def test_duplicate_initial_candidate_promoted_without_repeat(monkeypatch):
    configure(monkeypatch, [BASE, PDF])
    result, seen = run({BASE: (landing(f'<meta name="citation_pdf_url" content="{PDF}">'), 'html'), PDF: (pdf_bytes(), 'pdf')})
    assert seen == [BASE, PDF] and result.paper.full_text_format == 'pdf'


def test_unparseable_bad_cache_rejection_is_observable(monkeypatch, caplog):
    configure(monkeypatch, [])
    caplog.set_level('INFO')
    LocalSourceStore().put(AcceptedSourceArtifact.create(doi=DOI, content=b'<html><body></body></html>',
        format='html', source_url=BASE, provider='fixture', origin='remote',
        paper=PaperMetadata(paper_id=DOI, doi=DOI, title=CITATION.title)))
    result, seen = run({})
    assert result.status == PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE and not seen
    assert 'source_cache_rejected' in caplog.text and 'source_cache_hit' not in caplog.text
