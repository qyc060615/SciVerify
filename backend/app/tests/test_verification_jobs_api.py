"""Real ASGI routes, manual upload contract, and default/local access boundaries."""
import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.citation import CitationMetadata
from app.services.verification_job_store import LocalJobStore
from app.tests.test_manuscript_verification import inputs, paper
from app.tests.test_verification_jobs import harness
from app.tests.test_source_lifecycle import pdf_bytes, TITLE


@pytest.fixture
async def api(harness, monkeypatch):
    h = harness(blocked=["10.1234/local"])
    monkeypatch.setenv("RESEARCHGUARD_JOBS_ENABLED", "1")
    monkeypatch.setenv("RESEARCHGUARD_SOURCE_CACHE_DIR", str(h.source_store.root))
    monkeypatch.setattr(app.state, "verification_jobs", h.runtime, raising=False)
    await h.runtime.start()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 12345)),
        base_url="http://testserver") as client:
        yield client, h


def body():
    parsed, extraction = inputs()
    return {"parsed": parsed.model_dump(mode="json"), "extraction": extraction.model_dump(mode="json")}


@pytest.mark.anyio
async def test_api_create_partial_read_events_manual_upload_resume(api, monkeypatch):
    client, h = api
    payload = body()
    payload["parsed"]["manuscript"]["content_locator"] = "C:/private/client/paper.pdf"
    response = await client.post("/api/verification/jobs", json=payload)
    assert response.status_code == 202
    created = response.json()
    assert created["input_provenance"] == "client_supplied"
    assert "content_locator" not in response.text and "private/client" not in response.text
    job_id = created["job_id"]
    waiting = await h.runtime.wait(job_id)
    read = await client.get(f"/api/verification/jobs/{job_id}")
    assert read.json()["status"] == "waiting_for_source"
    assert read.json()["coverage"]["blocked_source_pairs"] == 1
    before_events = (await client.get(f"/api/verification/jobs/{job_id}/events")).json()
    assert [e["sequence"] for e in before_events["events"]] == list(range(1, before_events["next_sequence"]))
    last = before_events["events"][-1]["sequence"]
    assert not (await client.get(f"/api/verification/jobs/{job_id}/events", params={"after": last})).json()["events"]
    assert h.store.load(job_id) == waiting
    doi = "10.1234/local"
    monkeypatch.setattr("app.services.manual_source.resolve_doi", lambda value: CitationMetadata(
        doi=doi, title=TITLE, authors=["Ada Lovelace"], year=2020, source="crossref", type="journal-article"))
    content = pdf_bytes(lines=[TITLE, "Ada Lovelace 2020", "doi: " + doi,
                               "Results", "Treatment reduces risk by 12% in patients."])
    uploaded = await client.post("/api/sources/manual", data={"doi": doi},
        files={"file": ("ignored.pdf", content, "application/pdf")})
    assert uploaded.status_code == 200 and uploaded.json()["identity_match"] == "doi"
    digest = uploaded.json()["raw_content_sha256"]
    # Repeating the same existing upload preserves the content-addressed version.
    repeated = await client.post("/api/sources/manual", data={"doi": doi}, files={"file": ("same.pdf", content)})
    assert repeated.json()["raw_content_sha256"] == digest
    resumed = await client.post(f"/api/verification/jobs/{job_id}/resume", json={
        "expected_revision": waiting.revision, "reference_ids": ["r1"], "source_hashes": {"r1": digest}})
    assert resumed.status_code == 202
    final = await h.runtime.wait(job_id)
    assert final.state == "completed" and len(h.verified) == 1
    result = (await client.get(f"/api/verification/jobs/{job_id}")).json()
    assert result["tasks"][0]["source_version"] == "sha256:" + digest
    assert result["tasks"][0]["pair_outcome"]["verification"]["claim_id"] == "claim0"
    replay = (await client.get(f"/api/verification/jobs/{job_id}/events", params={"after": last})).json()
    assert all(e["sequence"] > last for e in replay["events"])
    unchanged = await client.post(f"/api/verification/jobs/{job_id}/resume", json={"expected_revision": final.revision})
    assert unchanged.status_code == 202 and unchanged.json()["revision"] == final.revision


