"""Small, dependency-free helpers for handling secrets safely."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


_SENSITIVE_KEY_PARTS = (
    "api_key", "apikey", "authorization", "secret", "password", "token",
    "cookie", "credential",
)


def is_sensitive_key(key: object) -> bool:
    """Return whether a mapping key is likely to hold a secret."""
    normalized = str(key).lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def redact(value: Any) -> Any:
    """Return a logging-safe copy without recursively exposing credentials."""
    if isinstance(value, dict):
        return {
            key: "***REDACTED***" if is_sensitive_key(key) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    return value


def safe_json(value: Any) -> str:
    """Serialize a value for logs after redacting secret-bearing fields."""
    return json.dumps(redact(value), ensure_ascii=False, default=str)


def mask_secret(value: str) -> str:
    """Return a small, non-reversible display hint for a configured key."""
    if not value:
        return ""
    return f"{value[:6]}***{value[-4:]}" if len(value) > 12 else "***"


def write_secret_file(path: Path, value: str) -> None:
    """Atomically write a project-local secret with owner-only permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass

    fd, temporary_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value)
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise
