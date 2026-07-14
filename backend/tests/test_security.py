from __future__ import annotations

import asyncio
import json
import stat
import sys
from pathlib import Path

from backend.security import mask_secret, redact, safe_json, write_secret_file


def test_recursive_log_redaction_hides_common_secret_fields():
    payload = {
        "Authorization": "Bearer do-not-log",
        "nested": {"apiKey": "do-not-log", "normal": "visible"},
        "items": [{"access_token": "do-not-log"}],
    }

    sanitized = safe_json(payload)

    assert "do-not-log" not in sanitized
    assert json.loads(sanitized)["nested"]["normal"] == "visible"
    assert redact(payload)["Authorization"] == "***REDACTED***"


def test_secret_file_is_owner_read_write_only(tmp_path: Path):
    secret = tmp_path / "secrets" / "provider-api-key"
    write_secret_file(secret, "test-secret")

    assert secret.read_text() == "test-secret"
    assert stat.S_IMODE(secret.stat().st_mode) == 0o600
    assert mask_secret("1234567890abcdef") == "123456***cdef"
    assert mask_secret("short") == "***"


def test_save_config_uses_secret_file_and_removes_duplicate_auth(tmp_path: Path, monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend_dir))
    try:
        import main as application

        config_dir = tmp_path / "config"
        data_dir = tmp_path / "data"
        secret_dir = config_dir / "secrets"
        data_dir.mkdir(parents=True)
        (data_dir / "auth.json").write_text(json.dumps({
            "deepseek": {"apiKey": "old-key"},
            "other": {"token": "keep-me"},
        }))
        monkeypatch.setattr(application, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(application, "DATA_DIR", data_dir)
        monkeypatch.setattr(application, "SECRET_DIR", secret_dir)

        result = asyncio.run(application.save_config(application.ConfigReq(
            provider="deepseek", model="test-model", baseURL="https://example.test", apiKey="new-test-key",
        )))
    finally:
        sys.path.pop(0)

    assert result["ok"] is True
    assert (secret_dir / "deepseek-api-key").read_text() == "new-test-key"
    auth = json.loads((data_dir / "auth.json").read_text())
    assert "deepseek" not in auth
    assert auth["other"]["token"] == "keep-me"
