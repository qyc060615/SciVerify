"""Pure, bounded, safe TEI-to-domain projection. Scope: body prose only."""
from __future__ import annotations

import re
from collections import defaultdict
from urllib.parse import unquote, urlsplit
from xml.etree.ElementTree import ParseError

from defusedxml.ElementTree import fromstring
from defusedxml.common import DefusedXmlException

from app.researchguard.domain import (
    CitationCallout, Manuscript, ManuscriptDiagnostic, Paragraph, ParsedManuscript,
    Reference, TextSpan,
)
from app.services.manuscript_errors import ManuscriptParseError
from app.utils.doi import InvalidDOIError, normalize_doi

TEI = "{http://www.tei-c.org/ns/1.0}"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
RECIPE = "grobid-0.9.1-body-prose-v1"
MAX_NODES = 100_000
MAX_DEPTH = 128


def _text(node) -> str:
    return " ".join("".join(node.itertext()).split()) if node is not None else ""


def _diag(code, message, entity_id=None, severity="warning"):
    return ManuscriptDiagnostic(code=code, severity=severity, entity_id=entity_id, safe_message=message)


def _manuscript_title(root, manuscript, diagnostics):
    """Use structural title roles; missing metadata is not proof of a bad title.

    Header copies are not independent corroboration. In particular, without any
    container metadata we cannot detect a container mislabelled as an article.
    Keep that candidate with an explicit warning rather than guess from prose.
    """
    header = root.find(f"{TEI}teiHeader/{TEI}fileDesc")
    if header is None:
        return manuscript.title
    containers = {_text(n).casefold() for n in header.findall(f".//{TEI}monogr/{TEI}title") if _text(n)}
    candidates = [n for n in (header.findall(f"{TEI}titleStmt/{TEI}title")
                  + header.findall(f"{TEI}sourceDesc/{TEI}biblStruct/{TEI}analytic/{TEI}title"))
                  if n.get("type") in {None, "main"}]
    rejected, usable = set(), []
    for node in candidates:
        text = _text(node)
        if not text:
            continue
        if node.get("level") in {"j", "s"} or text.casefold() in containers:
            rejected.add(text.casefold())
        elif text.casefold() not in {t.casefold() for t in usable}:
            usable.append(text)
    if rejected:
        diagnostics.append(_diag("MANUSCRIPT_TITLE_CONTAINER_CONFLICT",
            "A manuscript title candidate has a container role or duplicates container metadata.", manuscript.id))
    if len(usable) > 1:
        diagnostics.append(_diag("MANUSCRIPT_TITLE_CONFLICT",
            "Structured article title candidates disagree; no title was selected.", manuscript.id))
        return None
    if usable:
        if not containers:
            diagnostics.append(_diag("MANUSCRIPT_TITLE_UNVERIFIED",
                "Container title metadata is absent; the extracted article title cannot be checked for container misidentification.", manuscript.id))
        return usable[0]
    # An explicitly supplied title is separate from the parser's rejected fields.
    if manuscript.title and manuscript.title.casefold() not in containers | rejected:
        return manuscript.title
    return None


def _resource_path_identifier(value, doi, urls):
    """Abstain when a bare parser identifier copies a download resource path.

    DOI suffix syntax alone cannot distinguish an identifier from appended URL
    path segments. Require a corroborating non-resolver URL and a descendant file
    resource, and never trim it to a presumed parent DOI. Bare complex DOIs and
    explicit DOI resolver identifiers remain valid.
    """
    if value.lower().startswith(("http://doi.org/", "https://doi.org/",
                                 "http://dx.doi.org/", "https://dx.doi.org/")):
        return False
    if len(doi.split("/")) < 3:
        return False
    for url in urls:
        try:
            parts = urlsplit(url)
        except ValueError:
            continue
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            continue
        if parts.hostname.lower() in {"doi.org", "dx.doi.org"}:
            continue
        path = unquote(parts.path).lower()
        if (path.endswith("/" + doi) and re.search(r"\.(?:pdf|zip|docx?|xlsx?|pptx?|csv|gz)$", path)):
            return True
    return False


