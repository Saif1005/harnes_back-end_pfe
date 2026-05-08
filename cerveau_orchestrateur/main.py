"""Point d'entrée FastAPI du cerveau orchestrateur."""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router as api_router
from src.core.database import init_db
from src.services.sqlite_s3_sync import SQLiteS3SyncManager

# Origines autorisées pour le frontend (ex. Vite en local vers API sur EC2).
# Exemple : CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,https://app.example.com
_cors_raw = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
)
_cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]

app = FastAPI(
    title="Cerveau Orchestrateur Sotipapier",
    version="1.0.0",
)
sqlite_sync = SQLiteS3SyncManager()


@app.on_event("startup")
def on_startup() -> None:
    sqlite_sync.restore_if_available()
    init_db()
    sqlite_sync.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    sqlite_sync.stop()

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1", tags=["agent"])

