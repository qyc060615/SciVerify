"""Replay cached-reference recovery with all providers/downloads disabled.

This validates source preparation only; it never creates jobs or scientific verdicts.
"""
import argparse
import asyncio
import hashlib
import json
import logging
from pathlib import Path
import sys
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.schemas.claim_extraction import ClaimExtractionRequest
from app.services.citation_context import from_request
from app.services.reference_resolver import ProviderError, resolve_references
from app.services.source_locator import reference_locator
from app.services.source_preparation import prepare_reference
from app.services.source_store import LocalSourceStore, verify_source_durability
from app.services.source_acquisition import retrieve_reference_source
from app.researchguard.adapters.sciverify import accepted_source_to_domain


def locator_data(reference):
    locator = reference_locator(reference)
    return locator.model_dump(mode='json') if locator else None


def status_data(status):
    return {key: status.get(key) for key in (
        'state', 'identity', 'reason_code', 'format', 'raw_content_sha256')}


async def replay(args):
    payload = json.loads(Path(args.parsed).read_text(encoding='utf-8'))
    parsed = from_request(ClaimExtractionRequest.model_validate({key: payload[key]
        for key in ('schema_version', 'scope', 'offset_unit', 'parsed')}))
    store = LocalSourceStore()
    manifest = {str(file.relative_to(store.root)): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in store.root.rglob('*') if file.is_file()}
    before = {number: {'locator': locator_data(parsed.references[number - 1]),
        **status_data(prepare_reference(parsed.references[number - 1], retrieve=False))}
        for number in args.references}
    provider_calls = []
    async def unavailable(reference, provider, *unused):
        provider_calls.append({'reference_id': reference.id, 'provider': provider})
        raise ProviderError(provider.upper() + '_NETWORK_ERROR')
    def forbidden(*unused, **kwargs):
        raise AssertionError('Network/model access is forbidden during this replay')
    with patch('app.services.reference_resolver.search_reference_by_metadata', unavailable), \
            patch('socket.socket.connect', forbidden), patch('socket.getaddrinfo', forbidden), \
            patch('app.services.source_acquisition.retrieve_document', forbidden), \
            patch('app.services.paper_retriever.resolve_doi', forbidden):
        async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as client:
            enriched = await resolve_references(parsed, client=client)
        results = []
        for number in args.references:
            reference = enriched.references[number - 1]
            step2 = prepare_reference(reference, retrieve=False)
            print('Checking R' + str(number), locator_data(reference), step2['state'],
                reference.resolution.match_reason, flush=True)
            assert step2['state'] == 'available', (number, step2['reason_code'], reference.resolution.model_dump())
            # The same acquisition/adapter/durability path used by Step 4,
            # deliberately stopping before evidence models/scientific verification.
            prepared = retrieve_reference_source(reference, local_only=True)
            verify_source_durability(prepared, store)
            source, chunks = accepted_source_to_domain(prepared)
            artifact = store.get_locator(reference_locator(reference))
            assert artifact is not None
            raw_path = store.root / artifact.raw_content_sha256 / ('source.' + artifact.format)
            actual_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()
            assert step2['state'] == 'available' and step2['identity'] == 'CONFIRMED'
            assert step2['raw_content_sha256'] == prepared.source.raw_content_sha256 == actual_hash
            assert source.content_hash == 'sha256:' + actual_hash and chunks
            results.append({'reference_number': number, 'reference_id': reference.id, 'title': reference.title,
                'before': before[number], 'after': {'locator': locator_data(reference), **status_data(step2)},
                'resolution': reference.resolution.model_dump(mode='json'),
                'step4_source_preparation': {'cache_hit': prepared.source.cache_hit,
                    'source_version': source.content_hash, 'evidence_chunks': len(chunks)},
                'raw_file': str(raw_path), 'actual_file_sha256': actual_hash,
                'file_unchanged': manifest[str(raw_path.relative_to(store.root))] == actual_hash})
    after_manifest = {str(file.relative_to(store.root)): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in store.root.rglob('*') if file.is_file()}
    assert manifest == after_manifest, 'Source Store must remain unchanged'
    report = {'providers': 'forced unavailable', 'network': 'forbidden', 'models_called': False,
        'source_store': str(store.root), 'source_store_unchanged': True,
        'provider_failures_for_other_references': provider_calls, 'results': results}
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for row in results:
        print(json.dumps({'R': row['reference_number'], 'before': row['before']['reason_code'],
            'after': row['after']['state'], 'identity': row['after']['identity'],
            'locator': row['after']['locator'], 'sha256': row['actual_file_sha256'],
            'file_unchanged': row['file_unchanged']}, ensure_ascii=False))
    print('Source Store unchanged; no downloads, jobs or model calls. Report:', output)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    logging.getLogger('pypdf').setLevel(logging.ERROR)
    parser = argparse.ArgumentParser()
    parser.add_argument('--parsed', required=True)
    parser.add_argument('--references', type=int, nargs='+', required=True)
    parser.add_argument('--output', required=True)
    asyncio.run(replay(parser.parse_args()))
