"""Reference-to-locator policy belongs to the application layer, not domain data."""
from app.researchguard.source_locator import SourceLocator


def reference_locator(reference) -> SourceLocator | None:
    if reference.doi:
        return SourceLocator(kind='doi', value=reference.doi)
    resolution = reference.resolution
    url = resolution.source_url if resolution and resolution.source_url else reference.url
    if url:
        return SourceLocator(kind='url', value=url)
    if resolution and resolution.match_reason == 'VERSION_UNCERTAIN':
        from app.services.source_versions import probable_candidate
        candidate = probable_candidate(reference)
        if candidate is not None:
            # Discovery permission only. Acquisition must still check the actual text.
            return SourceLocator(kind='doi', value=candidate.doi)
    return None
