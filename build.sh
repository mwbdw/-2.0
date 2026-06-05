#!/bin/bash
set -e
cd "$(dirname "$0")"

PYTHON=".venv/bin/python3"
APP="dist/火花2.0.app"

echo "=== 检查 PyInstaller ==="
"$PYTHON" -m PyInstaller --version &>/dev/null || "$PYTHON" -m pip install pyinstaller -q

echo ""
echo "=== 清理旧构建 ==="
rm -rf build/ dist/

echo ""
echo "=== 构建 火花2.0.app ==="
"$PYTHON" -m PyInstaller 火花2.0.spec --noconfirm --clean --log-level WARN

echo ""
echo "=== 移除签名（未签名比损坏签名更容易被系统信任） ==="
# 移除所有子文件签名
find "$APP" -type f \( -name "*.dylib" -o -name "*.so" \) \
    -exec codesign --remove-signature {} \; 2>/dev/null || true
# 移除主 bundle 签名
codesign --remove-signature "$APP" 2>/dev/null || true
echo "签名已移除"

echo ""
echo "============================================"
echo "  构建完成！输出: $APP"
echo "============================================"
echo ""
echo "【首次使用解锁步骤】"
echo "  1. 双击 dist/火花2.0.app → 弹窗提示无法打开 → 点「好」"
echo "  2. 打开「系统设置」→「隐私与安全性」"
echo "  3. 往下滚动到「安全性」区域"
echo "  4. 看到「火花2.0 已被阻止」→ 点「仍要打开」"
echo "  5. 之后可以直接双击使用"
echo ""
echo "  首次运行若无 Chromium，会弹窗提示自动下载（约 200 MB）"
