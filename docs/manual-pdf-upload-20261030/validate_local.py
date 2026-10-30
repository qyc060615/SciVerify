"""Validate real local PDFs in an isolated store. No downloads or model calls."""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'

from fastapi.testclient import TestClient
from app.main import app
from app.researchguard.domain import Reference
from app.researchguard.adapters.sciverify import accepted_source_to_domain
from app.schemas.citation import CitationMetadata
from app.services.source_acquisition import retrieve_reference_source
from app.services.manual_source import review_manual_source
from app.services.source_preparation import prepare_reference
from app.services.source_store import LocalSourceStore, verify_source_durability


cases = [
    ('R10', 'He_Deep_Residual_Learning_CVPR_2016_paper.pdf', '10.1109/cvpr.2016.90',
     'Deep residual learning for image recognition', ['Kaiming He', 'Xiangyu Zhang', 'Shaoqing Ren', 'Jian Sun'], 2016),
    ('R12', '2604.pdf', '10.1162/neco.1997.9.8.1735',
     'Long short-term memory', ['Sepp Hochreiter', 'Jürgen Schmidhuber'], 1997),
]
results = []
live = LocalSourceStore(ROOT / 'backend/data/researchguard/sources')
original_connect = socket.socket.connect
def local_connect(sock, address):
    if not isinstance(address, tuple) or not ipaddress.ip_address(address[0]).is_loopback:
        raise AssertionError('No public network permitted')
    return original_connect(sock, address)

with tempfile.TemporaryDirectory(prefix='rg-manual-real-') as isolated:
    with patch.dict(os.environ, {'RESEARCHGUARD_SOURCE_CACHE_DIR': isolated}), \
            patch.object(socket.socket, 'connect', local_connect):
        for number, filename, doi, title, authors, year in cases:
            pdf = ROOT.parent / filename
            content = pdf.read_bytes()
            ref = Reference(id=number, manuscript_id='real-local-validation', raw_text=title,
                doi=doi, title=title, authors=tuple(authors), year=year)
            citation = CitationMetadata(doi=doi, title=title, authors=authors, year=year, source='crossref')
            store = LocalSourceStore()
            previous = live.get(doi)
            if previous:
                store.put(previous)
            before = prepare_reference(ref)
            old_conflict_rejected = None
            if previous and before['identity'] == 'CONFLICT':
                old_conflict_rejected = review_manual_source(previous, ref)['match'] is None
                assert old_conflict_rejected
            with patch('app.services.manual_source.resolve_doi', return_value=citation):
                response = TestClient(app).post('/api/sources/manual',
                    data={'doi': doi, 'reference': ref.model_dump_json()},
                    files={'file': (filename, content, 'application/pdf')})
            assert response.status_code == 200, response.text
            receipt = response.json()
            ready = prepare_reference(ref)
            stage4 = retrieve_reference_source(ref, local_only=True)
            verify_source_durability(stage4, store)
            source, chunks = accepted_source_to_domain(stage4)
            digest = hashlib.sha256(content).hexdigest()
            assert ready['state'] == 'available', ready
            assert ready['raw_content_sha256'] == digest == receipt['raw_content_sha256']
            assert source.content_hash == 'sha256:' + digest and chunks
            saved = store.get(doi)
            assert saved.origin == 'manual' and saved.provenance.matched_doi is None
            if previous:
                old_raw = store.root / previous.raw_content_sha256 / ('source.' + previous.format)
                assert old_raw.read_bytes() == previous.content
            results.append({'reference': number, 'file': str(pdf), 'doi': doi,
                'before': {'state': before['state'], 'identity': before['identity'], 'old_conflict_rejected': old_conflict_rejected,
                    'hash': previous.raw_content_sha256 if previous else None},
                'after': {'state': ready['state'], 'identity': ready['identity'], 'hash': digest,
                    'identity_match': receipt['identity_match'], 'warnings': list(saved.provenance.warnings)},
                'stage4': {'hash': source.content_hash, 'chunks': len(chunks), 'cache_hit': stage4.source.cache_hit}})
Path(__file__).with_name('real-pdf-results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(results, ensure_ascii=False, indent=2))
