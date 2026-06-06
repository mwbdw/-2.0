#!/bin/bash
echo "=== 抖音续火花：安装 Chromium 浏览器 ==="
echo ""

# 找 app 位置
APP=""
for p in \
  "$HOME/Applications/火花2.0.app" \
  "/Applications/火花2.0.app" \
  "$HOME/Downloads/火花2.0.app" \
  "$HOME/Desktop/火花2.0.app"
do
  if [ -d "$p" ]; then APP="$p"; break; fi
done

if [ -z "$APP" ]; then
  echo "❌ 找不到 火花2.0.app，请先将 app 拖入「应用程序」文件夹后再运行此脚本。"
  echo ""
  read -p "按回车退出..."
  exit 1
fi

NODE="$APP/Contents/Resources/playwright/driver/node"
CLI="$APP/Contents/Resources/playwright/driver/package/cli.js"

if [ ! -f "$NODE" ] || [ ! -f "$CLI" ]; then
  echo "❌ app 内未找到 Playwright 驱动，请重新下载 app。"
  echo ""
  read -p "按回车退出..."
  exit 1
fi

echo "✓ 找到 app：$APP"
echo "► 开始下载 Chromium（约 130MB，请勿关闭此窗口）..."
echo ""

export PLAYWRIGHT_BROWSERS_PATH="$HOME/Library/Caches/ms-playwright"
"$NODE" "$CLI" install chromium

echo ""
echo "============================================"
echo "  ✓ Chromium 安装完成！现在可以打开 app 登录。"
echo "============================================"
echo ""
read -p "按回车关闭..."