class _ParagraphText:
    """Normalize whitespace while walking; record each XML occurrence, never find()."""

    def __init__(self):
        self.chars = []
        self.callouts = []
        self.sentences = []

    def append(self, text):
        for char in text or "":
            if char.isspace():
                if self.chars and self.chars[-1] != " ":
                    self.chars.append(" ")
            else:
                self.chars.append(char)

    def walk(self, node):
        # A TEI sentence boundary supplies a separator even without an XML tail.
        # Emit it before recording offsets; never edit canonical text afterwards.
        if node.tag == TEI + "s" and self.sentences and self.chars:
            self.append(" ")
        start = len(self.chars)
        self.append(node.text)
        for child in node:
            # Embedded notes/layout are not prose. Keep their tail, not content.
            if child.tag not in {TEI + name for name in ("note", "figure", "table", "formula", "head", "fw")}:
                self.walk(child)
            self.append(child.tail)
        end = len(self.chars)
        if node.tag == TEI + "ref" and node.get("type") == "bibr":
            self.callouts.append((start, end, node.get("target", "")))
        if node.tag == TEI + "s":
            self.sentences.append((start, end))

    def finish(self):
        # Leading whitespace was never emitted; discard only trailing whitespace.
        text = "".join(self.chars).rstrip()

        def trimmed(start, end):
            end = min(end, len(text))
            while start < end and text[start].isspace():
                start += 1
            while end > start and text[end - 1].isspace():
                end -= 1
            return (start, end)

        callouts = [(*trimmed(a, b), target) for a, b, target in self.callouts]
        sentences = [trimmed(a, b) for a, b in self.sentences]
        return text, sorted(callouts), sorted(sentences)


