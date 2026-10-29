"""Pre-job source checks/acquisition using the same readers and checks as M4."""
from app.researchguard.domain import Reference
from app.services.source_locator import reference_locator
from app.services.source_acquisition import retrieve_reference_source
from app.services.source_store import LocalSourceStore, verify_source_durability, SourceDurabilityError
from app.services.paper_retriever import PaperNotFoundError, PaperProviderError
from app.schemas.paper import PaperRetrievalStatus


def prepare_reference(reference: Reference, *, retrieve=False):
    def outcome(state, reason, result=None, retryable=False):
        available = state == 'available'
        return {'reference_id': reference.id, 'state': state, 'reason_code': reason,
                'retryable': retryable, 'retrieval_status': result.status.value if result else None,
                'format': result.paper.full_text_format if available else None,
                'raw_content_sha256': result.source.raw_content_sha256 if available else None,
                'source': result.source.model_dump(mode='json') if result else None}
    if reference.resolution and reference.resolution.status not in {'resolved', 'non_doi_source'}:
        return outcome('needs_attention', 'REFERENCE_' + reference.resolution.status.upper())
    try:
        locator = reference_locator(reference)
        if locator is None:
            return outcome('needs_attention', 'SOURCE_LOCATOR_MISSING')
        result = retrieve_reference_source(reference, local_only=not retrieve)
        actual = result.source.locator
        if actual is None and result.paper.doi:
            from app.researchguard.source_locator import SourceLocator
            actual = SourceLocator(kind='doi', value=result.paper.doi)
        if result.status != PaperRetrievalStatus.SUCCESS:
            if result.detail in {'SOURCE_IDENTITY_CONFLICT', 'SOURCE_IDENTITY_UNCERTAIN', 'SOURCE_REFERENCE_ASSOCIATION_UNCONFIRMED', 'SOURCE_VERSION_UNCONFIRMED'}:
                return outcome('needs_attention', result.detail, result)
            if not retrieve:
                return outcome('not_cached', 'SOURCE_NOT_CACHED', result)
            reason = result.detail if result.detail and result.detail.startswith('SOURCE_') and result.detail.replace('_', '').isalnum() else 'SOURCE_' + result.status.value.upper()
            identity_issue = 'IDENTITY' in reason or 'ASSOCIATION' in reason or 'VERSION_UNCONFIRMED' in reason
            return outcome('needs_attention' if identity_issue else 'unavailable', reason, result, not identity_issue)
        if actual != locator or result.source.identity_status == 'conflict':
            return outcome('needs_attention', 'SOURCE_IDENTITY_CONFLICT', result)
        if not result.paper.full_text_available or not result.chunks or result.paper.full_text_format not in {'pdf', 'html'}:
            return outcome('failed' if retrieve else 'not_cached', 'SOURCE_CONTENT_INVALID', result, True)
        verify_source_durability(result, LocalSourceStore())
        return outcome('available', 'SOURCE_PERSISTED', result)
    except SourceDurabilityError as exc:
        return outcome('failed' if retrieve else 'not_cached', exc.code, retryable=True)
    except PaperNotFoundError:
        return outcome('unavailable' if retrieve else 'not_cached', 'SOURCE_NOT_FOUND', retryable=True)
    except PaperProviderError:
        return outcome('failed' if retrieve else 'not_cached', 'SOURCE_PROVIDER_ERROR', retryable=True)
    except (OSError, TimeoutError):
        return outcome('failed' if retrieve else 'not_cached', 'SOURCE_STORAGE_OR_NETWORK_ERROR', retryable=True)
    except ValueError:
        return outcome('needs_attention', 'SOURCE_IDENTITY_OR_URL_INVALID')
    except Exception:
        # Keep provider/parser internals and server paths out of the public response.
        return outcome('failed' if retrieve else 'not_cached', 'SOURCE_PREPARATION_FAILURE', retryable=True)
