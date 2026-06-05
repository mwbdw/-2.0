#!/bin/bash
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
INST="$HOME/Library/Application Support/火花2.0"
APP="$HOME/Desktop/抖音续火花.app"

echo "=== 抖音续火花 2.0 安装程序 ==="
echo ""

# ── 1. 复制程序文件 ──────────────────────────────────────────────────────────
echo "► 复制程序文件..."
mkdir -p "$INST"
cp "$SRC/app.py" "$SRC/server.py" "$SRC/automation.py" "$INST/"
cp -r "$SRC/static" "$INST/"
[ -f "$SRC/config.json"  ] && cp "$SRC/config.json"  "$INST/"
[ -f "$SRC/cookies.json" ] && cp "$SRC/cookies.json" "$INST/"

# ── 2. 创建 Python 虚拟环境 ─────────────────────────────────────────────────
if [ ! -d "$INST/.venv" ]; then
    echo "► 创建 Python 环境（约 1 分钟）..."
    python3 -m venv "$INST/.venv"
    "$INST/.venv/bin/pip" install -q \
        "fastapi>=0.111" "uvicorn[standard]>=0.29" \
        "playwright>=1.44" "schedule>=1.2" "pywebview>=4.0"
fi

# ── 3. 安装 Playwright Chromium ──────────────────────────────────────────────
if ! ls "$HOME/Library/Caches/ms-playwright/chromium-"*/INSTALLATION_COMPLETE &>/dev/null; then
    echo "► 下载 Chromium（约 200MB，请耐心等待）..."
    "$INST/.venv/bin/playwright" install chromium
fi

# ── 4. 找到真实 Python 路径（追溯所有 symlink，得到真实二进制） ──────────────
REAL_PY=$("$SRC/.venv/bin/python3" -c "
import sys, os
exe = sys.executable
while os.path.islink(exe):
    exe = os.path.join(os.path.dirname(exe), os.readlink(exe))
print(os.path.realpath(exe))
")
SITE_PKG="$INST/.venv/lib/python3.9/site-packages"

# ── 5. 创建 .app ─────────────────────────────────────────────────────────────
echo "► 创建 .app..."
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"

cat > "$APP/Contents/MacOS/抖音续火花" << LAUNCHER
#!/bin/bash
export PYTHONPATH="$SITE_PKG"
export PYTHONNOUSERSITE=1
export PLAYWRIGHT_BROWSERS_PATH="\$HOME/Library/Caches/ms-playwright"
# arch -arm64：launchd 默认会用 x86_64 运行 universal binary，强制指定 arm64
exec arch -arm64 "$REAL_PY" "$INST/app.py"
LAUNCHER
chmod +x "$APP/Contents/MacOS/抖音续火花"

cat > "$APP/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>CFBundleExecutable</key>     <string>抖音续火花</string>
    <key>CFBundleIdentifier</key>     <string>com.huahuo.v2</string>
    <key>CFBundleName</key>           <string>抖音续火花</string>
    <key>CFBundleDisplayName</key>    <string>抖音续火花 2.0</string>
    <key>CFBundlePackageType</key>    <string>APPL</string>
    <key>CFBundleShortVersionString</key> <string>2.0.0</string>
    <key>NSHighResolutionCapable</key>    <true/>
    <key>NSPrincipalClass</key>       <string>NSApplication</string>
    <key>LSMinimumSystemVersion</key> <string>12.0</string>
    <key>NSAppTransportSecurity</key>
    <dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict></plist>
PLIST

codesign -s - --force "$APP" 2>/dev/null

# ── 6. 同步更新辅助脚本 ──────────────────────────────────────────────────────
cat > "$INST/sync.sh" << SYNC
#!/bin/bash
# 当你修改了 Desktop/火花2.0 里的代码，运行这个脚本同步到已安装版本
SRC="$SRC"
INST="$INST"
cp "\$SRC/app.py" "\$SRC/server.py" "\$SRC/automation.py" "\$INST/"
cp -r "\$SRC/static" "\$INST/"
echo "同步完成"
SYNC
chmod +x "$INST/sync.sh"

echo ""
echo "============================================"
echo "  安装完成！"
echo "  桌面已生成「抖音续火花.app」"
echo "============================================"
echo ""
echo "首次运行提示："
echo "  双击 app → 若弹「无法打开」→ 系统设置 → 隐私与安全性 → 仍要打开"
echo "  之后可直接双击使用"
echo ""
echo "修改代码后同步："
echo "  bash \"$INST/sync.sh\""