def parse_tei(xml: bytes, manuscript: Manuscript) -> ParsedManuscript:
    try:
        root = fromstring(xml, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (ParseError, DefusedXmlException, ValueError, LookupError) as exc:
        raise ManuscriptParseError("MALFORMED_TEI", "The parser returned unsafe or malformed TEI XML.") from exc
    if root.tag != TEI + "TEI":
        raise ManuscriptParseError("MALFORMED_TEI", "The parser returned an unsupported XML document.")
    stack, count = [(root, 0)], 0
    while stack:
        node, depth = stack.pop()
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            raise ManuscriptParseError("MALFORMED_TEI", "The parser returned an excessively complex XML document.")
        stack.extend((child, depth + 1) for child in node)

    prefix = f"{manuscript.id}:{RECIPE}"
    diagnostics, references = [], []
    targets = defaultdict(list)
    for index, entry in enumerate(root.findall(f"{TEI}text/{TEI}back//{TEI}listBibl/{TEI}biblStruct")):
        reference_id = f"reference:{prefix}:{index}"
        analytic = entry.find(TEI + "analytic")
        monogr = entry.find(TEI + "monogr")
        title_node = analytic.find(TEI + "title") if analytic is not None else None
        if title_node is None and monogr is not None:
            title_node = monogr.find(TEI + "title")
        title = _text(title_node) or None
        author_parent = analytic if analytic is not None else monogr
        authors = ()
        # Names have XML boundaries, not necessarily spaces between name parts.
        if author_parent is not None:
            authors = tuple(filter(None, (
                " ".join(filter(None, (_text(n) for n in a.findall(f"{TEI}persName/*")))) or _text(a)
                for a in author_parent.findall(TEI + "author")
            )))
        journal = None
        if monogr is not None:
            journal = next((_text(n) for n in monogr.findall(TEI + "title") if n.get("level") == "j" and _text(n)), None)
        date = entry.find(f".//{TEI}imprint/{TEI}date")
        match = re.search(r"\b(\d{4})\b", (date.get("when", "") or _text(date)) if date is not None else "")
        year = int(match.group(1)) if match else None
        # Preserve resource URLs independently of DOI identity, including a URL
        # that the parser placed in an idno with the wrong type.
        urls = [n.get("target") for n in entry.iter()
                if n.tag in {TEI + "ref", TEI + "ptr"}
                and (n.get("target") or "").lower().startswith(("http://", "https://"))]
        urls += [_text(n) for n in entry.findall(f".//{TEI}idno")
                 if n.get("type", "").lower() in {"url", "uri"} and _text(n)]
        # Only non-resolver URLs in mislabelled DOI fields are resource locators.
        urls += [_text(n) for n in entry.findall(f".//{TEI}idno")
                 if n.get("type", "").lower() == "doi"
                 and _text(n).lower().startswith(("http://", "https://"))
                 and not re.match(r"https?://(?:dx\.)?doi\.org/", _text(n), re.IGNORECASE)]
        url = next((u for u in urls if len(u) <= 4000), None)
        doi = None
        for identifier in entry.findall(f".//{TEI}idno"):
            if identifier.get("type", "").lower() == "doi":
                try:
                    value = _text(identifier)
                    doi = normalize_doi(value)
                    if _resource_path_identifier(value, doi, urls):
                        doi = None
                        diagnostics.append(_diag("REFERENCE_DOI_RESOURCE_PATH",
                            "The DOI candidate duplicates a descendant download URL path; URL retained without inferring a parent DOI.", reference_id))
                except InvalidDOIError:
                    diagnostics.append(_diag("MISSING_REFERENCE_METADATA", "A reference DOI could not be normalized.", reference_id))
                break
        raw = next((_text(n) for n in entry.findall(TEI + "note") if n.get("type") == "raw_reference" and _text(n)), "")
        reconstructed = not raw
        if reconstructed:
            raw = " ".join(filter(None, ("; ".join(authors), title, journal, str(year) if year else None, doi)))
        if not raw:
            # Retain incomplete entry identity with its readable extracted text.
            raw = _text(entry)
        if not raw:
            diagnostics.append(_diag("MISSING_REFERENCE_METADATA", "An empty bibliography entry was omitted."))
            if entry.get(XML_ID):
                targets[entry.get(XML_ID)].append(None)
            continue
        if reconstructed:
            diagnostics.append(_diag("RECONSTRUCTED_REFERENCE_TEXT", "Reference text was reconstructed from structured fields, not extracted verbatim.", reference_id))
        references.append(Reference(id=reference_id, manuscript_id=manuscript.id, raw_text=raw,
                                    title=title, authors=authors, year=year, journal=journal, doi=doi, url=url))
        if not title or not authors or year is None:
            diagnostics.append(_diag("MISSING_REFERENCE_METADATA", "A reference has incomplete bibliographic metadata.", reference_id))
        if entry.get(XML_ID):
            targets[entry.get(XML_ID)].append(reference_id)
    for matches in targets.values():
        if len(matches) > 1:
            diagnostics.append(_diag("DUPLICATE_REFERENCE_TARGET", "A bibliography target is ambiguous; its occurrences remain unresolved."))

    paragraphs, callouts = [], []
    body = root.find(f"{TEI}text/{TEI}body")

    def visit(container, section=None):
        head = container.find(TEI + "head")
        local_section = _text(head) or section
        for child in container:
            if child.tag == TEI + "div":
                visit(child, local_section)
            elif child.tag == TEI + "p":
                builder = _ParagraphText()
                builder.walk(child)
                text, markers, sentences = builder.finish()
                if not text:
                    continue
                paragraph_id = f"paragraph:{prefix}:{len(paragraphs)}"
                spans = []
                previous_end = 0
                reliable = bool(sentences)
                for start, end in sentences:
                    if start >= end or start < previous_end:
                        reliable = False
                        break
                    spans.append(TextSpan(start=start, end=end))
                    previous_end = end
                # Sentence boundaries must cover all non-whitespace prose.
                covered_end = 0
                for span in spans:
                    if text[covered_end:span.start].strip():
                        reliable = False
                    covered_end = span.end
                if text[covered_end:].strip():
                    reliable = False
                if not reliable:
                    spans = []
                    diagnostics.append(_diag("MISSING_SENTENCE_BOUNDARIES", "No complete, reliable sentence boundaries were provided.", paragraph_id, "info"))
                paragraphs.append(Paragraph(id=paragraph_id, manuscript_id=manuscript.id, text=text,
                                            order=len(paragraphs), section=local_section, sentence_spans=tuple(spans)))
                for start, end, raw_target in markers:
                    if start >= end:
                        diagnostics.append(_diag("EMPTY_CITATION_CALLOUT", "An empty citation marker was omitted.", paragraph_id))
                        continue
                    callout_id = f"callout:{prefix}:{len(callouts)}"
                    resolved, failures = [], 0
                    tokens = raw_target.split()
                    for target in dict.fromkeys(tokens):
                        matches = targets.get(target[1:]) if target.startswith("#") else None
                        if matches and len(matches) == 1 and matches[0] is not None:
                            if matches[0] not in resolved:
                                resolved.append(matches[0])
                        else:
                            failures += 1
                    status = "resolved" if resolved and not failures else "partial" if resolved else "unresolved"
                    if status != "resolved":
                        code = "PARTIAL_REFERENCE_TARGET" if resolved else "UNRESOLVED_REFERENCE_TARGET"
                        diagnostics.append(_diag(code, "The citation marker could not be fully linked to bibliography entries.", callout_id))
                    callouts.append(CitationCallout(id=callout_id, manuscript_id=manuscript.id,
                        paragraph_id=paragraph_id, text=text[start:end], span=TextSpan(start=start, end=end),
                        order=len(callouts), reference_ids=tuple(resolved), resolution_status=status))

    if body is not None:
        visit(body)
    if not paragraphs:
        raise ManuscriptParseError("MANUSCRIPT_PARSE_FAILED", "No usable body prose was extracted from the manuscript.", 422)
    if not references:
        diagnostics.append(_diag("NO_REFERENCES", "No bibliography entries were extracted.", severity="info"))
    if not callouts:
        diagnostics.append(_diag("NO_CITATION_CALLOUTS", "No bibliographic citation markers were extracted from body prose.", severity="info"))
    title = _manuscript_title(root, manuscript, diagnostics)
    return ParsedManuscript(manuscript=manuscript.model_copy(update={"title": title}),
        paragraphs=tuple(paragraphs), references=tuple(references), citation_callouts=tuple(callouts),
        diagnostics=tuple(diagnostics))
