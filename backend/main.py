"""
ChainMind — FastAPI application entry point.

Startup sequence:
  1. Validate Azure OpenAI config
  2. Init SQLite DB + seed synthetic data (idempotent)
  3. Train / load ML models
  4. Mount routers
"""
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config
from database import init_db
from models import HealthResponse


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ────────────────────────────────────────────────────────────────
    warnings = config.validate_config()
    if warnings:
        print(f"⚠️  Config warnings: {warnings}", file=sys.stderr)

    init_db()

    # Train / load ML models lazily (imported here to avoid circular deps)
    try:
        from ml.train_models import ensure_models_trained
        ensure_models_trained()
    except Exception as exc:
        print(f"⚠️  ML model init failed (non-fatal): {exc}", file=sys.stderr)

    app.state.models_loaded = True
    print("🚀  ChainMind backend ready.")

    yield  # ── application runs ──────────────────────────────────────────────

    # ── Shutdown ───────────────────────────────────────────────────────────────
    print("👋  ChainMind shutting down.")


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=config.APP_TITLE,
    version=config.APP_VERSION,
    description="AI-powered supply chain network optimizer — Tesla MLE panel demo",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routers ────────────────────────────────────────────────────────────────────
# Imported after app creation to avoid circular imports

from routers import network, dashboard, optimize  # noqa: E402

app.include_router(network.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(optimize.router, prefix="/api")

# Chat router wired separately (requires agent which imports LangGraph)
try:
    from routers import chat  # noqa: E402
    app.include_router(chat.router, prefix="/api")
except Exception as exc:
    print(f"⚠️  Chat router unavailable: {exc}", file=sys.stderr)


# ── Health check ───────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["Meta"])
async def health_check() -> HealthResponse:
    from database import get_connection

    db_ok = False
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1")
        db_ok = True
    except Exception:
        pass

    warnings = config.validate_config()

    return HealthResponse(
        status="ok" if (db_ok and not warnings) else "degraded",
        version=config.APP_VERSION,
        db_connected=db_ok,
        models_loaded=getattr(app.state, "models_loaded", False),
        config_warnings=warnings,
    )


@app.get("/", tags=["Meta"])
async def root():
    return {
        "app": config.APP_TITLE,
        "version": config.APP_VERSION,
        "docs": "/docs",
        "health": "/health",
    }
