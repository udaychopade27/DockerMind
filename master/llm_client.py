"""
llm_client.py — Multi-provider LLM client for DockerMind
---------------------------------------------------------
Provider selection via LLM_PROVIDER env var:
  "local"      → Ollama only
  "online"     → Gemini first → OpenRouter fallback on quota/error
  "gemini"     → Gemini only
  "openrouter" → OpenRouter only

Public API (unchanged):
  chat(user_message, context="") -> str
  analyze_logs(container_name, logs) -> dict
  check_ollama_health() -> bool         # kept for /health endpoint compat
  ensure_model_loaded() -> bool         # kept for startup compat
"""

import httpx
import json
from config import (
    LLM_PROVIDER,
    OLLAMA_BASE_URL, LLM_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL,
    OPENROUTER_API_KEY, OPENROUTER_MODEL,
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
    if LLM_PROVIDER != "local":
        print(f"[LLM] Provider={LLM_PROVIDER} — skipping Ollama model preload")
        return True
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={"model": LLM_MODEL, "prompt": "ready", "stream": False},
            )
            resp.raise_for_status()
            print(f"[LLM] Ollama model loaded: {LLM_MODEL}")
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
    if LLM_PROVIDER == "local":
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
                r.raise_for_status()
                models = r.json().get("models", [])
                available = [m["name"] for m in models]
                ok = any(LLM_MODEL in m for m in available)
                if not ok:
                    print(f"[LLM] Ollama missing model: {LLM_MODEL}")
                return ok
        except Exception as e:
            print(f"[LLM] Ollama health failed: {e}")
            return False

    # Cloud providers: healthy if at least one key is configured
    if LLM_PROVIDER in ("online", "gemini") and GEMINI_API_KEY:
        return True
    if LLM_PROVIDER in ("online", "openrouter") and OPENROUTER_API_KEY:
        return True
    if LLM_PROVIDER == "gemini" and not GEMINI_API_KEY:
        print("[LLM] GEMINI_API_KEY not set!")
        return False
    if LLM_PROVIDER == "openrouter" and not OPENROUTER_API_KEY:
        print("[LLM] OPENROUTER_API_KEY not set!")
        return False
    return False


# ── Provider implementations ──────────────────────────────────────────────────

async def _chat_ollama(user_message: str, context: str = "") -> str:
    """Call local Ollama instance."""
    if not await check_ollama_health():
        raise RuntimeError(f"Ollama unavailable (model={LLM_MODEL})")

    content = (
        f"Context:\n{context}\n\nQuestion:\n{user_message}"
        if context else user_message
    )
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": content}],
        "system": SYSTEM_PROMPT,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 2048},
    }

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
            r.raise_for_status()
            return r.json().get("message", {}).get("content", "No response")
    except httpx.ConnectError:
        raise RuntimeError(f"Cannot connect to Ollama at {OLLAMA_BASE_URL}")
    except httpx.TimeoutException:
        raise RuntimeError("Ollama timeout")
    except Exception as e:
        raise RuntimeError(f"Ollama error: {e}")


async def _chat_gemini(user_message: str, context: str = "") -> str:
    """Call Google Gemini via REST API with high token limit and reasoning budget."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")

    if context:
        content = f"Context:\n{context}\n\nQuestion:\n{user_message}"
    else:
        content = user_message

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
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
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    content = (
        f"Context:\n{context}\n\nQuestion:\n{user_message}"
        if context else user_message
    )

    # Candidate models: user-specified model first, followed by active free models
    models_to_try = [OPENROUTER_MODEL]
    for m in OPENROUTER_CANDIDATE_MODELS:
        if m not in models_to_try:
            models_to_try.append(m)

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer":  "https://github.com/dockermind",
        "X-Title":       "DockerMind",
        "Content-Type":  "application/json",
    }

    last_error = None
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        for model in models_to_try:
            print(f"[LLM] Dispatching prompt to OpenRouter (model: {model})...")
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
                r = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    json=payload,
                    headers=headers,
                )
                if r.status_code == 200:
                    data = r.json()
                    ans = data["choices"][0]["message"]["content"]
                    print(f"[LLM] OpenRouter model '{model}' responded successfully (HTTP 200)")
                    return ans
                else:
                    err_snippet = r.text[:120].replace('\n', ' ')
                    print(f"[LLM] OpenRouter model '{model}' returned HTTP {r.status_code}: {err_snippet}")
                    last_error = f"HTTP {r.status_code}: {err_snippet}"
            except Exception as ex:
                print(f"[LLM] OpenRouter model '{model}' request failed: {ex}")
                last_error = str(ex)

    raise RuntimeError(f"All OpenRouter candidate models failed. Last error: {last_error}")


# ── Public API ────────────────────────────────────────────────────────────────

def _is_quota_error(error_msg: str) -> bool:
    """Check if a Gemini error is quota / rate-limit (triggers OpenRouter fallback)."""
    low = error_msg.lower()
    return any(kw.lower() in low for kw in _GEMINI_QUOTA_ERRORS)


async def chat(user_message: str, context: str = "") -> str:
    """
    Route to the right provider:
      local      → Ollama
      gemini     → Gemini only
      openrouter → OpenRouter only
      online     → Gemini → OpenRouter fallback
    """
    provider = LLM_PROVIDER.lower()

    if provider == "local":
        return await _chat_ollama(user_message, context)

    if provider == "gemini":
        return await _chat_gemini(user_message, context)

    if provider == "openrouter":
        return await _chat_openrouter(user_message, context)

    if provider == "online":
        # Try Gemini first
        if GEMINI_API_KEY:
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
        if OPENROUTER_API_KEY:
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

    raise RuntimeError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER!r} — use local/online/gemini/openrouter")


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
        provider = LLM_PROVIDER
        return {
            "severity":   "warn",
            "root_cause": str(e),
            "fix":        f"Check LLM provider ({provider})",
            "auto_heal":  False,
            "heal_action": "none",
        }