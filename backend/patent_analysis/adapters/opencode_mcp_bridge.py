"""OpenCode MCP bridge.

按 design doc Section 7.4 定义。
当前未能直接调用 Exa MCP SDK，故此 bridge 通过 OpenCode session 调用 MCP 工具。
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Any


class OpenCodeMCPBridgeError(RuntimeError):
    """Raised when OpenCode cannot execute an MCP tool request."""


class OpenCodeMCPBridge:
    """通过 OpenCode 子进程调用 MCP 工具"""

    def __init__(self) -> None:
        self._base = Path(__file__).resolve().parent.parent.parent.parent

    async def execute(self, tool_name: str, payload: dict[str, Any]) -> Any:
        """执行 MCP 工具调用. 返回 JSON 结果或原始文本."""
        import subprocess

        args = [
            self._opencode_exe(),
            "mcp", "call",
            "--tool", tool_name,
            "--payload", json.dumps(payload),
        ]
        env = os.environ.copy()
        env["XDG_CONFIG_HOME"] = str(self._base / "config")
        env["XDG_DATA_HOME"] = str(self._base / "data")

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(self._base / "workspace"),
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=60
            )
            output = stdout.decode("utf-8", errors="replace").strip()
            error_output = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                detail = error_output or output or f"exit code {proc.returncode}"
                raise OpenCodeMCPBridgeError(
                    f"MCP tool {tool_name} failed: {detail[:500]}"
                )
            if not output:
                raise OpenCodeMCPBridgeError(
                    f"MCP tool {tool_name} returned no output"
                )

            try:
                return json.loads(output)
            except json.JSONDecodeError:
                return output
        except asyncio.TimeoutError as exc:
            raise OpenCodeMCPBridgeError(
                f"MCP tool {tool_name} timed out after 60 seconds"
            ) from exc
        except OSError as exc:
            raise OpenCodeMCPBridgeError(
                f"Could not start OpenCode for MCP tool {tool_name}: {exc}"
            ) from exc

    def _opencode_exe(self) -> str:
        import shutil
        configured = os.environ.get("OPENCODE_EXE")
        if configured:
            return configured
        system_opencode = shutil.which("opencode")
        if system_opencode:
            return system_opencode
        return str(self._base / "bin" / "opencode" / "opencode.exe")
