"""Real disk writes at the Windows filename boundary, without shortening tmp_path."""
import os
from dataclasses import replace
from pathlib import Path

import pytest

from app.researchguard.source_locator import SourceLocator
from app.services.source_store import LocalSourceStore
from app.tests.test_source_lifecycle import artifact


@pytest.mark.parametrize('kind', ['doi', 'url'])
def test_long_path_reupload(tmp_path, monkeypatch, kind):
    original = artifact()
    if kind == 'url':
        locator = SourceLocator(kind='url', value='https://example.org/source.pdf')
        original = replace(original, doi=None, locator=locator,
            paper=original.paper.model_copy(update={'doi': None, 'paper_id': locator.key}))
    store = LocalSourceStore(tmp_path / 'sources')
    key = store._locator_path(original.source_locator).name
    metadata = store.root / original.raw_content_sha256 / key
    # Grow the path to 258 characters: .json works, .json.previous exceeds MAX_PATH.
    padding = 258 - len(str(metadata)) - 1
    assert padding > 0, 'The test parent must allow an initially accessible metadata path'
    store = LocalSourceStore(store.root / ('x' * padding))
    metadata = store.root / original.raw_content_sha256 / key
    assert len(str(metadata)) == 258
    assert len(str(metadata) + '.previous') >= 260
    # Enforce classic Windows limits even on Linux or long-path-enabled Windows;
    # successful operations still use the real atomic writer and filesystem.
    real_replace = os.replace

    def windows_replace(source, target):
        if len(str(target)) >= 260:
            raise FileNotFoundError(2, 'Windows path exceeds MAX_PATH', str(target))
        return real_replace(source, target)

    monkeypatch.setattr('app.services.source_store.os.replace', windows_replace)
    store.put(original)
    old_metadata = metadata.read_bytes()
    manual = replace(original, origin='manual', provider='manual-upload')
    store.put(manual)
    backup = metadata.with_suffix('.prev')
    assert backup.stem == metadata.stem  # Complete hash, including URL prefix.
    assert len(str(backup)) == len(str(metadata))
    assert backup.read_bytes() == old_metadata
    assert store.get_locator(original.source_locator) == manual
    assert (metadata.parent / 'source.html').read_bytes() == original.content
    # Further uploads must not overwrite the first acquisition record.
    latest = replace(manual, provider='second-manual-upload')
    store.put(latest)
    assert backup.read_bytes() == old_metadata
    assert store.get_locator(original.source_locator) == latest
    assert not list(metadata.parent.glob('.pending-*'))


def test_legacy_history_is_preserved(tmp_path):
    original = artifact()
    store = LocalSourceStore(tmp_path)
    store.put(original)
    metadata = store.root / original.raw_content_sha256 / store._lookup_path(original.doi).name
    # Existing historical records may themselves exceed classic MAX_PATH.
    legacy = Path(str(metadata) + '.previous')
    if os.name == 'nt':
        legacy = Path('\\\\?\\' + str(legacy.resolve()))
    legacy.write_bytes(b'older historical acquisition record')
    old_metadata = metadata.read_bytes()
    store.put(replace(original, origin='manual'))
    assert legacy.read_bytes() == b'older historical acquisition record'
    assert metadata.with_suffix('.prev').read_bytes() == old_metadata
    assert store.get(original.doi).origin == 'manual'
