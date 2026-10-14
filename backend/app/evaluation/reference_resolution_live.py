"""Opt-in real PDF/GROBID/metadata API check. Never invokes extraction or verifier.

Run from backend: python -m app.evaluation.reference_resolution_live --pdf PATH
Results go to the ignored .cache directory; the original PDF is never copied.
"""
import argparse
import asyncio
import hashlib
import json
from collections import Counter
from pathlib import Path

import httpx
from pypdf import PdfReader

from app.main import app
from app.researchguard.domain import ParsedManuscript
from app.schemas.claim_extraction import ClaimExtractionRequest
from app.services.citation_context import fingerprint, from_request
from app.services.citation_resolver import resolve_doi, CitationNotFoundError, CitationResolverError


class MetadataOnlyClient(httpx.Client):
    def send(self, request, **kwargs):
        # Live test authorization covers these two destinations only. Keep the
        # existing resolver, but stop its third-provider fallback before I/O.
        if request.url.host not in {"api.crossref.org", "api.openalex.org"}:
            raise CitationNotFoundError("Provider outside the authorized live test")
        return super().send(request, **kwargs)


def confirm_doi(doi):
    with MetadataOnlyClient(trust_env=False, timeout=10) as client:
        return resolve_doi(doi, client=client)


async def run(pdf, output, confirm):
    content = pdf.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://live-local-test", timeout=240) as api:
        parsed_response = await api.post("/api/manuscripts/parse", files={"file":("manuscript.pdf",content,"application/pdf")})
        parsed_response.raise_for_status()
        original = parsed_response.json()
        (output/"live-parse.json").write_text(json.dumps(original,ensure_ascii=False,indent=2),encoding="utf-8")
        request = {k:original[k] for k in ("schema_version","scope","offset_unit","parsed")}
        resolved_response = await api.post("/api/manuscripts/resolve-references",json=request)
        resolved_response.raise_for_status()
        enriched_response = resolved_response.json()
        (output/"live-resolution.json").write_text(json.dumps(enriched_response,ensure_ascii=False,indent=2),encoding="utf-8")
    enriched_request = {k:enriched_response[k] for k in ("schema_version","scope","offset_unit","parsed")}
    canonical = from_request(ClaimExtractionRequest.model_validate(enriched_request))
    job_parsed = {**enriched_response["parsed"],"manuscript":{**enriched_response["parsed"]["manuscript"],"content_locator":"submitted:client-structure"},"diagnostics":[]}
    assert ParsedManuscript.model_validate(job_parsed) == canonical
    assert original["parsed"]["paragraphs"] == enriched_response["parsed"]["paragraphs"]
    assert original["parsed"]["citation_callouts"] == enriched_response["parsed"]["citation_callouts"]
    counts = Counter(r.resolution.status for r in canonical.references)
    confirmations = {}
    if confirm:
        for ref in canonical.references:
            if ref.resolution.status != "resolved" or not ref.doi:
                continue
            try:
                metadata = await asyncio.to_thread(confirm_doi,ref.doi)
                confirmations[ref.id] = {"status":"metadata_resolved","metadata":metadata.model_dump(mode="json")}
            except (CitationResolverError,CitationNotFoundError):
                confirmations[ref.id] = {"status":"provider_error"}
    async with httpx.AsyncClient(trust_env=False) as local:
        version_response = await local.get("http://127.0.0.1:8070/api/version",timeout=5)
        version = version_response.json() if version_response.status_code == 200 else None
    report = {
        "pdf_path":str(pdf),"pdf_sha256":digest,"bytes":len(content),"pages":len(PdfReader(pdf).pages),
        "title":canonical.manuscript.title,"grobid_version":version,"paragraphs":len(canonical.paragraphs),
        "references":len(canonical.references),"citation_callouts":len(canonical.citation_callouts),
        "original_doi_count":sum(bool(r["doi"]) for r in original["parsed"]["references"]),
        "newly_resolved_doi_count":sum(r.resolution.status=="resolved" and r.resolution.original_doi is None for r in canonical.references),
        "status_counts":dict(counts),"canonical_input_fingerprint":"sha256:"+fingerprint(canonical),
        "public_to_job_projection_equal":True,"confirmations":confirmations,
        "llm_calls":0,"embedding_calls":0,"scientific_verification":"NOT_RUN","full_text_retrieval":"NOT_RUN",
        "reference_results":[r.model_dump(mode="json") for r in canonical.references],
    }
    (output/"live-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in {"confirmations","reference_results"}},ensure_ascii=False,indent=2))
    for i,ref in enumerate(canonical.references,1):
        resolution=ref.resolution
        print(i,resolution.status,ref.doi,resolution.provider,resolution.match_reason,list(resolution.diagnostics),flush=True)
        if resolution.status != "resolved":
            for c in resolution.candidates:
                print("  CANDIDATE",c.doi,c.title,c.publication_type,c.years,c.rejection_reason)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf",type=Path,required=True)
    parser.add_argument("--output",type=Path,default=Path(".cache/reference-resolution"))
    parser.add_argument("--confirm",action="store_true",help="Also use the existing DOI-to-metadata resolver; no full text or LLM.")
    args=parser.parse_args()
    asyncio.run(run(args.pdf.resolve(),args.output.resolve(),args.confirm))
