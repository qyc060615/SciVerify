"""Visible citation identifiers from local surfaces, never bibliography/ID inference."""
import re


def canonicalize_visible_citation_label(surface):
    """Recognize one ASCII number with optional parser-fragment punctuation.

    Multiple tokens, ranges and nonnumeric identifiers stay on the existing
    visible-label path. Raw callout text and occurrence identity are never edited.
    """
    match = re.fullmatch(
        r"(?P<opening>\(|\[)?\s*(?P<number>[0-9]+)\s*[,;]?\s*(?P<closing>\)|\])?",
        surface.strip(),
    )
    if not match:
        return None
    opening, closing = match.group("opening", "closing")
    if opening and closing and (opening, closing) not in {("(", ")"), ("[", "]")}:
        return None
    return match.group("number")


def visible_labels(surface):
    canonical = canonicalize_visible_citation_label(surface)
    if canonical is not None:
        return (canonical,)
    label = surface.strip()
    if len(label) >= 2 and (label[0], label[-1]) in {("[", "]"), ("(", ")")}:
        label = label[1:-1].strip()
    # GROBID may put a group separator into one occurrence: '4,' then '8'.
    numeric = label.rstrip(" ,;")
    if not re.fullmatch(r"[0-9]+(?:\s*[-–]\s*[0-9]+)?(?:\s*[,;]\s*[0-9]+(?:\s*[-–]\s*[0-9]+)?)*", numeric):
        return (label,) if label else ()
    labels = []
    for part in re.split(r"\s*[,;]\s*", numeric):
        ends = re.split(r"\s*[-–]\s*", part)
        if len(ends) == 1:
            labels.append(ends[0])
        else:
            start, end = map(int, ends)
            if end < start or end - start >= 2000:
                return (label,)  # Keep unsupported ranges opaque and bounded.
            width = len(ends[0]) if ends[0].startswith("0") and len(ends[0]) == len(ends[1]) else 0
            labels.extend(str(n).zfill(width) for n in range(start, end + 1))
    return tuple(dict.fromkeys(labels))


def local_label_index(callouts):
    index = {}
    for callout in callouts:
        for label in visible_labels(callout.text):
            index.setdefault(label, []).append(callout)
    return index
