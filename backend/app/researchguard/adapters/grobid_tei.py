"""Pure, bounded, safe TEI-to-domain projection. Scope: body prose only."""
from __future__ import annotations

import re
from collections import defaultdict
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
        doi = None
        for identifier in entry.findall(f".//{TEI}idno"):
            if identifier.get("type", "").lower() == "doi":
                try:
                    doi = normalize_doi(_text(identifier))
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
                                    title=title, authors=authors, year=year, journal=journal, doi=doi))
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
    title = _text(root.find(f"{TEI}teiHeader/{TEI}fileDesc/{TEI}titleStmt/{TEI}title")) or manuscript.title
    return ParsedManuscript(manuscript=manuscript.model_copy(update={"title": title}),
        paragraphs=tuple(paragraphs), references=tuple(references), citation_callouts=tuple(callouts),
        diagnostics=tuple(diagnostics))