@pytest.mark.anyio
@pytest.mark.parametrize("error", ["reference", "revision", "hash_required", "not_accepted", "hash_invalid"])
async def test_resume_stable_errors_no_partial_commit(api, error):
    client, h = api
    created = await client.post("/api/verification/jobs", json=body())
    job_id = created.json()["job_id"]
    waiting = await h.runtime.wait(job_id)
    payload = {"expected_revision": waiting.revision}
    expected = {"reference": (422, "JOB_REFERENCE_UNKNOWN"), "revision": (409, "JOB_REVISION_CONFLICT"),
        "hash_required": (422, "JOB_SOURCE_HASH_REQUIRED"), "not_accepted": (409, "JOB_SOURCE_NOT_ACCEPTED"),
        "hash_invalid": (422, "JOB_INPUT_INVALID")}[error]
    if error == "reference":
        payload["reference_ids"] = ["foreign"]
    elif error == "revision":
        payload["expected_revision"] = 0
    elif error == "not_accepted":
        payload["source_hashes"] = {"r1": "a" * 64}
    elif error == "hash_invalid":
        payload["source_hashes"] = {"r1": "bad"}
    response = await client.post(f"/api/verification/jobs/{job_id}/resume", json=payload)
    assert response.status_code == expected[0] and response.json()["detail"]["code"] == expected[1]
    assert h.store.load(job_id) == waiting


@pytest.mark.anyio
async def test_bad_input_id_missing_and_corrupt_snapshot(api):
    client, h = api
    bad = body()
    bad["extraction"]["metadata"]["input_fingerprint"] = "bad"
    response = await client.post("/api/verification/jobs", json=bad)
    assert response.status_code == 422 and not h.store.list_job_ids()
    assert (await client.get("/api/verification/jobs/invalid")).json()["detail"]["code"] == "JOB_ID_INVALID"
    assert (await client.get("/api/verification/jobs/job_" + "a" * 32)).status_code == 404
    created = await client.post("/api/verification/jobs", json=body())
    job_id = created.json()["job_id"]
    await h.runtime.wait(job_id)
    path = h.store.root / (job_id + ".json")
    path.write_text("{bad")
    response = await client.get(f"/api/verification/jobs/{job_id}")
    assert response.status_code == 500 and response.json()["detail"]["code"] == "JOB_SNAPSHOT_CORRUPT"
    assert path.read_text() == "{bad"


@pytest.mark.anyio
@pytest.mark.parametrize("method,path", [("POST", ""), ("GET", "/job_" + "a" * 32),
    ("GET", "/job_" + "a" * 32 + "/events"), ("POST", "/job_" + "a" * 32 + "/resume")])
async def test_disabled_flag_blocks_every_endpoint(api, monkeypatch, method, path):
    client, h = api
    monkeypatch.setenv("RESEARCHGUARD_JOBS_ENABLED", "0")
    response = await client.request(method, "/api/verification/jobs" + path, json=body())
    assert response.status_code == 404 and response.json()["detail"]["code"] == "JOBS_DISABLED"
    assert not h.store.list_job_ids()


@pytest.mark.anyio
async def test_nonlocal_peer_denied_even_when_enabled(api):
    _, h = api
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("203.0.113.5", 1234)),
        base_url="http://testserver") as client:
        response = await client.post("/api/verification/jobs", json=body())
    assert response.status_code == 403 and response.json()["detail"]["code"] == "JOBS_LOCAL_ONLY"
    assert not h.store.list_job_ids()


def test_real_app_lifespan_recovers_without_starting_providers(tmp_path, monkeypatch):
    from app.tests.test_verification_job_store import snapshot
    from app.services.verification_job_models import JobState
    from app.services.verification_jobs import evolve
    store = LocalJobStore(tmp_path)
    original = snapshot()
    store.create(original)
    store.commit(evolve(original, "job_started", JobState.RUNNING), expected_revision=0)
    monkeypatch.setenv("RESEARCHGUARD_JOBS_ENABLED", "1")
    monkeypatch.setenv("RESEARCHGUARD_JOB_DIR", str(tmp_path))
    def forbidden(*args, **kwargs):
        pytest.fail("Startup recovery must never call a provider")
    monkeypatch.setattr("app.services.paper_retriever.retrieve_paper", forbidden)
    monkeypatch.setattr("app.services.llm.provider.get_llm_provider", forbidden)
    with TestClient(app) as client:
        response = client.get(f"/api/verification/jobs/{original.job_id}")
        assert response.status_code == 200 and response.json()["status"] == "interrupted"
        assert not app.state.verification_jobs._workers
    assert app.state.verification_jobs is None


@pytest.mark.anyio
async def test_oversized_request_is_rejected_before_creation(api):
    from app.services.manuscript_verification import MAX_INPUT_BYTES
    client, h = api
    response = await client.post("/api/verification/jobs", content=b"x" * (MAX_INPUT_BYTES + 1))
    assert response.status_code == 413 and not h.store.list_job_ids()


