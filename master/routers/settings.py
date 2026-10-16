import time
import httpx
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException

from middleware.auth import get_current_user, require_role
from database import db_set_setting
import config
from config import (
    get_llm_provider,
    get_gemini_api_key,
    get_gemini_model,
    get_openrouter_api_key,
    get_openrouter_model,
    get_ollama_base_url,
    get_ollama_model,
    mask_secret,
    set_config_val,
)
from services.notifier import notifier
import llm_client

router = APIRouter(prefix="/settings", tags=["settings"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class AISettingsUpdate(BaseModel):
    provider: Optional[str] = None
    gemini_api_key: Optional[str] = None
    gemini_model: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    openrouter_model: Optional[str] = None
    ollama_base_url: Optional[str] = None
    ollama_model: Optional[str] = None


class NotificationSettingsUpdate(BaseModel):
    slack_webhook_url: Optional[str] = None
    discord_webhook_url: Optional[str] = None
    generic_webhook_url: Optional[str] = None
    min_severity: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_to: Optional[str] = None
    smtp_tls: Optional[bool] = None


class TestNotificationRequest(BaseModel):
    channel: Optional[str] = "all"  # all | slack | discord | generic | email


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", summary="Get dynamic system settings and integrations (viewer+)")
async def get_all_settings(user: dict = Depends(get_current_user)):
    """Retrieve current AI and notification settings with secrets masked."""
    gemini_key = get_gemini_api_key()
    openrouter_key = get_openrouter_api_key()

    return {
        "ai": {
            "provider": get_llm_provider(),
            "gemini_configured": bool(gemini_key),
            "gemini_model": get_gemini_model(),
            "gemini_key_masked": mask_secret(gemini_key),
            "openrouter_configured": bool(openrouter_key),
            "openrouter_model": get_openrouter_model(),
            "openrouter_key_masked": mask_secret(openrouter_key),
            "ollama_base_url": get_ollama_base_url(),
            "ollama_model": get_ollama_model(),
        },
        "notifications": notifier.get_config(),
    }


@router.put("/ai", summary="Update AI engine provider & credentials (operator+)")
async def update_ai_settings(
    req: AISettingsUpdate,
    user: dict = Depends(require_role("operator")),
):
    """
    Update AI provider, keys, or models.
    Changes take effect in memory immediately with ZERO container restarts.
    """
    # 1. Provider
    if req.provider is not None:
        p = req.provider.strip().lower()
        if p in ("local", "online", "gemini", "openrouter"):
            await db_set_setting("LLM_PROVIDER", p)
            set_config_val("LLM_PROVIDER", p)

    # 2. Gemini
    if req.gemini_api_key is not None:
        key = req.gemini_api_key.strip()
        # Ignore if user sent back masked string
        if not ("*" in key and "..." in key):
            await db_set_setting("GEMINI_API_KEY", key)
            set_config_val("GEMINI_API_KEY", key)

    if req.gemini_model is not None and req.gemini_model.strip():
        await db_set_setting("GEMINI_MODEL", req.gemini_model.strip())
        set_config_val("GEMINI_MODEL", req.gemini_model.strip())

    # 3. OpenRouter
    if req.openrouter_api_key is not None:
        key = req.openrouter_api_key.strip()
        if not ("*" in key and "..." in key):
            await db_set_setting("OPENROUTER_API_KEY", key)
            set_config_val("OPENROUTER_API_KEY", key)

    if req.openrouter_model is not None and req.openrouter_model.strip():
        await db_set_setting("OPENROUTER_MODEL", req.openrouter_model.strip())
        set_config_val("OPENROUTER_MODEL", req.openrouter_model.strip())

    # 4. Ollama
    if req.ollama_base_url is not None and req.ollama_base_url.strip():
        await db_set_setting("OLLAMA_BASE_URL", req.ollama_base_url.strip())
        set_config_val("OLLAMA_BASE_URL", req.ollama_base_url.strip())

    if req.ollama_model is not None and req.ollama_model.strip():
        await db_set_setting("LLM_MODEL", req.ollama_model.strip())
        set_config_val("LLM_MODEL", req.ollama_model.strip())

    gemini_key = get_gemini_api_key()
    openrouter_key = get_openrouter_api_key()

    return {
        "status": "updated",
        "ai": {
            "provider": get_llm_provider(),
            "gemini_configured": bool(gemini_key),
            "gemini_model": get_gemini_model(),
            "gemini_key_masked": mask_secret(gemini_key),
            "openrouter_configured": bool(openrouter_key),
            "openrouter_model": get_openrouter_model(),
            "openrouter_key_masked": mask_secret(openrouter_key),
            "ollama_base_url": get_ollama_base_url(),
            "ollama_model": get_ollama_model(),
        }
    }


@router.post("/ai/test", summary="Test AI provider connection and latency (operator+)")
async def test_ai_connection(user: dict = Depends(require_role("operator"))):
    """Send a lightweight prompt to the active AI provider to verify key and latency."""
    provider = get_llm_provider()
    t0 = time.time()
    try:
        if provider == "gemini":
            gemini_key = get_gemini_api_key()
            if not gemini_key:
                raise RuntimeError("GEMINI_API_KEY is not configured")
            model = get_gemini_model()
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(url, json={
                    "contents": [{"parts": [{"text": "Respond with the word PONG only."}]}]
                })
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:160]}")
                data = r.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                latency_ms = int((time.time() - t0) * 1000)
                return {
                    "status": "ok",
                    "provider": "gemini",
                    "model": model,
                    "latency_ms": latency_ms,
                    "reply": text,
                }

        elif provider == "openrouter":
            openrouter_key = get_openrouter_api_key()
            if not openrouter_key:
                raise RuntimeError("OPENROUTER_API_KEY is not configured")
            model = get_openrouter_model()
            headers = {
                "Authorization": f"Bearer {openrouter_key}",
                "HTTP-Referer": "https://github.com/dockermind",
                "X-Title": "DockerMind",
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "Respond with PONG"}],
                        "max_tokens": 10
                    }
                )
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:160]}")
                data = r.json()
                reply = data["choices"][0]["message"]["content"].strip()
                latency_ms = int((time.time() - t0) * 1000)
                return {
                    "status": "ok",
                    "provider": "openrouter",
                    "model": model,
                    "latency_ms": latency_ms,
                    "reply": reply,
                }

        elif provider == "local":
            base_url = get_ollama_base_url()
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{base_url}/api/tags")
                if r.status_code != 200:
                    raise RuntimeError(f"Ollama returned HTTP {r.status_code}")
                latency_ms = int((time.time() - t0) * 1000)
                models = [m.get("name") for m in r.json().get("models", [])]
                return {
                    "status": "ok",
                    "provider": "local (ollama)",
                    "model": get_ollama_model(),
                    "latency_ms": latency_ms,
                    "available_models": models,
                }

        elif provider == "online":
            # Test online chat function
            reply = await llm_client.chat("Respond with the word PONG only.")
            latency_ms = int((time.time() - t0) * 1000)
            return {
                "status": "ok",
                "provider": "online",
                "latency_ms": latency_ms,
                "reply": reply[:100],
            }

        else:
            raise RuntimeError(f"Unknown provider '{provider}'")

    except Exception as e:
        latency_ms = int((time.time() - t0) * 1000)
        return {
            "status": "error",
            "provider": provider,
            "latency_ms": latency_ms,
            "error": str(e),
        }


