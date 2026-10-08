from contextlib import asynccontextmanager
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure backend/.env is loaded even if CWD is repo root
backend_env = Path(__file__).resolve().parent.parent / ".env"
if backend_env.exists():
    load_dotenv(dotenv_path=backend_env, override=True)
else:
    load_dotenv(override=True)

from app.logging_config import configure_application_logging

configure_application_logging()

from app.api.routes.citations import router as citations_router
from app.api.routes.evidence import router as evidence_router
from app.api.routes.papers import router as papers_router
from app.api.routes.verification import router as verification_router
from app.api.routes.sources import router as sources_router

BACKEND_HOST = os.getenv("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT = int(os.getenv("PORT") or os.getenv("BACKEND_PORT", "8000"))


def _get_cors_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS") or os.getenv("FRONTEND_URL") or "http://localhost:5173"
    configured = [origin.strip() for origin in raw.split(",") if origin.strip()]
    dev_defaults = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "https://sciverify.vercel.app",
    ]
    return list(dict.fromkeys(configured + dev_defaults))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from app.researchguard.adapters.paperqa2 import clear_index_cache
    clear_index_cache()
    try:
        yield
    finally:
        clear_index_cache()


app = FastAPI(
    lifespan=lifespan,
    title="SciVerify Backend",
    description="Evidence-backed scientific citation verification API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(citations_router)
app.include_router(papers_router)
app.include_router(evidence_router)
app.include_router(verification_router)
app.include_router(sources_router)


@app.get("/health", tags=["health"])
@app.get("/api/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "sciverify-backend"}