@pytest.mark.anyio
async def test_mismatched_manual_pdf_keeps_job_blocked(api, monkeypatch):
    client, h = api
    created = await client.post("/api/verification/jobs", json=body())
    job_id = created.json()["job_id"]
    waiting = await h.runtime.wait(job_id)
    doi = "10.1234/local"
    monkeypatch.setattr("app.services.manual_source.resolve_doi", lambda value: CitationMetadata(
        doi=doi, title=TITLE, authors=["Ada Lovelace"], year=2020, source="crossref", type="journal-article"))
    wrong = pdf_bytes(lines=[TITLE, "doi: 10.1234/foreign", "Results", "Treatment reduces risk."])
    response = await client.post("/api/sources/manual", data={"doi": doi}, files={"file": ("wrong.pdf", wrong)})
    assert response.status_code == 400 and response.json()["detail"]["code"] == "SOURCE_MISMATCH"
    assert h.source_store.get(doi) is None and h.store.load(job_id) == waiting and not h.verified


@pytest.mark.anyio
@pytest.mark.parametrize('after_replace', [False, True])
async def test_runtime_error_does_not_hide_atomic_checkpoint(api, monkeypatch, after_replace):
    import json
    import app.services.verification_job_store as module
    from app.services.verification_job_store import JobError
    from app.services.verification_jobs import VerificationJobRuntime
    from app.schemas.verification_jobs import JobView
    client, h = api
    h.blocked.clear()
    original = module.os.replace
    injected = []
    def replace_fault(src, dst):
        if str(dst).endswith('.json') and str(src).endswith('.tmp'):
            envelope = json.loads(__import__('pathlib').Path(src).read_bytes())
            if envelope['snapshot']['events'][-1]['event_type'] == 'pair_completed' and not injected:
                injected.append(True)
                if after_replace:
                    original(src, dst)
                raise OSError('injected atomic checkpoint error')
        return original(src, dst)
    monkeypatch.setattr(module.os, 'replace', replace_fault)
    created = await client.post('/api/verification/jobs', json=body())
    job_id = created.json()['job_id']
    with pytest.raises(JobError, match='JOB_STORAGE_ERROR'):
        await h.runtime.wait(job_id)
    read = await client.get('/api/verification/jobs/' + job_id)
    assert read.status_code == 200
    data = read.json()
    assert data['runtime_error_code'] == 'JOB_STORAGE_ERROR'
    assert h.runtime.errors[job_id] == 'JOB_STORAGE_ERROR'
    events = (await client.get('/api/verification/jobs/' + job_id + '/events')).json()
    assert events['runtime_error_code'] == 'JOB_STORAGE_ERROR'
    assert sum(e['event_type'] == 'pair_completed' for e in events['events']) == int(after_replace)
    legacy_shape = dict(data)
    legacy_shape.pop('runtime_error_code')
    assert JobView.model_validate(legacy_shape).runtime_error_code is None
    saved = h.runtime.get(job_id)
    if after_replace:
        assert data['status'] == 'completed'
        assert data['tasks'][0]['pair_outcome']['verification']['verdict'] == 'SUPPORTED'
        for _ in range(2):
            repeated = await client.post('/api/verification/jobs/' + job_id + '/resume', json={'expected_revision': saved.revision})
            assert repeated.status_code == 202 and repeated.json()['runtime_error_code'] == 'JOB_STORAGE_ERROR'
        assert h.runtime.get(job_id) == saved and len(h.verified) == 1
    else:
        assert data['status'] == 'interrupted'
        assert data['tasks'][0]['pair_outcome'] is None
        resumed = await client.post('/api/verification/jobs/' + job_id + '/resume', json={'expected_revision': saved.revision})
        assert resumed.status_code == 202 and resumed.json()['runtime_error_code'] == 'JOB_STORAGE_ERROR'
        final = await h.runtime.wait(job_id)
        assert final.state == 'completed' and job_id not in h.runtime.errors
    restarted = VerificationJobRuntime(LocalJobStore(h.store.root), source_store=h.source_store, core_dependencies=h.dependencies)
    await restarted.start()
    assert restarted.get(job_id) == h.store.load(job_id)
    assert len(h.verified) == (1 if after_replace else 2)
    await restarted.shutdown(0)


@pytest.mark.anyio
async def test_snapshot_corruption_takes_priority_over_runtime_error(api):
    client, h = api
    created = await client.post('/api/verification/jobs', json=body())
    job_id = created.json()['job_id']
    await h.runtime.wait(job_id)
    h.runtime.errors[job_id] = 'JOB_STORAGE_ERROR'
    (h.store.root / (job_id + '.json')).write_bytes(b'{broken')
    for suffix in ('', '/events'):
        response = await client.get('/api/verification/jobs/' + job_id + suffix)
        assert response.status_code == 500
        assert response.json()['detail']['code'] == 'JOB_SNAPSHOT_CORRUPT'
    assert h.runtime.errors[job_id] == 'JOB_STORAGE_ERROR'
