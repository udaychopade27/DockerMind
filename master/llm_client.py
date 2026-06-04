import httpx
import json
from config import OLLAMA_BASE_URL, LLM_MODEL

SYSTEM_PROMPT = """You are DockerMind, an expert DevOps AI assistant embedded in a container orchestration system.
You have direct access to Docker container state, logs, and metrics.
When analyzing logs or errors:
- Be concise and actionable
- Identify root cause first, then suggest fix
- If you can auto-heal, say exactly what command will fix it
- Format: [SEVERITY] Root cause: ... Fix: ... Auto-heal: yes/no
Respond in plain text, no markdown."""


async def chat(user_message: str, context: str = "") -> str:
    """Send a message to the local LLM and return the response."""

    # Fail fast with a clear message if Ollama/model isn't ready
    if not await check_ollama_health():
        raise RuntimeError(
            f"Ollama is not reachable or model '{LLM_MODEL}' is not loaded. "
            "Ensure the model has been pulled and Ollama is running."
        )

    messages = []
    if context:
        messages.append({"role": "user", "content": f"Context:\n{context}\n\nQuestion: {user_message}"})
    else:
        messages.append({"role": "user", "content": user_message})

    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "system": SYSTEM_PROMPT,
        "stream": False,
        "options": {
            "temperature": 0.2,   # low temp = more deterministic for ops tasks
            "num_predict": 512,   # keep responses short — we're on 4GB RAM
        }
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["message"]["content"]
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"Ollama API error {e.response.status_code}: {e.response.text}") from e
    except httpx.ConnectError:
        raise RuntimeError(f"Cannot connect to Ollama at {OLLAMA_BASE_URL}") from None
    except httpx.TimeoutException:
        raise RuntimeError("Ollama request timed out (model may be overloaded)") from None


async def analyze_logs(container_name: str, logs: str) -> dict:
    """Ask the LLM to analyze container logs and return structured result."""
    prompt = f"""Analyze these logs from container '{container_name}' and respond with JSON only:
{{
  "severity": "ok|warn|error|critical",
  "root_cause": "one sentence",
  "fix": "one sentence action",
  "auto_heal": true/false,
  "heal_action": "restart|pull_restart|exec:<command>|none"
}}

Logs (last 50 lines):
{logs[-3000:]}"""

    try:
        raw = await chat(prompt)
    except RuntimeError as e:
        # LLM unavailable — return a safe degraded response instead of crashing
        return {
            "severity": "unknown",
            "root_cause": f"LLM unavailable: {e}",
            "fix": "Check Ollama service and model pull status",
            "auto_heal": False,
            "heal_action": "none",
        }

    # Strip any accidental markdown fences
    raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "severity": "warn",
            "root_cause": "LLM returned non-JSON — check logs manually",
            "fix": "Review raw logs",
            "auto_heal": False,
            "heal_action": "none",
            "raw": raw,
        }


async def check_ollama_health() -> bool:
    """Return True if Ollama is reachable AND the required model is pulled."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            return any(LLM_MODEL.split(":")[0] in m for m in models)
    except Exception:
        return False