import asyncio
import json
import os
import queue
import threading
import webbrowser
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

import schedule
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import automation

_res = os.environ.get("HUAHUO_RESOURCE_DIR")
_dat = os.environ.get("HUAHUO_DATA_DIR")
BASE = Path(_res) if _res else Path(__file__).parent
_DATA = Path(_dat) if _dat else BASE
CONFIG_FILE = _DATA / "config.json"
COOKIES_FILE = _DATA / "cookies.json"
STATIC_DIR = BASE / "static"
PORT = 8765


@asynccontextmanager
async def lifespan(app: FastAPI):
    _state["login"] = automation.check_login(COOKIES_FILE)
    # launcher.py 负责打开浏览器；直接运行 server.py 时自己打开
    if not os.environ.get("HUAHUO_LAUNCHER"):
        webbrowser.open(f"http://localhost:{PORT}")
    yield


app = FastAPI(lifespan=lifespan)

# ── Global state ──────────────────────────────────────────────────────────────

_state = {
    "running": False,
    "scheduled": False,
    "last_run": None,
    "login": False,
}
_log_queue: queue.Queue = queue.Queue()
_scheduler_stop = threading.Event()
_scheduler_thread: Optional[threading.Thread] = None
_task_lock = threading.Lock()


def _push_log(msg: str):
    _log_queue.put(msg)


# ── Config helpers ────────────────────────────────────────────────────────────

