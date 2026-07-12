import asyncio
import os
import re
import uuid
import json as _json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OPENCODE_EXE = str(BASE / "bin" / "opencode" / "opencode.exe")
WORKSPACE = BASE / "workspace"
UPLOADS = WORKSPACE / "uploads"
DEFAULT_MODEL = "agent-plan/glm-5.2"
_ANSI = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
_IDLE_TIMEOUT = 300  # seconds without output before killing subprocess
_procs = {}  # task_id -> proc, supports parallel execution


def kill_task(task_id):
    """Kill a specific running task by task_id."""
    proc = _procs.get(task_id)
    if proc and proc.returncode is None:
        proc.kill()
        return True
    return False


def _env():
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(BASE / "config")
    env["XDG_DATA_HOME"] = str(BASE / "data")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def kill_current():
    """Kill all running tasks. Called by /api/stop when no task_id given."""
    for proc in list(_procs.values()):
        if proc and proc.returncode is None:
            proc.kill()


async def run_task(text, model=DEFAULT_MODEL, files=None, session_id=None, task_id=None):
    """opencode run --format json。session_id 不为空时续接该 session（追问）。
    task_id 用于多模块并行时追踪/停止单个任务。"""
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
    if task_id is None:
        task_id = str(uuid.uuid4())
    _procs[task_id] = proc
    sid = None
    texts = []
    buf = ""
    try:
        while True:
            try:
                chunk = await asyncio.wait_for(proc.stdout.read(8192), timeout=_IDLE_TIMEOUT)
            except asyncio.TimeoutError:
                yield {"type": "error", "error": f"任务超时（{_IDLE_TIMEOUT}秒无输出），已终止"}
                break
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
        # flush remaining buffer after EOF (last line without trailing newline)
        if buf.strip():
            line = _ANSI.sub("", buf.strip())
            if line.startswith("{"):
                try:
                    evt = _json.loads(line)
                    if not sid and evt.get("sessionID"):
                        sid = evt["sessionID"]
                    t = evt.get("type")
                    part = evt.get("part") or {}
                    if t == "text" and part.get("text"):
                        texts.append(part["text"])
                        yield {"type": "output", "text": part["text"]}
                except Exception:
                    pass
    finally:
        if proc.returncode is None:
            proc.kill()
        await proc.wait()
        _procs.pop(task_id, None)
    yield {"type": "done", "result": "\n".join(texts), "session_id": sid}
