import json
from pathlib import Path


def test_opencode_example_has_a_safe_remote_exa_mcp_configuration():
    path = Path(__file__).resolve().parents[2] / "config" / "opencode" / "opencode.json.example"
    config = json.loads(path.read_text(encoding="utf-8"))

    assert config["mcp"]["exa"] == {
        "url": "https://mcp.exa.ai/mcp",
        "type": "remote",
        "enabled": True,
    }
    assert "secrets/" in config["provider"]["deepseek"]["options"]["apiKey"]
