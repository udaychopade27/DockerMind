import copy
import logging
import re
from typing import Any
from uvicorn.config import LOGGING_CONFIG

class TokenRedactingFilter(logging.Filter):
    """
    Security filter that redacts sensitive tokens (JWTs, Bearer headers,
    URL query parameter tokens, and password fields) from all log outputs.
    """
    # Standard 3-part base64url JWT pattern (eyJ...)
    JWT_PATTERN = re.compile(r'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+')

    # URL query parameter token=... or &token=...
    TOKEN_QUERY_PATTERN = re.compile(r'([?&](?:token|access_token|secret)=)[^&\s"\')]+', re.IGNORECASE)

    # Authorization header: Bearer <token>
    BEARER_PATTERN = re.compile(r'(Bearer\s+)[A-Za-z0-9_.\-]+', re.IGNORECASE)

    # JSON fields: "token": "...", "access_token": "...", "password": "..."
    JSON_TOKEN_PATTERN = re.compile(r'("(?:token|access_token|password|secret)"\s*:\s*")[^"]+(")', re.IGNORECASE)

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = self.redact(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: self.redact(v) if isinstance(v, str) else v for k, v in record.args.items()}
                elif isinstance(record.args, tuple):
                    record.args = tuple(self.redact(arg) if isinstance(arg, str) else arg for arg in record.args)
                elif isinstance(record.args, list):
                    record.args = [self.redact(arg) if isinstance(arg, str) else arg for arg in record.args]
        except Exception:
            pass
        return True

    @classmethod
    def redact(cls, text: Any) -> Any:
        if not isinstance(text, str):
            return text
        text = cls.JWT_PATTERN.sub('[REDACTED_JWT]', text)
        text = cls.TOKEN_QUERY_PATTERN.sub(r'\1[REDACTED_TOKEN]', text)
        text = cls.BEARER_PATTERN.sub(r'\1[REDACTED_TOKEN]', text)
        text = cls.JSON_TOKEN_PATTERN.sub(r'\1[REDACTED]\2', text)
        return text


def get_redacted_logging_config() -> dict:
    """
    Returns a copy of uvicorn LOGGING_CONFIG with the TokenRedactingFilter attached
    to all handlers (access, default, error).
    """
    cfg = copy.deepcopy(LOGGING_CONFIG)
    cfg["filters"] = {
        "token_redactor": {
            "()": TokenRedactingFilter
        }
    }
    if "handlers" in cfg:
        for handler_name in cfg["handlers"]:
            cfg["handlers"][handler_name].setdefault("filters", []).append("token_redactor")
    return cfg


def install_global_redactor():
    """
    Attaches TokenRedactingFilter to Python's root logger and all known loggers/handlers.
    """
    redactor = TokenRedactingFilter()
    root = logging.getLogger()
    root.addFilter(redactor)
    for h in root.handlers:
        h.addFilter(redactor)

    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        l = logging.getLogger(name)
        l.addFilter(redactor)
        for h in l.handlers:
            h.addFilter(redactor)