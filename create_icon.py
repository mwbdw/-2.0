"""
create_icon.py — 生成火花 2.0 的 macOS .icns 图标
使用 AppKit (PyObjC) 绘制，无需额外安装库。
"""
import os
import subprocess
import shutil
from pathlib import Path

ICON_DIR = Path("/tmp/huahuo.iconset")
ICNS_OUT = Path("/tmp/huahuo.icns")

SIZES = [16, 32, 64, 128, 256, 512, 1024]


def draw_icon(size: int, out_path: str):
    """用 AppKit 画单张 PNG。"""
    code = f"""
import sys, math
sys.path.insert(0, '/Users/maoweibo/Library/Application Support/火花2.0/.venv/lib/python3.9/site-packages')

from AppKit import (
    NSBitmapImageRep, NSGraphicsContext, NSColor, NSBezierPath,
    NSString, NSFont, NSGradient, NSMakeRect, NSMakePoint, NSMakeSize,
    NSFontAttributeName,
)

S = {size}

rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
    None, S, S, 8, 4, True, False, 'NSCalibratedRGBColorSpace', 0, 0)

ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.setCurrentContext_(ctx)

# ── 背景：深色圆角矩形 ────────────────────────────────────────────────────────
r = S * 0.18
rect = NSMakeRect(0, 0, S, S)
path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, r, r)

# 渐变背景：深紫 → 深橙
grad = NSGradient.alloc().initWithColors_([
    NSColor.colorWithRed_green_blue_alpha_(0.08, 0.04, 0.18, 1.0),
    NSColor.colorWithRed_green_blue_alpha_(0.22, 0.08, 0.02, 1.0),
])
grad.drawInBezierPath_angle_(path, -70)

# ── 外光晕：橙色发光圆圈 ─────────────────────────────────────────────────────
glow_path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, r, r)
NSColor.colorWithRed_green_blue_alpha_(1.0, 0.45, 0.0, 0.18).setStroke()
glow_path.setLineWidth_(S * 0.04)
glow_path.stroke()

# ── 主体：🔥 emoji ───────────────────────────────────────────────────────────
emoji  = "🔥"
fs     = S * 0.60
font   = NSFont.systemFontOfSize_(fs)
attrs  = {{NSFontAttributeName: font}}
ns_str = NSString.stringWithString_(emoji)
tsz    = ns_str.sizeWithAttributes_(attrs)
x      = (S - tsz.width)  / 2 + S * 0.02
y      = (S - tsz.height) / 2 - S * 0.04
ns_str.drawAtPoint_withAttributes_((x, y), attrs)

# ── 右下角小字"2.0" ──────────────────────────────────────────────────────────
if {size} >= 64:
    label   = "2.0"
    lfs     = S * 0.13
    lfont   = NSFont.boldSystemFontOfSize_(lfs)
    lattrs  = {{
        NSFontAttributeName: lfont,
        '__NSColor': NSColor.colorWithRed_green_blue_alpha_(1.0, 0.75, 0.2, 0.90),
    }}
    from AppKit import NSForegroundColorAttributeName
    lattrs2 = {{
        NSFontAttributeName: lfont,
        NSForegroundColorAttributeName: NSColor.colorWithRed_green_blue_alpha_(1.0, 0.8, 0.25, 0.92),
    }}
    ns_label = NSString.stringWithString_(label)
    lsz      = ns_label.sizeWithAttributes_(lattrs2)
    lx = S - lsz.width  - S * 0.09
    ly = S * 0.07
    ns_label.drawAtPoint_withAttributes_((lx, ly), lattrs2)

NSGraphicsContext.restoreGraphicsState()

data = rep.representationUsingType_properties_(4, None)
data.writeToFile_atomically_('{out_path}', True)
print("OK {size}x{size}")
"""
    env = os.environ.copy()
    real_py = "/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3.9"
    r = subprocess.run(["arch", "-arm64", real_py, "-c", code],
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        print(f"  ✗ {size}px 失败:\n{r.stderr[-400:]}")
        return False
    print(r.stdout.strip())
    return True


def build_icns():
    ICON_DIR.mkdir(exist_ok=True)

    # iconutil 所需的固定文件名列表
    spec = [
        (16,   "icon_16x16.png"),
        (32,   "icon_16x16@2x.png"),
        (32,   "icon_32x32.png"),
        (64,   "icon_32x32@2x.png"),
        (128,  "icon_128x128.png"),
        (256,  "icon_128x128@2x.png"),
        (256,  "icon_256x256.png"),
        (512,  "icon_256x256@2x.png"),
        (512,  "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]

    print("正在绘制图标...")
    cache: dict[int, bool] = {}
    for size, name in spec:
        dst = ICON_DIR / name
        if size not in cache:
            ok = draw_icon(size, str(dst))
            cache[size] = ok
        else:
            # 同尺寸复用
            src_name = next(n for s, n in spec if s == size and (ICON_DIR / n).exists())
            shutil.copy(ICON_DIR / src_name, dst)

    print("生成 .icns...")
    r = subprocess.run(
        ["iconutil", "-c", "icns", str(ICON_DIR), "-o", str(ICNS_OUT)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print("iconutil 失败:", r.stderr)
        return False
    print(f"图标已生成: {ICNS_OUT}")
    return True


def apply_to_app(app_path: str):
    """把 .icns 复制到 app 并用 SetFile 或直接放 Resources。"""
    res_dir = Path(app_path) / "Contents" / "Resources"
    res_dir.mkdir(exist_ok=True)
    dst = res_dir / "AppIcon.icns"
    shutil.copy(ICNS_OUT, dst)

    # 更新 Info.plist 引用图标文件
    plist = Path(app_path) / "Contents" / "Info.plist"
    content = plist.read_text(encoding="utf-8")
    if "CFBundleIconFile" not in content:
        content = content.replace(
            "<key>CFBundleDisplayName</key>",
            "<key>CFBundleIconFile</key>\n    <string>AppIcon</string>\n    <key>CFBundleDisplayName</key>",
        )
        plist.write_text(content, encoding="utf-8")

    # 重新签名
    subprocess.run(["codesign", "-s", "-", "--force", app_path],
                   capture_output=True)

    # 刷新 Finder 图标缓存
    subprocess.run(["touch", app_path], capture_output=True)
    subprocess.run(["killall", "Finder"], capture_output=True)
    print(f"图标已应用到: {app_path}")


if __name__ == "__main__":
    if build_icns():
        apply_to_app(str(Path.home() / "Desktop" / "抖音续火花.app"))
        print("\n✓ 完成！在 Finder 里重新打开桌面文件夹即可看到新图标。")
