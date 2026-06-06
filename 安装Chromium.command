#!/bin/bash
echo ""
echo "🔥 抖音续火花 — Chromium 安装程序"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 找 app 位置
APP=""
for p in \
  "/Applications/火花2.0.app" \
  "$HOME/Applications/火花2.0.app" \
  "$HOME/Desktop/火花2.0.app" \
  "$HOME/Downloads/火花2.0.app"
do
  if [ -d "$p" ]; then APP="$p"; break; fi
done

if [ -z "$APP" ]; then
  echo "❌ 找不到 火花2.0.app"
  echo "   请先将 app 拖入「应用程序」文件夹后再运行此脚本。"
  echo ""
  read -rp "按回车退出..."
  exit 1
fi

NODE="$APP/Contents/Resources/playwright/driver/node"
CLI="$APP/Contents/Resources/playwright/driver/package/cli.js"

if [ ! -f "$NODE" ] || [ ! -f "$CLI" ]; then
  echo "❌ app 内未找到 Playwright 驱动，请重新下载 app。"
  echo ""
  read -rp "按回车退出..."
  exit 1
fi

echo "✓ 找到 app：$APP"
echo ""

# 检查是否已安装
export PLAYWRIGHT_BROWSERS_PATH="$HOME/Library/Caches/ms-playwright"
if ls "$PLAYWRIGHT_BROWSERS_PATH"/chromium-*/chrome-mac-arm64/"Google Chrome for Testing.app" &>/dev/null 2>&1; then
  echo "✓ Chromium 已安装，无需重复下载。"
  echo ""
  read -rp "按回车关闭..."
  exit 0
fi

echo "► 开始下载 Chromium（约 130MB）..."
echo "  下载过程中请保持网络畅通，不要关闭此窗口。"
echo ""

# 运行并实时显示进度
"$NODE" "$CLI" install chromium 2>&1 | while IFS= read -r line; do
  # 过滤空行
  [ -z "$line" ] && continue
  # 下载进度行（含 Mb 或 %）直接显示
  if echo "$line" | grep -qE "Mb|%|Downloading|downloaded to"; then
    echo "  $line"
  else
    echo "  $line"
  fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✓ 安装完成！现在可以打开 app 登录了。"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
read -rp "按回车关闭..."
