"""Platform & User Settings API — LLM Keys, Model Config, Infrastructure Status."""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.core.encryption import decrypt_token, encrypt_token
from app.models.settings import PlatformSetting
from app.models.user import GitHubAccount, User
from app.services.graph_service import GraphService
from app.services.llm_service import LLMService
from app.services.vector_store_service import VectorStoreService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])

_PROVIDER_DEFAULT_BASE_URLS = {
    "openai": "",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": "http://localhost:11434/v1",
    "custom": "",
}


def _mask_secret(raw: str) -> str:
    if not raw:
        return ""
    if len(raw) <= 8:
        return "*" * len(raw)
    return f"{raw[:4]}...{raw[-4:]}"


def _get_setting(db: Session, key: str) -> Optional[str]:
    row = db.query(PlatformSetting).filter(PlatformSetting.key == key).first()
    if not row or row.value is None:
        return None
    if row.is_secret:
        return decrypt_token(row.value)
    return row.value


def _set_setting(db: Session, key: str, value: str, is_secret: bool = False) -> None:
    row = db.query(PlatformSetting).filter(PlatformSetting.key == key).first()
    stored = encrypt_token(value) if (is_secret and value) else value
    if row:
        row.value = stored
        row.is_secret = is_secret
    else:
        row = PlatformSetting(key=key, value=stored, is_secret=is_secret)
        db.add(row)


def load_persisted_settings(db: Session) -> None:
    """Hydrate runtime config from persisted PlatformSetting rows on boot."""
    try:
        api_key = _get_setting(db, "openai_api_key")
        if api_key:
            settings.OPENAI_API_KEY = api_key
        model = _get_setting(db, "llm_model")
        if model:
            settings.OPENAI_MODEL = model
        base_url = _get_setting(db, "openai_base_url")
        if base_url is not None:
            settings.OPENAI_BASE_URL = base_url
    except Exception as exc:
        logger.debug("Could not load persisted settings: %s", exc)


class UpdateSettingsRequest(BaseModel):
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    github_token: Optional[str] = None
    sandbox_timeout: Optional[int] = None
    max_retries: Optional[int] = None


@router.get("")
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    load_persisted_settings(db)

    provider = _get_setting(db, "llm_provider")
    if not provider:
        url = settings.OPENAI_BASE_URL.lower()
        if "generativelanguage.googleapis.com" in url:
            provider = "gemini"
        elif "openrouter.ai" in url:
            provider = "openrouter"
        elif "localhost:11434" in url or "127.0.0.1:11434" in url:
            provider = "ollama"
        elif url:
            provider = "custom"
        else:
            provider = "openai"

    sandbox_timeout = int(_get_setting(db, "sandbox_timeout") or "60")
    max_retries = int(_get_setting(db, "max_retries") or "3")

    # Infrastructure checks
    vs = VectorStoreService.get_instance()
    vs_ok = vs.is_available()
    vs_mode = vs.get_mode() if vs_ok else "unavailable"

    gs = GraphService.get_instance()
    graph_backend = "neo4j" if gs._neo4j_ok else "networkx_disk"

    db_backend = "postgresql" if settings.DATABASE_URL.startswith("postgres") else "sqlite"

    gh_token_set = bool(current_user.github_account and current_user.github_account.access_token_enc)

    return {
        "llm_provider": provider,
        "llm_model": settings.OPENAI_MODEL,
        "openai_base_url": settings.OPENAI_BASE_URL,
        "openai_api_key_set": bool(settings.OPENAI_API_KEY.strip()),
        "openai_api_key_masked": _mask_secret(settings.OPENAI_API_KEY.strip()),
        "llm_configured": LLMService.is_configured(),
        "github_token_set": gh_token_set,
        "github_username": current_user.github_account.username if current_user.github_account else None,
        "sandbox_timeout": sandbox_timeout,
        "max_retries": max_retries,
        "infrastructure": {
            "database": {"status": "connected", "backend": db_backend},
            "qdrant": {"status": "connected" if vs_ok else "error", "mode": vs_mode},
            "graph": {"status": "connected", "backend": graph_backend},
        },
    }


@router.put("")
def update_settings(
    req: UpdateSettingsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if req.llm_provider is not None:
        _set_setting(db, "llm_provider", req.llm_provider.strip())
        if req.openai_base_url is None and req.llm_provider in _PROVIDER_DEFAULT_BASE_URLS:
            default_url = _PROVIDER_DEFAULT_BASE_URLS[req.llm_provider]
            _set_setting(db, "openai_base_url", default_url)
            settings.OPENAI_BASE_URL = default_url

    if req.llm_model is not None and req.llm_model.strip():
        _set_setting(db, "llm_model", req.llm_model.strip())
        settings.OPENAI_MODEL = req.llm_model.strip()

    if req.openai_base_url is not None:
        clean_url = req.openai_base_url.strip()
        _set_setting(db, "openai_base_url", clean_url)
        settings.OPENAI_BASE_URL = clean_url

    if req.openai_api_key is not None and req.openai_api_key.strip():
        # Ignore masked placeholder if user didn't edit it
        key_val = req.openai_api_key.strip()
        if "..." not in key_val and not set(key_val) == {"*"}:
            _set_setting(db, "openai_api_key", key_val, is_secret=True)
            settings.OPENAI_API_KEY = key_val

    if req.sandbox_timeout is not None:
        _set_setting(db, "sandbox_timeout", str(max(10, min(300, req.sandbox_timeout))))

    if req.max_retries is not None:
        _set_setting(db, "max_retries", str(max(1, min(5, req.max_retries))))

    if req.github_token is not None and req.github_token.strip():
        tok = req.github_token.strip()
        enc = encrypt_token(tok)
        if current_user.github_account:
            current_user.github_account.access_token_enc = enc
        else:
            db.add(GitHubAccount(user_id=current_user.id, access_token_enc=enc))

    db.commit()
    return get_settings(db=db, current_user=current_user)


@router.post("/test-llm")
def test_llm_connection(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Perform a real minimal LLM call to verify credentials and endpoint."""
    load_persisted_settings(db)
    if not LLMService.is_configured():
        return {
            "ok": False,
            "model": LLMService.get_model_name(),
            "error": "No LLM API key or Base URL configured.",
        }

    res = LLMService.invoke(
        system_prompt="You are a connectivity probe.",
        user_prompt="Reply with the single word: OK",
        agent_name="SettingsProbe",
        temperature=0.0,
    )
    return {
        "ok": res.available,
        "model": res.model_name,
        "reply": res.content[:120] if res.available else None,
        "latency_ms": res.latency_ms,
        "total_tokens": res.total_tokens,
        "error": res.error,
    }