@router.put("/notifications", summary="Update webhook & SMTP notification channels (operator+)")
async def update_notification_settings(
    req: NotificationSettingsUpdate,
    user: dict = Depends(require_role("operator")),
):
    """Update notification channels and save dynamically to SQLite."""
    await notifier.update_config(
        slack_url=req.slack_webhook_url,
        discord_url=req.discord_webhook_url,
        generic_url=req.generic_webhook_url,
        min_severity=req.min_severity,
        smtp_host=req.smtp_host,
        smtp_port=req.smtp_port,
        smtp_user=req.smtp_user,
        smtp_password=req.smtp_password,
        smtp_from=req.smtp_from,
        smtp_to=req.smtp_to,
        smtp_tls=req.smtp_tls,
    )
    return {
        "status": "updated",
        "notifications": notifier.get_config(),
    }


@router.post("/notifications/test", summary="Send test alert to channels (operator+)")
async def test_notifications(
    req: TestNotificationRequest = TestNotificationRequest(),
    user: dict = Depends(require_role("operator")),
):
    """Dispatch a test notification to Slack, Discord, Generic Webhook, and/or Email."""
    results = await notifier.send_test_notification(channel=req.channel or "all")
    return {
        "status": "dispatched",
        "channel": req.channel or "all",
        "results": results,
    }
