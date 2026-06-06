"""
app.py — 独立窗口启动器
用 pywebview 在原生 macOS 窗口里显示界面，不需要打开浏览器。
"""
import os
import sys
import socket
import threading
import time
from pathlib import Path

# 确保工作目录是脚本所在目录
os.chdir(Path(__file__).parent)

# 告诉 server.py 不要自动打开浏览器
os.environ["HUAHUO_LAUNCHER"] = "1"

# Playwright 浏览器路径：优先用用户缓存，打包环境下自动下载
_browsers_cache = Path.home() / "Library" / "Caches" / "ms-playwright"
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_browsers_cache)

def _ensure_chromium(log=None):
    """后台下载 Chromium（约 130MB），逐行输出进度"""
    import subprocess

    def emit(msg):
        if log: log(msg)
        else: print(msg, flush=True)

    if list(_browsers_cache.glob("chromium-*/chrome-mac-arm64/Google Chrome for Testing.app")):
        emit("[✓] 浏览器已就绪，可以登录")
        return

    emit("[~] 首次运行：正在下载 Chromium 浏览器（约 130MB），完成前请勿点击登录…")

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        node = Path(meipass) / "playwright" / "driver" / "node"
        cli  = Path(meipass) / "playwright" / "driver" / "package" / "cli.js"
        cmd  = [str(node), str(cli), "install", "chromium"] if (node.exists() and cli.exists()) else None
    else:
        cmd = [sys.executable, "-m", "playwright", "install", "chromium"]

    if not cmd:
        emit("[✗] 找不到 Playwright 驱动，请重新下载 app")
        return

    # 按字节读取，\r 和 \n 都作为行分隔符（兼容进度条）
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    buf = b""
    while True:
        ch = proc.stdout.read(1)
        if not ch:
            break
        if ch in (b"\n", b"\r"):
            line = buf.decode("utf-8", errors="replace").strip()
            if line:
                emit(f"[~] {line}")
            buf = b""
        else:
            buf += ch
    if buf:
        line = buf.decode("utf-8", errors="replace").strip()
        if line:
            emit(f"[~] {line}")
    proc.wait()

    if proc.returncode == 0:
        emit("[✓] Chromium 下载完成，现在可以点击登录了")
    else:
        emit("[✗] Chromium 下载失败，请检查网络后重试")

PORT = 8765


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _kill_old_server():
    import subprocess, signal
    try:
        r = subprocess.run(["lsof", "-ti", f":{PORT}"], capture_output=True, text=True)
        for pid in r.stdout.strip().split():
            try:
                os.kill(int(pid), signal.SIGTERM)
            except Exception:
                pass
        time.sleep(0.5)
    except Exception:
        pass


def _start_server():
    import server
    import uvicorn
    uvicorn.run(
        server.app,
        host="127.0.0.1",
        port=PORT,
        log_level="warning",
    )


def _wait_for_server(timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _port_free(PORT):
            return True
        time.sleep(0.1)
    return False


def main():
    import webview

    # 清理旧进程
    if not _port_free(PORT):
        _kill_old_server()

    # 后台启动服务器
    t = threading.Thread(target=_start_server, daemon=True)
    t.start()

    # 等服务器就绪
    if not _wait_for_server():
        print("服务器启动失败", file=sys.stderr)
        sys.exit(1)

    # 服务器就绪后，推启动消息 + 后台检查/下载 Chromium
    import server as _srv

    def _init_log():
        time.sleep(1)  # 等前端 SSE 连接建立
        _srv._push_log("[✓] 应用已启动，准备就绪")
        _ensure_chromium(_srv._push_log)

    threading.Thread(target=_init_log, daemon=True).start()

    # 创建原生窗口
    window = webview.create_window(
        title="🔥 抖音续火花",
        url=f"http://127.0.0.1:{PORT}",
        width=960,
        height=720,
        resizable=True,
        min_size=(720, 560),
    )
    webview.start()


if __name__ == "__main__":
    main()
