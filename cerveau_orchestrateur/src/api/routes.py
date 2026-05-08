"""Routes FastAPI exposant le cerveau orchestrateur."""
from __future__ import annotations

import asyncio
import csv
import json
import os
import re
import threading
import uuid
from io import StringIO
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token as google_id_token
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from src.agent.graph import brain_app
from src.api.schemas import (
    AdminSessionResponse,
    AdminMonitoringOverviewResponse,
    SelfLearningJobResponse,
    SelfLearningRetrainRequest,
    AuthAdminForgotPasswordRequest,
    AuthAdminRegistrationStatusResponse,
    AuthAdminRegisterRequest,
    AuthAdminBootstrapRequest,
    AuthGoogleLoginRequest,
    AuthLoginRequest,
    AuthRegisterRequest,
    AuthTokenResponse,
    AuthUserResponse,
    AskAgentRequest as AgentRequest,
    AskAgentResponse,
    ERPConfigResponse,
    ERPConfigUpsertRequest,
    ERPConnectionTestResponse,
    FileClassificationJobResponse,
    LongTermMemoryItem,
    LongTermMemoryListResponse,
    LongTermMemoryUpsertRequest,
    ProductionDashboardResponse,
    WarehouseDatabaseSummaryResponse,
    WarehouseIngestionJobResponse,
    ShortTermMemoryCreateRequest,
    ShortTermMemoryItem,
    ShortTermMemoryListResponse,
)
from src.core.config import get_settings
from src.core.database import get_db
from src.core.security import create_access_token, decode_access_token, hash_password, verify_password
from src.models.entities import ERPConfig, User
from src.models.entities import LongTermMemory, ShortTermMemory, WarehouseInventoryRecord, WarehouseStockSnapshot
from src.services.file_classification import create_job, get_job, parse_uploaded_file, run_job
from src.services.file_classification import JOBS, JOBS_LOCK
from src.services.memory_store import (
    append_short_term_memory,
    generate_session_id,
    list_long_term_memories,
    list_short_term_memories,
    record_ask_agent_turn,
    upsert_long_term_memory,
)
from src.services.production_dashboard import build_production_dashboard
from src.services.self_learning import create_retrain_job, get_job as get_self_learning_job, run_retrain_job
from src.services.warehouse_ingestion import cancel_ingest_job, create_ingest_job, get_ingest_job, run_ingest_job

router = APIRouter()
APP_START_AT = datetime.now(timezone.utc)


def _normalize_preferred_route(raw: str) -> str:
    r = (raw or "").strip().lower()
    if r in {"classification", "recette", "workflow", "human"}:
        return r
    return ""


def _extract_bearer_token(http_request: Request) -> str:
    auth = str(http_request.headers.get("Authorization") or "").strip()
    if not auth.lower().startswith("bearer "):
        return ""
    return auth.split(" ", 1)[1].strip()


def _user_to_schema(user: User) -> AuthUserResponse:
    return AuthUserResponse(
        id=str(user.id),
        email=str(user.email),
        name=str(user.name or ""),
        role=str(user.role or "operator"),
    )


def _get_current_user_optional(http_request: Request, db: Session) -> User | None:
    token = _extract_bearer_token(http_request)
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    user_id = str(payload.get("sub") or "")
    if not user_id:
        return None
    user = db.get(User, user_id)
    if not user or not user.is_active:
        return None
    return user


