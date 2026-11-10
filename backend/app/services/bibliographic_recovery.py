"""Positive-only recovery of pure bibliographic assertions from real source bytes.

Never use manuscript/reference metadata to prove itself; never fabricate a chunk.
"""
import hashlib
import re
import unicodedata

from bs4 import BeautifulSoup

from app.researchguard.domain import ProcessingStatus, Verdict


_TITLE_CLAIM = re.compile(
    r'^(?:The|A|An) (?:study|paper|article|review|analysis|report|publication)'
    r'(?: by (?P<author>[^"“\n]+?))? is titled ["“](?P<title>[^"”\n]+)["”]\.?(?:\s*)$', re.I)


def _normal(text):
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def recover_bibliographic_result(claim, result, source, *, store=None):
    if (result.processing_status != ProcessingStatus.COMPLETED
            or result.verdict != Verdict.INSUFFICIENT or not result.evidence_chunks
            or source.retrieval_status != "available"):
        return result
    match = _TITLE_CLAIM.fullmatch(claim)
    if not match or not source.doi or not source.content_hash:
        return result
    try:
        from app.services.source_store import LocalSourceStore
        artifact = (store or LocalSourceStore()).get(source.doi)
        if (artifact is None or artifact.format != "html"
                or "sha256:" + hashlib.sha256(artifact.content).hexdigest() != source.content_hash
                or not artifact.provenance or artifact.provenance.identity != "EXACT_IDENTITY"):
            return result
        soup = BeautifulSoup(artifact.content, "html.parser")
        title_node = soup.select_one('meta[name="citation_title"]')
        if title_node is None:
            return result
        title = str(title_node.get("content", ""))
        authors = [str(n.get("content", "")) for n in soup.select('meta[name="citation_author"]')]
        if _normal(match["title"]) != _normal(title):
            return result
        if match["author"]:
            author = re.sub(r"^(?:Dr\.?|Prof\.?)\s+", "", match["author"], flags=re.I)
            author = re.sub(r"\s+et\s+al\.?$", "", author, flags=re.I)
            # "X et al." is a first-author attribution, not any coauthor.
            if (not author or not authors
                    or not (_normal(authors[0]).endswith(" " + _normal(author)) or _normal(authors[0]) == _normal(author))):
                return result
    except (OSError, ValueError, TypeError):
        return result
    proof = {"kind": "source_html_bibliography", "source_document_id": source.id,
             "source_hash": source.content_hash, "title": title, "authors": authors,
             "fields": ["citation_title"] + (["citation_author"] if match["author"] else []),
             "original_verdict": result.verdict.value, "original_explanation": result.explanation}
    trace = result.traceability.model_copy(update={
        "method": (result.traceability.method or "verification") + "+source_bibliography",
        "metadata": {**result.traceability.metadata, "bibliographic_recovery": proof}})
    return result.model_copy(update={"verdict": Verdict.SUPPORTED, "traceability": trace,
        "explanation": "The title" + (" and named author" if match["author"] else "")
        + " match bibliographic metadata extracted directly from the identity-verified source HTML. "
          "This is source metadata evidence, not a quotation from its body. "
          "The original INSUFFICIENT analysis is retained in traceability.",
    })
