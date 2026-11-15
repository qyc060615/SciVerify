import re

DOI_PREFIX_PATTERN = re.compile(r"^doi:\s*", re.IGNORECASE)
DOI_URL_PATTERN = re.compile(
    r"^https?://(?:dx\.)?doi\.org/\s*",
    re.IGNORECASE,
)
# Registrant code is typically 4–9 digits; suffix must be non-empty.
VALID_DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)


class InvalidDOIError(ValueError):
    """Raised when a DOI string cannot be normalized to a valid identifier."""


def normalize_doi(value: str) -> str:
    """Normalize common DOI input formats to a bare DOI identifier."""
    if not value or not value.strip():
        raise InvalidDOIError("DOI is required.")

    normalized = value.strip()
    normalized = DOI_PREFIX_PATTERN.sub("", normalized)
    normalized = DOI_URL_PATTERN.sub("", normalized.strip())
    normalized = normalized.strip().rstrip(".,;")

    if not normalized:
        raise InvalidDOIError("DOI is required.")

    if not VALID_DOI_PATTERN.match(normalized):
        raise InvalidDOIError(f"Invalid DOI format: {value.strip()}")

    return normalized.lower()