def _get_current_user_required(http_request: Request, db: Session) -> User:
    user = _get_current_user_optional(http_request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentification requise.")
    return user


def _safe_json_load(raw: str) -> dict:
    try:
        parsed = json.loads(raw or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _mask_password(raw: str) -> str:
    s = str(raw or "")
    if not s:
        return ""
    if len(s) <= 4:
        return "*" * len(s)
    return f"{s[:2]}{'*' * (len(s) - 4)}{s[-2:]}"


def _require_admin(http_request: Request, db: Session) -> User:
    user = _get_current_user_required(http_request, db)
    if str(user.role or "").lower() != "admin":
        raise HTTPException(status_code=403, detail="Rôle admin requis.")
    return user


def _allowed_google_client_ids() -> set[str]:
    settings = get_settings()
    raw = str(settings.auth_google_client_ids or "")
    ids = {x.strip() for x in raw.split(",") if x.strip()}
    return ids


def _admin_emails() -> set[str]:
    settings = get_settings()
    raw = str(settings.auth_admin_emails or "")
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def _has_admin_user(db: Session) -> bool:
    row = db.execute(select(User.id).where(User.role == "admin").limit(1)).first()
    return bool(row)


def _erp_db_url(
    db_type: str,
    host: str,
    port: int,
    db_name: str,
    username: str,
    password: str,
) -> str:
    kind = str(db_type or "").strip().lower()
    if kind in {"postgres", "postgresql"}:
        return f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{db_name}"
    if kind == "mysql":
        return f"mysql+pymysql://{username}:{password}@{host}:{port}/{db_name}"
    if kind in {"sqlserver", "mssql"}:
        return (
            f"mssql+pyodbc://{username}:{password}@{host}:{port}/{db_name}"
            "?driver=ODBC+Driver+17+for+SQL+Server"
        )
    if kind == "sqlite":
        return f"sqlite:///{db_name}"
    raise HTTPException(status_code=400, detail="db_type non supporté (postgresql/mysql/sqlserver/sqlite).")


@router.post("/auth/register", response_model=AuthTokenResponse)
async def auth_register(payload: AuthRegisterRequest, db: Session = Depends(get_db)) -> AuthTokenResponse:
    email = payload.email.strip().lower()
    password = payload.password or ""
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Email invalide.")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Mot de passe trop court (min 8 caractères).")

    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Cet email existe déjà.")

    role = "admin" if email in _admin_emails() else "operator"
    user = User(
        id=str(uuid.uuid4()),
        email=email,
        name=(payload.name or "").strip(),
        password_hash=hash_password(password),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(subject=str(user.id), extra={"email": user.email, "role": user.role})
    return AuthTokenResponse(access_token=token, user=_user_to_schema(user))


@router.get("/auth/admin/registration-status", response_model=AuthAdminRegistrationStatusResponse)
async def auth_admin_registration_status(db: Session = Depends(get_db)) -> AuthAdminRegistrationStatusResponse:
    return AuthAdminRegistrationStatusResponse(admin_exists=_has_admin_user(db))


@router.post("/auth/register/admin", response_model=AuthTokenResponse)
async def auth_register_admin(payload: AuthAdminRegisterRequest, db: Session = Depends(get_db)) -> AuthTokenResponse:
    if _has_admin_user(db):
        raise HTTPException(status_code=409, detail="Un compte admin existe déjà. Inscription admin fermée.")

    settings = get_settings()
    expected = str(settings.auth_admin_bootstrap_key or "").strip()
    if expected and str(payload.bootstrap_key or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Bootstrap key admin invalide.")

    email = payload.email.strip().lower()
    password = payload.password or ""
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Email invalide.")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Mot de passe trop court (min 8 caractères).")

    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Cet email existe déjà.")

    user = User(
        id=str(uuid.uuid4()),
        email=email,
        name=(payload.name or "").strip(),
        password_hash=hash_password(password),
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(subject=str(user.id), extra={"email": user.email, "role": user.role})
    return AuthTokenResponse(access_token=token, user=_user_to_schema(user))


@router.post("/auth/login", response_model=AuthTokenResponse)
async def auth_login(payload: AuthLoginRequest, db: Session = Depends(get_db)) -> AuthTokenResponse:
    email = payload.email.strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or not verify_password(payload.password or "", user.password_hash):
        raise HTTPException(status_code=401, detail="Identifiants invalides.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte désactivé.")

    if email in _admin_emails() and str(user.role or "").lower() != "admin":
        user.role = "admin"
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(subject=str(user.id), extra={"email": user.email, "role": user.role})
    return AuthTokenResponse(access_token=token, user=_user_to_schema(user))


@router.post("/auth/google", response_model=AuthTokenResponse)
async def auth_google_login(payload: AuthGoogleLoginRequest, db: Session = Depends(get_db)) -> AuthTokenResponse:
    token_raw = str(payload.id_token or "").strip()
    if not token_raw:
        raise HTTPException(status_code=400, detail="id_token Google requis.")

    allowed_ids = _allowed_google_client_ids()
    if not allowed_ids:
        raise HTTPException(
            status_code=503,
            detail="Google login non configuré côté serveur (AUTH_GOOGLE_CLIENT_IDS manquant).",
        )

    try:
        token_info = google_id_token.verify_oauth2_token(token_raw, GoogleAuthRequest(), audience=None)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=401, detail=f"Token Google invalide: {exc}") from exc

    aud = str(token_info.get("aud") or "")
    if aud not in allowed_ids:
        raise HTTPException(status_code=401, detail="Client Google non autorisé.")

    email = str(token_info.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=401, detail="Email Google invalide.")
    if not bool(token_info.get("email_verified")):
        raise HTTPException(status_code=401, detail="Email Google non vérifié.")

    name = str(token_info.get("name") or "").strip()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    role = "admin" if email in _admin_emails() else "operator"
    if user is None:
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            name=name,
            password_hash=hash_password(str(uuid.uuid4())),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        changed = False
        if name and name != str(user.name or ""):
            user.name = name
            changed = True
        if role == "admin" and str(user.role or "").lower() != "admin":
            user.role = "admin"
            changed = True
        if changed:
            db.add(user)
            db.commit()
            db.refresh(user)

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte désactivé.")

    token = create_access_token(subject=str(user.id), extra={"email": user.email, "role": user.role})
    return AuthTokenResponse(access_token=token, user=_user_to_schema(user))


@router.post("/auth/admin/bootstrap", response_model=AuthUserResponse)
async def auth_admin_bootstrap(payload: AuthAdminBootstrapRequest, db: Session = Depends(get_db)) -> AuthUserResponse:
    settings = get_settings()
    expected = str(settings.auth_admin_bootstrap_key or "")
    if not expected:
        raise HTTPException(status_code=503, detail="Bootstrap admin non configuré.")
    if str(payload.bootstrap_key or "") != expected:
        raise HTTPException(status_code=401, detail="Bootstrap key invalide.")

    email = str(payload.email or "").strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    user.role = "admin"
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_to_schema(user)


@router.post("/auth/admin/forgot-password")
async def auth_admin_forgot_password(
    payload: AuthAdminForgotPasswordRequest, db: Session = Depends(get_db)
) -> dict[str, str]:
    expected = str(get_settings().auth_admin_bootstrap_key or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Bootstrap admin non configuré.")
    if str(payload.bootstrap_key or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Bootstrap key invalide.")

    email = str(payload.email or "").strip().lower()
    new_password = str(payload.new_password or "")
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Mot de passe trop court (min 8 caractères).")

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or str(user.role or "").lower() != "admin":
        raise HTTPException(status_code=404, detail="Admin introuvable.")

    user.password_hash = hash_password(new_password)
    db.add(user)
    db.commit()
    return {"status": "ok", "message": "Mot de passe admin réinitialisé."}


@router.get("/auth/admin/session", response_model=AdminSessionResponse)
async def auth_admin_session(http_request: Request, db: Session = Depends(get_db)) -> AdminSessionResponse:
    user = _require_admin(http_request, db)
    return AdminSessionResponse(
        session_id=f"admin-{uuid.uuid4()}",
        user=_user_to_schema(user),
        permissions=["erp_config:read", "erp_config:write", "erp_config:test", "system:admin"],
    )


@router.get("/auth/me", response_model=AuthUserResponse)
async def auth_me(http_request: Request, db: Session = Depends(get_db)) -> AuthUserResponse:
    user = _get_current_user_required(http_request, db)
    return _user_to_schema(user)


@router.post("/auth/logout")
async def auth_logout() -> dict[str, str]:
    # JWT stateless : la vraie invalidation se fait côté client (suppression token)
    return {"status": "ok", "message": "Déconnexion effectuée côté client."}


@router.post("/ask_agent", response_model=AskAgentResponse)
async def ask_agent(
    payload: AgentRequest,
    http_request: Request,
    db: Session = Depends(get_db),
) -> AskAgentResponse:
    forced = _normalize_preferred_route(payload.preferred_route)
    current_user = _get_current_user_optional(http_request, db)
    session_id = (payload.session_id or "").strip() or generate_session_id()
    initial_state = {
        "messages": [HumanMessage(content=payload.question_operateur or "")],
        "id_article_erp": payload.id_article_erp,
        "description": payload.description,
        "categorie": payload.categorie or "",
        "question_operateur": payload.question_operateur or "",
        "route_intent": forced,
        "statut_classification": "EN_ATTENTE",
        "categorie_cible": "EN_ATTENTE",
        "resultat_agent_brut": "",
        "recipe": {},
        "stock_alerts": [],
        "final_response": "",
        "confirm_production": bool(payload.confirm_production),
        "confirmation_token_input": (payload.confirmation_token or "").strip(),
        "confirmation_token": "",
        "confirmation_required": False,
        "production_applied": False,
        "inventory": {},
        "inventory_dashboard": {},
        "production_capacity": {},
        "stock_prediction": {},
    }

    try:
        final_state = await brain_app.ainvoke(initial_state)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    messages = final_state.get("messages") or []
    last = messages[-1] if messages else None
    if last is None:
        reponse_agent = ""
    elif isinstance(last, AIMessage):
        reponse_agent = str(last.content or "")
    else:
        reponse_agent = str(getattr(last, "content", last))

    response = AskAgentResponse(
        id_article_erp=str(final_state.get("id_article_erp") or payload.id_article_erp),
        route_intent=str(final_state.get("route_intent") or ""),
        statut_classification=str(final_state.get("statut_classification") or "INCONNU"),
        categorie_cible=str(final_state.get("categorie_cible") or "INCONNUE"),
        resultat_agent_brut=str(final_state.get("resultat_agent_brut") or ""),
        stock_alerts=list(final_state.get("stock_alerts") or []),
        recipe_items=list(
            final_state.get("recipe_items")
            or (dict(final_state.get("recipe") or {}).get("items") or [])
        ),
        production_capacity=dict(final_state.get("production_capacity") or {}),
        stock_prediction=dict(final_state.get("stock_prediction") or {}),
        final_response=str(final_state.get("final_response") or reponse_agent),
        confirmation_required=bool(final_state.get("confirmation_required") or False),
        confirmation_token=str(final_state.get("confirmation_token") or ""),
        production_applied=bool(final_state.get("production_applied") or False),
        inventory_dashboard=dict(final_state.get("inventory_dashboard") or {}),
        reponse_agent=reponse_agent,
    )

    try:
        record_ask_agent_turn(
            db,
            user_id=str(current_user.id) if current_user else None,
            session_id=session_id,
            question=str(payload.question_operateur or ""),
            response=response.final_response or response.reponse_agent,
            route_intent=response.route_intent or "",
            article_id=payload.id_article_erp,
        )
    except Exception:  # noqa: BLE001
        # La persistance mémoire ne doit pas bloquer l'orchestrateur.
        pass
    return response


@router.get("/dashboard/production_trends", response_model=ProductionDashboardResponse)
async def dashboard_production_trends(
    start_year: int = Query(default=2017, ge=2010, le=2100),
    max_articles: int = Query(default=6, ge=1, le=20),
    article: str = Query(default=""),
) -> ProductionDashboardResponse:
    try:
        payload = build_production_dashboard(
            start_year=int(start_year),
            max_articles=int(max_articles),
            selected_article=article,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"dashboard_production_trends_error: {exc}") from exc
    return ProductionDashboardResponse(**payload)


@router.post("/classification/upload", response_model=FileClassificationJobResponse)
async def classification_upload_file(
    file: UploadFile = File(...),
    categorie_default: str = Form(default=""),
) -> FileClassificationJobResponse:
    filename = file.filename or "uploaded_file"
    if not filename.lower().endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Format non supporté. Utilisez CSV/XLSX.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Fichier vide.")

    try:
        rows = parse_uploaded_file(content, filename=filename, categorie_default=categorie_default)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Erreur lecture fichier: {exc}") from exc

    if not rows:
        raise HTTPException(status_code=400, detail="Aucune ligne exploitable (description absente).")

    job_id = create_job(filename=filename, total_rows=len(rows))
    asyncio.create_task(run_job(job_id, rows))
    payload = get_job(job_id)
    if not payload:
        raise HTTPException(status_code=500, detail="Impossible de créer le job.")
    payload["recent_results"] = []
    return FileClassificationJobResponse(**payload)


@router.get("/classification/upload/{job_id}", response_model=FileClassificationJobResponse)
async def classification_upload_status(
    job_id: str,
    limit: int = Query(default=100, ge=1, le=500),
) -> FileClassificationJobResponse:
    payload = get_job(job_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Job introuvable.")

    results = list(payload.get("results") or [])
    payload["recent_results"] = results[-limit:]
    return FileClassificationJobResponse(**payload)


@router.post("/memory/short-term", response_model=ShortTermMemoryItem)
async def create_short_term_memory(
    payload: ShortTermMemoryCreateRequest,
    http_request: Request,
    db: Session = Depends(get_db),
) -> ShortTermMemoryItem:
    user = _get_current_user_required(http_request, db)
    session_id = (payload.session_id or "").strip() or generate_session_id()
    row = append_short_term_memory(
        db,
        session_id=session_id,
        user_id=str(user.id),
        role=(payload.role or "user").strip().lower()[:32],
        content=str(payload.content or "").strip(),
        metadata=dict(payload.metadata or {}),
    )
    return ShortTermMemoryItem(
        id=int(row.id),
        session_id=str(row.session_id),
        turn_index=int(row.turn_index),
        role=str(row.role),
        content=str(row.content),
        metadata=_safe_json_load(row.metadata_json),
        created_at=row.created_at.isoformat(),
    )


@router.get("/memory/short-term", response_model=ShortTermMemoryListResponse)
async def get_short_term_memory(
    http_request: Request,
    session_id: str = Query(default=""),
    limit: int = Query(default=30, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ShortTermMemoryListResponse:
    user = _get_current_user_required(http_request, db)
    sid = session_id.strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id requis.")
    rows = list_short_term_memories(db, session_id=sid, user_id=str(user.id), limit=limit)
    return ShortTermMemoryListResponse(
        session_id=sid,
        items=[
            ShortTermMemoryItem(
                id=int(r.id),
                session_id=str(r.session_id),
                turn_index=int(r.turn_index),
                role=str(r.role),
                content=str(r.content),
                metadata=_safe_json_load(r.metadata_json),
                created_at=r.created_at.isoformat(),
            )
            for r in rows
        ],
    )


@router.post("/memory/long-term", response_model=LongTermMemoryItem)
async def upsert_long_term_memory_route(
    payload: LongTermMemoryUpsertRequest,
    http_request: Request,
    db: Session = Depends(get_db),
) -> LongTermMemoryItem:
    user = _get_current_user_required(http_request, db)
    key = (payload.memory_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="memory_key requis.")
    row = upsert_long_term_memory(
        db,
        user_id=str(user.id),
        namespace=(payload.namespace or "global").strip() or "global",
        memory_key=key,
        memory_value=str(payload.memory_value or ""),
        score=float(payload.score or 1.0),
        metadata=dict(payload.metadata or {}),
    )
    return LongTermMemoryItem(
        id=int(row.id),
        namespace=str(row.namespace),
        memory_key=str(row.memory_key),
        memory_value=str(row.memory_value),
        score=float(row.score),
        metadata=_safe_json_load(row.metadata_json),
        updated_at=row.updated_at.isoformat(),
    )


@router.get("/memory/long-term", response_model=LongTermMemoryListResponse)
async def get_long_term_memory(
    http_request: Request,
    namespace: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> LongTermMemoryListResponse:
    user = _get_current_user_required(http_request, db)
    rows = list_long_term_memories(
        db,
        user_id=str(user.id),
        namespace=namespace.strip(),
        limit=limit,
    )
    return LongTermMemoryListResponse(
        items=[
            LongTermMemoryItem(
                id=int(r.id),
                namespace=str(r.namespace),
                memory_key=str(r.memory_key),
                memory_value=str(r.memory_value),
                score=float(r.score),
                metadata=_safe_json_load(r.metadata_json),
                updated_at=r.updated_at.isoformat(),
            )
            for r in rows
        ]
    )


@router.get("/erp/admin/config", response_model=ERPConfigResponse)
async def erp_admin_get_config(http_request: Request, db: Session = Depends(get_db)) -> ERPConfigResponse:
    _require_admin(http_request, db)
    row = db.get(ERPConfig, 1)
    if not row:
        row = ERPConfig(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return ERPConfigResponse(
        db_type=str(row.db_type),
        host=str(row.host),
        port=int(row.port),
        db_name=str(row.db_name),
        username=str(row.username),
        password_masked=_mask_password(str(row.password or "")),
        enabled=bool(row.enabled),
        updated_at=row.updated_at.isoformat(),
        updated_by_user_id=str(row.updated_by_user_id or ""),
    )


@router.post("/erp/admin/config", response_model=ERPConfigResponse)
async def erp_admin_upsert_config(
    payload: ERPConfigUpsertRequest,
    http_request: Request,
    db: Session = Depends(get_db),
) -> ERPConfigResponse:
    admin = _require_admin(http_request, db)
    row = db.get(ERPConfig, 1) or ERPConfig(id=1)
    row.db_type = str(payload.db_type or "postgresql").strip().lower()
    row.host = str(payload.host or "").strip()
    row.port = int(payload.port or 0)
    row.db_name = str(payload.db_name or "").strip()
    row.username = str(payload.username or "").strip()
    if str(payload.password or "").strip():
        row.password = str(payload.password)
    row.enabled = bool(payload.enabled)
    row.updated_by_user_id = str(admin.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return ERPConfigResponse(
        db_type=str(row.db_type),
        host=str(row.host),
        port=int(row.port),
        db_name=str(row.db_name),
        username=str(row.username),
        password_masked=_mask_password(str(row.password or "")),
        enabled=bool(row.enabled),
        updated_at=row.updated_at.isoformat(),
        updated_by_user_id=str(row.updated_by_user_id or ""),
    )


@router.post("/erp/admin/test-connection", response_model=ERPConnectionTestResponse)
async def erp_admin_test_connection(http_request: Request, db: Session = Depends(get_db)) -> ERPConnectionTestResponse:
    _require_admin(http_request, db)
    row = db.get(ERPConfig, 1)
    if not row:
        raise HTTPException(status_code=404, detail="Config ERP absente.")
    if not row.enabled:
        raise HTTPException(status_code=400, detail="Config ERP désactivée.")
    url = _erp_db_url(row.db_type, row.host, row.port, row.db_name, row.username, row.password)
    settings = get_settings()
    timeout = int(settings.erp_sql_connect_timeout_seconds or 5)
    try:
        engine = create_engine(url, future=True, pool_pre_ping=True, connect_args={}, pool_timeout=timeout)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
    except Exception as exc:  # noqa: BLE001
        return ERPConnectionTestResponse(ok=False, detail=f"Connexion ERP échouée: {exc}")
    return ERPConnectionTestResponse(ok=True, detail="Connexion ERP SQL OK.")


@router.get("/admin/monitoring/overview", response_model=AdminMonitoringOverviewResponse)
async def admin_monitoring_overview(http_request: Request, db: Session = Depends(get_db)) -> AdminMonitoringOverviewResponse:
    _require_admin(http_request, db)
    now = datetime.now(timezone.utc)
    uptime = int((now - APP_START_AT).total_seconds())
    users_count = int(db.query(User).count())
    short_count = int(db.query(ShortTermMemory).count())
    long_count = int(db.query(LongTermMemory).count())
    with JOBS_LOCK:
        jobs = list(JOBS.values())
    status_counts: dict[str, int] = {"running": 0, "done": 0, "error": 0}
    for j in jobs:
        status = str(j.get("status") or "").lower()
        if status in status_counts:
            status_counts[status] += 1

    ask_outputs = (
        db.query(LongTermMemory)
        .filter(LongTermMemory.namespace == "ask_agent_outputs")
        .order_by(LongTermMemory.updated_at.desc())
        .limit(30)
        .all()
    )
    request_type_counts: dict[str, int] = {}
    recent_executions: list[dict] = []
    subagent_traces: list[dict] = []
    for row in ask_outputs:
        meta = _safe_json_load(str(row.metadata_json or "{}"))
        route = str(meta.get("route_intent") or "unknown").strip().lower() or "unknown"
        request_type_counts[route] = int(request_type_counts.get(route, 0)) + 1
        recent_executions.append(
            {
                "updated_at": row.updated_at.isoformat(),
                "memory_key": str(row.memory_key),
                "route_intent": route,
                "article_id": str(meta.get("article_id") or ""),
                "session_id": str(meta.get("session_id") or ""),
                "response_excerpt": str(row.memory_value or "")[:220],
            }
        )
        subagent_traces.append(
            {
                "trace_time": row.updated_at.isoformat(),
                "subagent": route,
                "status": "completed",
                "details": f"route={route} article={str(meta.get('article_id') or '')}",
            }
        )

    load1 = load5 = load15 = 0.0
    try:
        l1, l5, l15 = os.getloadavg()
        load1, load5, load15 = float(l1), float(l5), float(l15)
    except Exception:  # noqa: BLE001
        pass

    mem_total_mb = 0
    mem_available_mb = 0
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            meminfo = f.read()
        parsed: dict[str, int] = {}
        for line in meminfo.splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            num = "".join(ch for ch in v if ch.isdigit())
            parsed[k.strip()] = int(num or 0)
        mem_total_mb = int(parsed.get("MemTotal", 0) / 1024)
        mem_available_mb = int(parsed.get("MemAvailable", 0) / 1024)
    except Exception:  # noqa: BLE001
        pass

    instance_performance = {
        "load_avg_1m": round(load1, 3),
        "load_avg_5m": round(load5, 3),
        "load_avg_15m": round(load15, 3),
        "mem_total_mb": mem_total_mb,
        "mem_available_mb": mem_available_mb,
        "uptime_seconds": uptime,
    }
    return AdminMonitoringOverviewResponse(
        app_uptime_seconds=uptime,
        users_count=users_count,
        short_memories_count=short_count,
        long_memories_count=long_count,
        classification_jobs_total=len(jobs),
        classification_jobs_running=status_counts["running"],
        classification_jobs_done=status_counts["done"],
        classification_jobs_error=status_counts["error"],
        request_type_counts=request_type_counts,
        recent_executions=recent_executions[:12],
        instance_performance=instance_performance,
        subagent_traces=subagent_traces[:12],
    )


@router.post("/admin/self-learning/retrain", response_model=SelfLearningJobResponse)
async def admin_self_learning_retrain(
    payload: SelfLearningRetrainRequest,
    http_request: Request,
    db: Session = Depends(get_db),
) -> SelfLearningJobResponse:
    _require_admin(http_request, db)
    settings = get_settings()
    base_path = str(settings.self_learning_db_long_memory_path or "/tmp/db_long_memory").strip()
    if not base_path:
        raise HTTPException(status_code=400, detail="Path db_long_memory non configuré.")

    job_id = create_retrain_job(target_model=str(payload.target_model or "mistral:7b-instruct"))

    def _runner() -> None:
        from src.core.database import SessionLocal

        local_db = SessionLocal()
        try:
            run_retrain_job(
                job_id,
                db=local_db,
                base_path=base_path,
                max_memories=int(payload.max_memories or 500),
            )
        except Exception as exc:  # noqa: BLE001
            from src.services.self_learning import _set_job

            _set_job(job_id, status="error", detail=f"Erreur self-learning: {exc}")
        finally:
            local_db.close()

    threading.Thread(target=_runner, daemon=True).start()
    out = get_self_learning_job(job_id) or {}
    return SelfLearningJobResponse(**out)


@router.get("/admin/self-learning/job/{job_id}", response_model=SelfLearningJobResponse)
async def admin_self_learning_job(job_id: str, http_request: Request, db: Session = Depends(get_db)) -> SelfLearningJobResponse:
    _require_admin(http_request, db)
    out = get_self_learning_job(job_id)
    if not out:
        raise HTTPException(status_code=404, detail="Job self-learning introuvable.")
    return SelfLearningJobResponse(**out)


@router.post("/admin/warehouse/upload", response_model=WarehouseIngestionJobResponse)
async def admin_warehouse_upload(
    http_request: Request,
    file: UploadFile = File(...),
    categorie_default: str = Form(default=""),
    db: Session = Depends(get_db),
) -> WarehouseIngestionJobResponse:
    _require_admin(http_request, db)
    filename = file.filename or "warehouse_extract"
    if not filename.lower().endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Format non supporté. Utilisez CSV/XLSX.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Fichier vide.")
    try:
        rows = parse_uploaded_file(content, filename=filename, categorie_default=categorie_default)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Erreur lecture fichier: {exc}") from exc
    if not rows:
        raise HTTPException(status_code=400, detail="Aucune ligne exploitable.")

    job_id = create_ingest_job(filename=filename, total_rows=len(rows))

    async def _worker() -> None:
        from src.core.database import SessionLocal

        local_db = SessionLocal()
        try:
            await run_ingest_job(job_id, filename=filename, rows=rows, db=local_db)
        except Exception as exc:  # noqa: BLE001
            from src.services.warehouse_ingestion import _update

            _update(job_id, status="error", error=str(exc))
        finally:
            local_db.close()

    asyncio.create_task(_worker())
    payload = get_ingest_job(job_id) or {}
    return WarehouseIngestionJobResponse(**payload)


@router.get("/admin/warehouse/upload/{job_id}", response_model=WarehouseIngestionJobResponse)
async def admin_warehouse_upload_status(job_id: str, http_request: Request, db: Session = Depends(get_db)) -> WarehouseIngestionJobResponse:
    _require_admin(http_request, db)
    payload = get_ingest_job(job_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Job warehouse introuvable.")
    return WarehouseIngestionJobResponse(**payload)


@router.post("/admin/warehouse/upload/{job_id}/cancel", response_model=WarehouseIngestionJobResponse)
async def admin_warehouse_upload_cancel(job_id: str, http_request: Request, db: Session = Depends(get_db)) -> WarehouseIngestionJobResponse:
    _require_admin(http_request, db)
    ok = cancel_ingest_job(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Job warehouse introuvable.")
    payload = get_ingest_job(job_id) or {}
    return WarehouseIngestionJobResponse(**payload)


@router.get("/admin/warehouse/summary", response_model=WarehouseDatabaseSummaryResponse)
async def admin_warehouse_summary(http_request: Request, db: Session = Depends(get_db)) -> WarehouseDatabaseSummaryResponse:
    _require_admin(http_request, db)
    total = int(db.query(WarehouseInventoryRecord).count())
    latest = db.query(WarehouseInventoryRecord).order_by(WarehouseInventoryRecord.created_at.desc()).first()
    latest_snapshot = db.query(WarehouseStockSnapshot).order_by(WarehouseStockSnapshot.created_at.desc()).first()
    total_stock_kg = float(
        sum(float(r[0] or 0.0) for r in db.query(WarehouseStockSnapshot.stock_quantity_kg).all())
    )
    labels: dict[str, int] = {}
    qty_by_label_kg: dict[str, float] = {}
    if total:
        rows = db.query(WarehouseInventoryRecord.final_label).all()
        for r in rows:
            key = str(r[0] or "UNKNOWN")
            labels[key] = int(labels.get(key, 0)) + 1
    qty_rows = db.query(WarehouseStockSnapshot.final_label, WarehouseStockSnapshot.stock_quantity_kg).all()
    for lbl, qty in qty_rows:
        key = str(lbl or "UNKNOWN")
        qty_by_label_kg[key] = float(qty_by_label_kg.get(key, 0.0)) + float(qty or 0.0)
    ingredient_totals: dict[tuple[str, str], float] = {}
    ing_rows = db.query(
        WarehouseStockSnapshot.description,
        WarehouseStockSnapshot.final_label,
        WarehouseStockSnapshot.stock_quantity_kg,
    ).all()
    for desc, lbl, qty in ing_rows:
        ingredient = str(desc or "").strip() or "N/A"
        # Normalise les libellés de type "[ARTICLE] ingredient" pour sommer par ingrédient réel.
        ingredient = re.sub(r"^\s*\[[^\]]+\]\s*", "", ingredient).strip(" -:;") or "N/A"
        label = str(lbl or "UNKNOWN").upper()
        key = (ingredient, label)
        ingredient_totals[key] = float(ingredient_totals.get(key, 0.0)) + float(qty or 0.0)
    top_ingredients_kg = [
        {"ingredient": ing, "label": lbl, "qty_kg": round(total, 6)}
        for (ing, lbl), total in sorted(ingredient_totals.items(), key=lambda kv: float(kv[1]), reverse=True)[:20]
    ]
    return WarehouseDatabaseSummaryResponse(
        total_records=total,
        latest_batch_id=str(latest.batch_id) if latest else "",
        latest_source_file=str(latest.source_file) if latest else "",
        latest_snapshot_date=str(latest_snapshot.snapshot_date) if latest_snapshot else "",
        total_stock_kg=round(total_stock_kg, 3),
        labels=labels,
        qty_by_label_kg={k: round(v, 6) for k, v in qty_by_label_kg.items()},
        top_ingredients_kg=top_ingredients_kg,
    )


@router.get("/admin/warehouse/export.csv")
async def admin_warehouse_export_csv(http_request: Request, db: Session = Depends(get_db)) -> StreamingResponse:
    _require_admin(http_request, db)
    rows = db.query(WarehouseStockSnapshot).order_by(WarehouseStockSnapshot.id.asc()).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "batch_id",
            "source_file",
            "id_article_erp",
            "description",
            "categorie",
            "snapshot_date",
            "stock_quantity_kg",
            "stage1_mp_pdr",
            "stage2_mp_chimie",
            "final_label",
            "created_at",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r.id,
                r.batch_id,
                r.source_file,
                r.id_article_erp,
                r.description,
                r.categorie,
                r.snapshot_date,
                round(float(r.stock_quantity_kg or 0.0), 6),
                r.stage1_mp_pdr,
                r.stage2_mp_chimie,
                r.final_label,
                r.created_at.isoformat() if r.created_at else "",
            ]
        )
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=warehouse_stock_classified_export.csv"},
    )