def _read_config() -> dict:
    if not CONFIG_FILE.exists():
        return {"friends": [], "messages": [], "send_time": "08:00", "headless": False}
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def _write_config(data: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Automation thread helpers ─────────────────────────────────────────────────

def _run_locked(fn, task_name: str, update_last_run: bool = True):
    """Non-blocking task runner: acquires lock, manages state, runs fn."""
    if not _task_lock.acquire(blocking=False):
        _push_log("[!] 已有任务在运行，请稍后再试")
        return
    _state["running"] = True
    automation.set_log_callback(_push_log)
    try:
        fn()
    except Exception as e:
        _push_log(f"[✗] {task_name}异常: {e}")
    finally:
        _state["running"] = False
        if update_last_run:
            _state["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _task_lock.release()
        automation.set_log_callback(None)


def _run_task_thread(override_friends=None):
    def _work():
        _push_log("[→] 任务线程已启动")
        cfg = _read_config()
        if override_friends is not None:
            cfg = {**cfg, "friends": override_friends}
        automation.run_task(cfg, COOKIES_FILE)
        _push_log("[→] 任务线程已结束")
    _run_locked(_work, "任务线程")


def _login_thread():
    def _work():
        automation.do_login(COOKIES_FILE)
        _state["login"] = automation.check_login(COOKIES_FILE)
    _run_locked(_work, "登录线程", update_last_run=False)


# ── Scheduler ─────────────────────────────────────────────────────────────────

def _scheduler_loop(send_time: str):
    schedule.clear("spark")
    # 与「立即执行」保持一致：在新线程里启动，避免调度器线程环境差异
    def _spawn():
        threading.Thread(target=_run_task_thread, daemon=True).start()
    schedule.every().day.at(send_time).do(_spawn).tag("spark")
    while not _scheduler_stop.is_set():
        schedule.run_pending()
        _scheduler_stop.wait(timeout=10)
    schedule.clear("spark")


def _next_run_str() -> Optional[str]:
    jobs = schedule.get_jobs("spark")
    if not jobs:
        return None
    return jobs[0].next_run.strftime("%Y-%m-%d %H:%M:%S") if jobs[0].next_run else None


# ── Routes ────────────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/config")
async def get_config():
    return _read_config()


@app.put("/api/config")
async def put_config(body: dict):
    _write_config(body)
    return {"ok": True}


@app.get("/api/status")
async def get_status():
    return {
        "running": _state["running"],
        "scheduled": _state["scheduled"],
        "last_run": _state["last_run"],
        "next_run": _next_run_str(),
        "login": _state["login"],
    }


@app.post("/api/run")
async def post_run(request: Request):
    if _state["running"]:
        raise HTTPException(status_code=409, detail="任务正在运行中")
    try:
        body = await request.json()
    except Exception:
        body = {}
    override_friends = body.get("friends") if isinstance(body, dict) else None
    threading.Thread(target=_run_task_thread, args=(override_friends,), daemon=True).start()
    return {"ok": True}


def _start_scheduler(send_time: str):
    """启动调度器（内部复用，调用前确保旧线程已停止）。"""
    global _scheduler_thread, _scheduler_stop
    _scheduler_stop = threading.Event()
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop, args=(send_time,), daemon=True
    )
    _scheduler_thread.start()
    _state["scheduled"] = True


@app.post("/api/schedule")
async def post_schedule(body: dict):
    global _scheduler_stop
    action = body.get("action")

    if action == "start":
        if _state["scheduled"]:
            return {"ok": True, "msg": "已在运行"}
        cfg = _read_config()
        send_time = body.get("send_time") or cfg.get("send_time", "08:00")
        # 保存到配置
        cfg["send_time"] = send_time
        _write_config(cfg)
        _start_scheduler(send_time)
        _push_log(f"[✓] 定时任务已启动，每天 {send_time} 自动执行")
        return {"ok": True}

    elif action == "stop":
        if _scheduler_stop:
            _scheduler_stop.set()
        _state["scheduled"] = False
        _push_log("[✓] 定时任务已停止")
        return {"ok": True}

    elif action == "update_time":
        send_time = body.get("send_time", "").strip()
        if not send_time:
            raise HTTPException(status_code=400, detail="send_time 不能为空")
        # 保存到配置
        cfg = _read_config()
        cfg["send_time"] = send_time
        _write_config(cfg)
        # 如果调度器正在运行，重启以应用新时间
        if _state["scheduled"]:
            if _scheduler_stop:
                _scheduler_stop.set()
            _state["scheduled"] = False
            await asyncio.sleep(0.3)
            _start_scheduler(send_time)
            _push_log(f"[✓] 定时时间已更新为 {send_time}，调度器已重启")
        else:
            _push_log(f"[✓] 定时时间已设置为 {send_time}")
        return {"ok": True, "send_time": send_time}

    raise HTTPException(status_code=400, detail="action must be start / stop / update_time")


@app.post("/api/login")
async def post_login():
    if _state["running"]:
        raise HTTPException(status_code=409, detail="任务正在运行中")
    threading.Thread(target=_login_thread, daemon=True).start()
    return {"ok": True}


@app.post("/api/reset")
async def post_reset():
    """紧急重置：强制清除 running 状态和锁（任务卡死时使用）。"""
    _state["running"] = False
    # 尝试释放锁（如果已锁住）
    try:
        _task_lock.release()
    except RuntimeError:
        pass  # 锁本来就是空闲的
    _push_log("[✓] 运行状态已强制重置")
    return {"ok": True}


@app.get("/api/screenshots")
async def list_screenshots():
    debug_dir = _DATA / "debug"
    # 读取发送验证结果
    verify_map = {}
    result_file = debug_dir / "send_results.json"
    if result_file.exists():
        try:
            import json as _json
            verify_map = _json.loads(result_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    results = []
    if debug_dir.exists():
        for f in debug_dir.glob("after_send_*.png"):
            friend = f.stem[len("after_send_"):]
            v = verify_map.get(friend, {})
            results.append({
                "friend": friend,
                "mtime": f.stat().st_mtime,
                "verified": v.get("ok") if isinstance(v, dict) else None,
            })
    results.sort(key=lambda x: x["mtime"], reverse=True)
    return results


@app.get("/api/screenshots/{friend}")
async def get_screenshot(friend: str):
    if any(c in friend for c in ('/', '\\', '..', '\0')):
        raise HTTPException(status_code=400, detail="Invalid friend name")
    path = _DATA / "debug" / f"after_send_{friend}.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, media_type="image/png")


@app.delete("/api/cookies")
async def delete_cookies():
    if COOKIES_FILE.exists():
        COOKIES_FILE.unlink()
    _state["login"] = False
    _push_log("[✓] Cookie 已清除，下次运行需重新登录")
    return {"ok": True}


@app.get("/api/logs")
async def stream_logs():
    async def generate():
        loop = asyncio.get_running_loop()
        last_heartbeat = loop.time()
        while True:
            try:
                msg = _log_queue.get_nowait()
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                last_heartbeat = loop.time()
            except queue.Empty:
                now = loop.time()
                if now - last_heartbeat > 15:
                    yield ": heartbeat\n\n"
                    last_heartbeat = now
                await asyncio.sleep(0.2)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT)
