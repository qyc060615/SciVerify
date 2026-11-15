"""Exclude only explicit, unreferenced boilerplate; preserve uncertain entries."""
import re


def is_unreferenced_publisher_notice(reference, cited_ids):
    if reference.id in cited_ids:
        return False
    if not re.match(r"^\s*Disclaimer\s*/\s*Publisher['’]s\s+Note\s*:", reference.raw_text, re.I):
        return False
    resolution = reference.resolution
    return not (reference.authors or reference.year or reference.journal or reference.doi or reference.url
                or resolution and (resolution.resolved_doi or resolution.source_url)
                or re.search(r"\b10\.\d{4,9}/\S+|\bISBN\b", reference.raw_text, re.I))
