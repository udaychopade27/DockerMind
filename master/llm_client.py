"""
llm_client.py — Multi-provider LLM client for DockerMind
---------------------------------------------------------
Provider selection via LLM_PROVIDER dynamic setting / env var:
  "local"      → Ollama only
  "online"     → Gemini first → OpenRouter fallback on quota/error
  "gemini"     → Gemini only
  "openrouter" → OpenRouter only

Supports Zero-Downtime Hot Reloading: API keys and models are dynamically
fetched from SQLite/memory without requiring container restarts.
"""

import httpx
import json
import config
from config import (
    get_llm_provider,
    get_ollama_base_url,
    get_ollama_model,
    get_gemini_api_key,
    get_gemini_model,
    get_openrouter_api_key,
    get_openrouter_model,
)


# ── System prompt (shared across all providers) ────────────────────────────────

SYSTEM_PROMPT = """
You are DockerMind AI, an expert DevOps and Site Reliability Engineering (SRE) assistant.

Guidelines:
- Provide clear, thorough, and complete explanations with actionable Docker / Linux CLI commands in fenced code blocks.
- If diagnosing an incident or error, identify the root cause, provide exact fix commands, and describe how to verify the container's health.
- If answering general DevOps, architecture, or troubleshooting questions, provide comprehensive step-by-step guidance.
- Always provide complete answers without cutting off prematurely.
"""

HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=30.0)

# Errors that indicate quota exhausted on Gemini — trigger OpenRouter fallback
_GEMINI_QUOTA_ERRORS = (
    "429",
    "quota",
    "resource_exhausted",
    "RESOURCE_EXHAUSTED",
    "rateLimitExceeded",
)


# ── Ollama helpers (kept for /health endpoint + startup) ──────────────────────

async def ensure_model_loaded() -> bool:
    """Warm up Ollama model during startup. No-op when using cloud providers."""
    provider = get_llm_provider()
    if provider != "local":
        print(f"[LLM] Provider={provider} — skipping Ollama model preload")
        return True
    model = get_ollama_model()
    base_url = get_ollama_base_url()
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.post(
                f"{base_url}/api/generate",
                json={"model": model, "prompt": "ready", "stream": False},
            )
            resp.raise_for_status()
            print(f"[LLM] Ollama model loaded: {model}")
            return True
    except Exception as e:
        print(f"[LLM] Ollama model preload failed: {e}")
        return False


async def check_ollama_health() -> bool:
    """
    Health check:
    - local  → ping Ollama
    - online/gemini/openrouter → return True if API key is configured
    """
    provider = get_llm_provider()
    gemini_key = get_gemini_api_key()
    openrouter_key = get_openrouter_api_key()
    base_url = get_ollama_base_url()
    model = get_ollama_model()

    if provider == "local":
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{base_url}/api/tags")
                r.raise_for_status()
                models = r.json().get("models", [])
                available = [m["name"] for m in models]
                ok = any(model in m for m in available)
                if not ok:
                    print(f"[LLM] Ollama missing model: {model}")
                return ok
        except Exception as e:
            print(f"[LLM] Ollama health failed: {e}")
            return False

    # Cloud providers: healthy if at least one key is configured
    if provider in ("online", "gemini") and gemini_key:
        return True
    if provider in ("online", "openrouter") and openrouter_key:
        return True
    if provider == "gemini" and not gemini_key:
        print("[LLM] GEMINI_API_KEY not set!")
        return False
    if provider == "openrouter" and not openrouter_key:
        print("[LLM] OPENROUTER_API_KEY not set!")
        return False
    return False


# ── Provider implementations ──────────────────────────────────────────────────

async def _chat_ollama(user_message: str, context: str = "") -> str:
    """Call local Ollama instance."""
    base_url = get_ollama_base_url()
    model = get_ollama_model()

    if not await check_ollama_health():
        raise RuntimeError(f"Ollama unavailable at {base_url} (model={model})")

    content = (
        f"Context:\n{context}\n\nQuestion:\n{user_message}"
        if context else user_message
    )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "system": SYSTEM_PROMPT,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 2048},
    }

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.post(f"{base_url}/api/chat", json=payload)
            r.raise_for_status()
            return r.json().get("message", {}).get("content", "No response")
    except httpx.ConnectError:
        raise RuntimeError(f"Cannot connect to Ollama at {base_url}")
    except httpx.TimeoutException:
        raise RuntimeError("Ollama timeout")
    except Exception as e:
        raise RuntimeError(f"Ollama error: {e}")


async def _chat_gemini(user_message: str, context: str = "") -> str:
    """Call Google Gemini via REST API with high token limit and reasoning budget."""
    gemini_key = get_gemini_api_key()
    gemini_model = get_gemini_model()

    if not gemini_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    if context:
        content = f"Context:\n{context}\n\nQuestion:\n{user_message}"
    else:
        content = user_message

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{gemini_model}:generateContent?key={gemini_key}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": content}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 8192,
            "thinkingConfig": {
                "thinkingBudget": 512
            }
        },
    }

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        r = await client.post(url, json=payload)
        # Surface quota / rate-limit errors with the status code in message
        if r.status_code != 200:
            raise RuntimeError(f"{r.status_code} {r.text[:200]}")
        data = r.json()
        try:
            candidate = data["candidates"][0]
            parts = candidate.get("content", {}).get("parts", [])
            # Filter out internal reasoning/thought parts to prevent truncation
            text_parts = [p["text"] for p in parts if not p.get("thought") and "text" in p]
            if text_parts:
                return "\n".join(text_parts).strip()
            for p in parts:
                if "text" in p:
                    return p["text"].strip()
            return "No response text received from Gemini."
        except (KeyError, IndexError):
            raise RuntimeError(f"Unexpected Gemini response: {data}")


