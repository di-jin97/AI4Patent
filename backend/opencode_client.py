import asyncio
import os
import re
import json as _json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OPENCODE_EXE = str(BASE / "bin" / "opencode" / "opencode.exe")
WORKSPACE = BASE / "workspace"
UPLOADS = WORKSPACE / "uploads"
DEFAULT_MODEL = "agent-plan/glm-5.2"
_ANSI = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


def _env():
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(BASE / "config")
    env["XDG_DATA_HOME"] = str(BASE / "data")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


async def run_task(text, model=DEFAULT_MODEL, files=None, session_id=None):
    """opencode run --format json。session_id 不为空时续接该 session（追问）。"""
    args = [OPENCODE_EXE, "run", "--format", "json", text]
    if session_id:
        args += ["--session", session_id]
    else:
        for fn in (files or []):
            f = UPLOADS / fn
            if f.is_file():
                args += ["-f", str(f)]
    args += ["--model", model]
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=_env(),
        cwd=str(WORKSPACE),
    )
    sid = None
    texts = []
    buf = ""
    while True:
        chunk = await proc.stdout.read(8192)
        if not chunk:
            break
        buf += chunk.decode("utf-8", errors="replace")
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            line = _ANSI.sub("", line.strip())
            if not line.startswith("{"):
                continue
            try:
                evt = _json.loads(line)
            except Exception:
                continue
            if not sid and evt.get("sessionID"):
                sid = evt["sessionID"]
            t = evt.get("type")
            part = evt.get("part") or {}
            if t == "text" and part.get("text"):
                texts.append(part["text"])
                yield {"type": "output", "text": part["text"]}
            elif t == "step_start":
                yield {"type": "step"}
    await proc.wait()
    yield {"type": "done", "result": "\n".join(texts), "session_id": sid}
