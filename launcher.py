"""
launcher.py — 抖音续火花 2.0 打包入口
所有环境变量必须在其他任何 import 之前设置好。
"""
import os
import sys
import subprocess
import threading
import webbrowser
import time
import logging
from pathlib import Path


# ── 1. 路径解析 ───────────────────────────────────────────────────────────────

def _resource_dir() -> Path:
    """只读的 bundle 资源目录（static/ 及 Python 模块）。"""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def _data_dir() -> Path:
    """可写的用户数据目录。"""
    d = Path.home() / "Library" / "Application Support" / "火花2.0"
    d.mkdir(parents=True, exist_ok=True)
    return d


RESOURCE_DIR = _resource_dir()
DATA_DIR = _data_dir()

# 发布路径到环境变量，server.py / automation.py 在 import 时会读取
os.environ["HUAHUO_RESOURCE_DIR"] = str(RESOURCE_DIR)
os.environ["HUAHUO_DATA_DIR"] = str(DATA_DIR)
os.environ["HUAHUO_LAUNCHER"] = "1"

# 关键：在任何 playwright import 之前覆盖浏览器缓存路径。
# playwright/_impl/_transport.py 在 frozen 模式下会 setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")，
# "0" 表示"在 bundle 内部找浏览器"——但 bundle 是只读的，会找不到。
# 我们提前 setdefault，让它的 setdefault 变成 no-op。
BROWSERS_CACHE = str(Path.home() / "Library" / "Caches" / "ms-playwright")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", BROWSERS_CACHE)


# ── 2. 日志重定向（.app 无终端窗口） ──────────────────────────────────────────

LOG_FILE = DATA_DIR / "app.log"


def _setup_logging():
    log_fh = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    sys.stderr = log_fh
    logging.basicConfig(
        stream=log_fh,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


_setup_logging()


# ── 3. Chromium 检测与安装 ────────────────────────────────────────────────────

def _chromium_installed() -> bool:
    pw_cache = Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"])
    if pw_cache.exists():
        for d in pw_cache.glob("chromium-*"):
            if (d / "INSTALLATION_COMPLETE").exists():
                return True
    return False


def _show_dialog(msg: str):
    """macOS 原生弹窗（无终端时使用）。"""
    try:
        subprocess.run(
            [
                "osascript", "-e",
                f'display dialog "{msg}" buttons {{"好的"}} default button "好的" '
                f"with icon note giving up after 120",
            ],
            timeout=125,
        )
    except Exception:
        pass


def _install_chromium() -> bool:
    _show_dialog(
        "首次启动需要下载 Chromium 浏览器（约 200 MB），请确保网络畅通。\\n"
        "点击「好的」后将在后台开始下载，请耐心等待（约 1-3 分钟）…"
    )
    try:
        from playwright._impl._driver import compute_driver_executable, get_driver_env

        driver_exe, driver_cli = compute_driver_executable()
        env = get_driver_env()
        env["PLAYWRIGHT_BROWSERS_PATH"] = BROWSERS_CACHE
        result = subprocess.run(
            [str(driver_exe), str(driver_cli), "install", "chromium"],
            env=env,
            timeout=600,
        )
        return result.returncode == 0
    except Exception as e:
        logging.error(f"Chromium 安装出错: {e}")
        return False


def ensure_chromium():
    if _chromium_installed():
        return
    if not _install_chromium():
        _show_dialog(
            "Chromium 安装失败。\\n"
            f"请查看日志：\\n~/Library/Application Support/火花2.0/app.log"
        )
        sys.exit(1)
    if not _chromium_installed():
        _show_dialog("安装后未检测到 Chromium，请重启应用重试。")
        sys.exit(1)


# ── 4. 启动服务器并打开浏览器 ─────────────────────────────────────────────────

PORT = 8765


def _port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def _kill_port(port: int):
    """杀掉占用端口的旧进程。"""
    import signal
    try:
        import subprocess
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True
        )
        pids = result.stdout.strip().split()
        for pid in pids:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except Exception:
                pass
        time.sleep(0.5)
    except Exception:
        pass


def _open_browser_delayed(delay: float = 2.5):
    def _work():
        time.sleep(delay)
        webbrowser.open(f"http://localhost:{PORT}")

    threading.Thread(target=_work, daemon=True).start()


def main():
    ensure_chromium()

    # 如果端口已被占用，先杀掉旧进程
    if _port_in_use(PORT):
        _kill_port(PORT)

    _open_browser_delayed(2.5)

    # 在环境变量设好之后再 import server（server.py 在模块级读取环境变量）
    import server
    import uvicorn

    uvicorn.run(
        server.app,
        host="127.0.0.1",
        port=PORT,
        log_level="info",
        loop="asyncio",    # 避免 frozen app 里 uvloop 的动态 import 问题
        http="h11",        # 避免 httptools 动态 import 问题
        ws="websockets",   # 避免 wsproto 动态 import 问题
    )


if __name__ == "__main__":
    main()