OPENROUTER_CANDIDATE_MODELS = [
    "liquid/lfm-2.5-2.6b:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3.5-lightning:free",
    "cohere/north-mini-code:free",
    "dots-studio/dots-3-note-preview:free",
]

async def _chat_openrouter(user_message: str, context: str = "") -> str:
    """Call OpenRouter with multi-model auto-fallback across verified free models."""
    openrouter_key = get_openrouter_api_key()
    openrouter_model = get_openrouter_model()

    if not openrouter_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    content = (
        f"Context:\n{context}\n\nQuestion:\n{user_message}"
        if context else user_message
    )

    # Candidate models: user-specified model first, followed by active free models
    models_to_try = [openrouter_model]
    for m in OPENROUTER_CANDIDATE_MODELS:
        if m not in models_to_try:
            models_to_try.append(m)

    headers = {
        "Authorization": f"Bearer {openrouter_key}",
        "HTTP-Referer":  "https://github.com/dockermind",
        "X-Title":       "DockerMind",
        "Content-Type":  "application/json",
    }

    last_error = ""
    for model in models_to_try:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": content},
            ],
            "temperature": 0.2,
            "max_tokens": 4096,
        }

        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                r = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )

                if r.status_code == 200:
                    data = r.json()
                    choices = data.get("choices", [])
                    if choices:
                        print(f"[LLM] OpenRouter model '{model}' responded successfully")
                        return choices[0]["message"]["content"].strip()
                else:
                    last_error = f"{r.status_code}: {r.text[:200]}"
                    print(f"[LLM] OpenRouter model '{model}' failed ({last_error}) — trying next candidate...")
        except Exception as e:
            last_error = str(e)
            print(f"[LLM] OpenRouter model '{model}' exception: {e} — trying next candidate...")

    raise RuntimeError(f"All OpenRouter models failed. Last error: {last_error}")


def _is_quota_error(err_str: str) -> bool:
    return any(q in err_str for q in _GEMINI_QUOTA_ERRORS)


# ── Public API ────────────────────────────────────────────────────────────────

async def chat(user_message: str, context: str = "") -> str:
    """
    Route to the right provider:
      local      → Ollama
      gemini     → Gemini only
      openrouter → OpenRouter only
      online     → Gemini → OpenRouter fallback
    """
    provider = get_llm_provider()
    gemini_key = get_gemini_api_key()
    openrouter_key = get_openrouter_api_key()

    if provider == "local":
        return await _chat_ollama(user_message, context)

    if provider == "gemini":
        return await _chat_gemini(user_message, context)

    if provider == "openrouter":
        return await _chat_openrouter(user_message, context)

    if provider == "online":
        # Try Gemini first
        if gemini_key:
            try:
                result = await _chat_gemini(user_message, context)
                print("[LLM] Gemini responded OK")
                return result
            except RuntimeError as e:
                err = str(e)
                if _is_quota_error(err):
                    print(f"[LLM] Gemini quota/rate-limit hit — falling back to OpenRouter. ({err[:80]})")
                else:
                    print(f"[LLM] Gemini error — falling back to OpenRouter. ({err[:80]})")
                # Fall through to OpenRouter
        else:
            print("[LLM] GEMINI_API_KEY not set — skipping Gemini, using OpenRouter")

        # Fallback: OpenRouter
        if openrouter_key:
            print("[LLM] Fallback to OpenRouter initiated...")
            try:
                result = await _chat_openrouter(user_message, context)
                print("[LLM] OpenRouter responded OK")
                return result
            except Exception as ex:
                print(f"[LLM] OpenRouter fallback failed: {ex}")
                return (
                    "DockerMind AI Assistant: Primary LLM (Gemini) quota limit reached, and OpenRouter free endpoint is temporarily throttled upstream. "
                    "Cluster health monitoring, circuit breaker backoffs, and auto-remediations are fully active."
                )

        raise RuntimeError(
            "LLM_PROVIDER=online but neither GEMINI_API_KEY nor OPENROUTER_API_KEY is set"
        )

    raise RuntimeError(f"Unknown LLM_PROVIDER: {provider!r} — use local/online/gemini/openrouter")


async def analyze_logs(container_name: str, logs: str) -> dict:
    """
    Ask the active LLM to analyze container logs and return structured JSON.
    Signature unchanged — called by heal_engine.py.
    """
    prompt = f"""
Analyze logs.

Container:
{container_name}

Return JSON only.

{{
"severity":"ok|warn|error|critical",
"root_cause":"",
"fix":"",
"auto_heal":true,
"heal_action":"restart|exec:<cmd>|none"
}}

Logs:
{logs[-3000:]}
"""
    try:
        raw = await chat(prompt)
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        provider = get_llm_provider()
        return {
            "severity":   "warn",
            "root_cause": str(e),
            "fix":        f"Check LLM provider ({provider})",
            "auto_heal":  False,
            "heal_action": "none",
        }


# ── Dynamic module-level attribute lookup for backward compatibility ──────────
def __getattr__(name: str):
    if name == 'LLM_PROVIDER':
        return get_llm_provider()
    if name == 'GEMINI_MODEL':
        return get_gemini_model()
    if name == 'OPENROUTER_MODEL':
        return get_openrouter_model()
    if name == 'LLM_MODEL':
        return get_ollama_model()
    if name == 'GEMINI_API_KEY':
        return get_gemini_api_key()
    if name == 'OPENROUTER_API_KEY':
        return get_openrouter_api_key()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
