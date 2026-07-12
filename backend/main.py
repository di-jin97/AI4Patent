import json
import shutil
import logging
import uuid
from pathlib import Path
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from opencode_client import run_task, kill_current, kill_task

BASE = Path(__file__).resolve().parent.parent
FRONTEND = BASE / "frontend"
WORKSPACE = BASE / "workspace"
UPLOADS = WORKSPACE / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)
CONFIG_DIR = BASE / "config" / "opencode"
DATA_DIR = BASE / "data" / "opencode"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR = BASE / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(LOG_DIR / "ai4p.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger("ai4p")
# Suppress noisy uvicorn access logs (200 OK on every /api/files poll etc.)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

app = FastAPI(title="AI4P 专利工作台")


def sse(d):
    return f"data: {json.dumps(d, ensure_ascii=False)}\n\n"


def _safe_name(name: str) -> str:
    """Strip directory components to prevent path traversal."""
    return Path(name).name


@app.get("/api/health")
async def health():
    return {"ok": True, "engine": "opencode run"}


# ===== 配置管理（一键傻瓜式） =====
@app.get("/api/config")
async def get_config():
    cfg_path = CONFIG_DIR / "opencode.json"
    auth_path = DATA_DIR / "auth.json"
    result = {"configured": False, "provider": "", "model": "", "baseURL": "", "apiKey": ""}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            full_model = cfg.get("model", "")
            if "/" in full_model:
                result["provider"] = full_model.split("/")[0]
                result["model"] = full_model.split("/", 1)[1]
            else:
                result["model"] = full_model
            p = cfg.get("provider", {}).get(result["provider"], {})
            result["baseURL"] = p.get("options", {}).get("baseURL", "")
        except Exception:
            pass
    if auth_path.exists():
        try:
            auth = json.loads(auth_path.read_text(encoding="utf-8"))
            prov = result["provider"]
            if prov and prov in auth and auth[prov].get("apiKey"):
                result["configured"] = True
                k = auth[prov]["apiKey"]
                result["apiKey"] = k[:6] + "***" + k[-4:] if len(k) > 12 else "***"
        except Exception:
            pass
    return result


class ConfigReq(BaseModel):
    provider: str = "agent-plan"
    model: str = "glm-5.2"
    baseURL: str = "https://ark.cn-beijing.volces.com/api/plan/v3"
    apiKey: str = ""


@app.post("/api/config")
async def save_config(req: ConfigReq):
    provider = req.provider.strip() or "custom"
    model = req.model.strip() or "glm-5.2"
    baseURL = req.baseURL.strip()
    apiKey = req.apiKey.strip()
    if not apiKey:
        return {"ok": False, "error": "API Key 不能为空"}
    opencode_cfg = {
        "$schema": "https://opencode.ai/config.json",
        "model": f"{provider}/{model}",
        "provider": {
            provider: {
                "name": provider,
                "npm": "@ai-sdk/openai-compatible",
                "options": {"apiKey": apiKey, "baseURL": baseURL},
                "models": {
                    model: {"name": model, "limit": {"context": 1048576, "output": 16384}}
                }
            }
        },
    }

    # Preserve MCP server config (EXA search etc.) if it already exists
    cfg_path = CONFIG_DIR / "opencode.json"
    if cfg_path.exists():
        try:
            old = json.loads(cfg_path.read_text(encoding="utf-8"))
            if "mcp" in old:
                opencode_cfg["mcp"] = old["mcp"]
        except Exception:
            pass
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "opencode.json").write_text(
        json.dumps(opencode_cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    auth = {provider: {"apiKey": apiKey}}
    (DATA_DIR / "auth.json").write_text(
        json.dumps(auth, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info(f"配置已保存: {provider}/{model} @ {baseURL}")
    return {"ok": True, "model": f"{provider}/{model}"}


# ===== 文件管理 =====
@app.get("/api/files")
async def list_files():
    uploads = []
    for f in sorted(UPLOADS.iterdir()):
        if f.is_file():
            uploads.append({"name": f.name, "size": f.stat().st_size, "type": "upload"})
    generated = []
    for f in sorted(WORKSPACE.iterdir()):
        if f.is_file():
            generated.append({"name": f.name, "size": f.stat().st_size, "type": "generated"})
    return {"uploads": uploads, "generated": generated}


@app.post("/api/upload")
async def upload(files: list[UploadFile] = File(...)):
    saved = []
    for f in files:
        dest = UPLOADS / Path(f.filename).name
        with dest.open("wb") as out:
            shutil.copyfileobj(f.file, out)
        saved.append(dest.name)
    logger.info(f"上传文件: {saved}")
    return {"uploaded": saved}


@app.get("/api/download/{name}")
async def download(name: str):
    name = _safe_name(name)
    for d in [UPLOADS, WORKSPACE]:
        f = d / name
        if f.is_file():
            return FileResponse(str(f), filename=name)
    return JSONResponse({"error": "not found"}, status_code=404)


@app.delete("/api/files/{name}")
async def delete_file(name: str):
    name = _safe_name(name)
    for d in [UPLOADS, WORKSPACE]:
        f = d / name
        if f.is_file():
            f.unlink()
            logger.info(f"删除文件: {name}")
            return {"deleted": name}
    return JSONResponse({"error": "not found"}, status_code=404)


# ===== 任务执行 =====
class Task(BaseModel):
    text: str
    model: str = "agent-plan/glm-5.2"
    files: list[str] = []
    session_id: str | None = None


@app.post("/api/run")
async def run(task: Task):
    task_id = str(uuid.uuid4())
    async def gen():
        yield sse({"type": "task_id", "task_id": task_id})
        try:
            tag = f"续接session={task.session_id[:16]}" if task.session_id else f"附带文件={task.files}"
            logger.info(f"任务开始: model={task.model}, {tag}")
            yield sse({"type": "status", "text": "已提交，agent 工作中..." if not task.session_id else "追问中..."})
            async for evt in run_task(task.text, task.model, task.files, task.session_id, task_id):
                et = evt.get("type")
                if et == "output":
                    logger.info(f"  [output] {evt['text'][:2000]}")
                elif et == "log":
                    raw_t = evt.get("event_type", "?")
                    part = evt.get("part", {})
                    logger.info(f"  [{raw_t}] {json.dumps(part, ensure_ascii=False)[:1000]}")
                elif et == "step":
                    logger.info("  [step]")
                yield sse(evt)
            logger.info("任务完成")
        except Exception as e:
            logger.exception(f"任务异常: {e}")
            yield sse({"type": "error", "error": f"{type(e).__name__}: {e}"})
    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/stop")
async def stop(task_id: str | None = None):
    """Stop a specific task (by task_id) or all running tasks."""
    if task_id:
        kill_task(task_id)
    else:
        kill_current()
    return {"ok": True}


@app.get("/")
async def index():
    return FileResponse(str(FRONTEND / "index.html"), headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")
