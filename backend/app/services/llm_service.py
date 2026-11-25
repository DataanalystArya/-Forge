"""
Unified LLM Service — Phase 4+.

Supports OpenAI (and any OpenAI-compatible endpoint via OPENAI_BASE_URL,
such as Ollama, vLLM, or LM Studio) using langchain-openai.

Never fabricates or fakes LLM responses. When OPENAI_API_KEY (and
OPENAI_BASE_URL) are not configured, returns available=False clearly so
callers can run deterministic static/AST/RAG analysis and report the exact
LLM limitation transparently.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("forge.llm")

# Approximate USD pricing per 1M tokens for common models
_MODEL_PRICING_PER_1M = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
}


@dataclass
class LLMResult:
    available: bool
    content: str
    model_name: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    latency_ms: int = 0
    error: Optional[str] = None


def estimate_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    in_price, out_price = _MODEL_PRICING_PER_1M.get(model_name, (0.15, 0.60))
    return round((prompt_tokens * in_price + completion_tokens * out_price) / 1_000_000, 6)


class LLMService:
    """Wrapper around ChatOpenAI with token, cost, and latency tracking."""

    @staticmethod
    def is_configured() -> bool:
        return bool(settings.OPENAI_API_KEY.strip() or settings.OPENAI_BASE_URL.strip())

    @staticmethod
    def get_model_name() -> str:
        return settings.OPENAI_MODEL or "gpt-4o-mini"

    @classmethod
    def invoke(
        cls,
        system_prompt: str,
        user_prompt: str,
        session_id: Optional[str] = None,
        agent_name: str = "unknown",
        temperature: float = 0.1,
    ) -> LLMResult:
        model_name = cls.get_model_name()
        if not cls.is_configured():
            msg = "OPENAI_API_KEY is not configured; LLM synthesis skipped."
            cls._log_usage(
                session_id=session_id,
                agent_name=agent_name,
                model_name=model_name,
                status="UNAVAILABLE",
                error_message=msg,
            )
            return LLMResult(
                available=False,
                content="",
                model_name=model_name,
                error=msg,
            )

        t0 = time.monotonic()
        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import SystemMessage, HumanMessage

            kwargs = {
                "model": model_name,
                "temperature": temperature,
                "api_key": settings.OPENAI_API_KEY or "local-key",
                "timeout": 45,
                "max_retries": 1,
            }
            if settings.OPENAI_BASE_URL.strip():
                kwargs["base_url"] = settings.OPENAI_BASE_URL.strip()

            llm = ChatOpenAI(**kwargs)
            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])
            latency_ms = int((time.monotonic() - t0) * 1000)

            usage = getattr(response, "usage_metadata", None) or {}
            prompt_tokens = int(usage.get("input_tokens", 0) or 0)
            completion_tokens = int(usage.get("output_tokens", 0) or 0)
            total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens) or 0)
            cost = estimate_cost(model_name, prompt_tokens, completion_tokens)

            cls._log_usage(
                session_id=session_id,
                agent_name=agent_name,
                model_name=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                estimated_cost_usd=cost,
                latency_ms=latency_ms,
                status="SUCCESS",
            )
            return LLMResult(
                available=True,
                content=str(response.content),
                model_name=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                estimated_cost_usd=cost,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            logger.error(f"LLM invocation failed for {agent_name}: {exc}")
            cls._log_usage(
                session_id=session_id,
                agent_name=agent_name,
                model_name=model_name,
                latency_ms=latency_ms,
                status="ERROR",
                error_message=str(exc),
            )
            return LLMResult(
                available=False,
                content="",
                model_name=model_name,
                latency_ms=latency_ms,
                error=str(exc),
            )

    @staticmethod
    def _log_usage(
        session_id: Optional[str],
        agent_name: str,
        model_name: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        estimated_cost_usd: float = 0.0,
        latency_ms: int = 0,
        status: str = "SUCCESS",
        error_message: Optional[str] = None,
    ) -> None:
        try:
            from app.core.database import SessionLocal
            from app.models.observability import LLMUsageLog

            db = SessionLocal()
            try:
                entry = LLMUsageLog(
                    session_id=session_id,
                    agent_name=agent_name,
                    model_name=model_name,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    estimated_cost_usd=estimated_cost_usd,
                    latency_ms=latency_ms,
                    status=status,
                    error_message=error_message,
                )
                db.add(entry)
                db.commit()
            finally:
                db.close()
        except Exception as exc:
            logger.debug(f"Could not persist LLMUsageLog: {exc}")
