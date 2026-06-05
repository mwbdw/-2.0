import json
import os
import random
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

DOUYIN_URL = "https://www.douyin.com"

_DEBUG_DIR = Path(os.environ.get("HUAHUO_DATA_DIR") or str(Path(__file__).parent)) / "debug"

_MSG_INPUT_SELECTOR = (
    '[contenteditable="true"], div[contenteditable], '
    '[data-e2e="message-input"], [data-e2e*="chat-input"], '
    '[data-e2e*="im-input"], textarea'
)

# 反检测：注入脚本，隐藏 headless / 自动化特征
_STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
if (!window.chrome) {
    window.chrome = {runtime: {}, loadTimes: () => {}, csi: () => {}, app: {}};
}
try {
    const _q = window.navigator.permissions.query.bind(navigator.permissions);
    window.navigator.permissions.query = (p) =>
        p.name === 'notifications'
            ? Promise.resolve({state: Notification.permission})
            : _q(p);
} catch(e) {}
Object.defineProperty(navigator, 'plugins', {get: () => [
    {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
    {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
    {name: 'Native Client', filename: 'internal-nacl-plugin'},
]});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
"""

_BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--disable-notifications",
    "--no-first-run",
    "--no-service-autorun",
    "--password-store=basic",
    "--use-mock-keychain",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
]

_CONTEXT_OPTS = dict(
    user_agent=(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    locale="zh-CN",
    timezone_id="Asia/Shanghai",
    viewport={"width": 1280, "height": 800},
    extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8"},
)

_log_cb = None


def _log(msg: str):
    print(msg)
    if _log_cb:
        try:
            _log_cb(msg)
        except Exception:
            pass


def set_log_callback(cb):
    global _log_cb
    _log_cb = cb


def check_login(cookies_path: Path) -> bool:
    if not cookies_path.exists():
        return False
    try:
        data = json.loads(cookies_path.read_text(encoding="utf-8"))
        return isinstance(data, list) and len(data) > 0
    except Exception:
        return False


def _save_cookies(context, cookies_path: Path):
    cookies = context.cookies()
    cookies_path.write_text(
        json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _log("[✓] Cookie 已保存")


def _load_cookies(context, cookies_path: Path) -> bool:
    if not cookies_path.exists():
        return False
    try:
        cookies = json.loads(cookies_path.read_text(encoding="utf-8"))
        context.add_cookies(cookies)
        return True
    except Exception:
        return False


def _is_logged_in(page) -> bool:
    try:
        _goto_home(page)
        url = page.url
        _log(f"  [~] 登录检测 URL: {url}")
        _screenshot(page, "login_check.png")
        # URL 含 passport/login 说明被重定向到登录页 → 未登录
        if "passport" in url or "login" in url:
            _log("  [!] URL 含 passport/login，判定未登录")
            return False
        # URL 正常（cookies 已加载且未跳转登录页）→ 视为已登录
        # 不检测「登录」按钮：弹窗/加载过渡期页面可能短暂出现该文字，导致误判
        _log("  [~] URL 正常，判定已登录")
        return True
    except Exception as e:
        _log(f"  [!] 登录检测异常: {e}")
        return False


def _register_popup_handler(page):
    """注册持久监听器：只要「保存登录信息」弹窗出现就自动点取消。此函数定稿不修改。"""
    def _handle():
        try:
            els = page.get_by_text('取消', exact=True).all()
            if els:
                box = els[-1].bounding_box()
                if box:
                    cx = box['x'] + box['width'] / 2
                    cy = box['y'] + box['height'] / 2
                    page.mouse.move(cx, cy)
                    page.wait_for_timeout(150)
                    page.mouse.click(cx, cy)
                    _log("  [~] 自动关闭「保存登录信息」弹窗")
        except Exception:
            pass
    try:
        page.add_locator_handler(page.locator('text=保存登录信息'), _handle)
    except Exception:
        pass  # 低版本 Playwright 不支持时静默降级


def _dismiss_popups(page):
    """处理「是否保存登录信息」及其他弹窗。此函数定稿，不再修改。"""
    # ── 专门针对「保存登录信息」弹窗 ──────────────────────────────────────
    # 最多重试 3 次，每次先检测弹窗是否存在，再用三种方式依次尝试点取消
    for _ in range(3):
        try:
            if not page.locator('text=保存登录信息').is_visible(timeout=1200):
                break  # 弹窗不存在，退出重试
            # 方式 1：Playwright mouse 坐标点击（最接近真人操作）
            els = page.get_by_text('取消', exact=True).all()
            if els:
                el = els[-1]  # 取最后一个（弹窗在 DOM 末尾）
                box = el.bounding_box()
                if box:
                    cx = box['x'] + box['width'] / 2
                    cy = box['y'] + box['height'] / 2
                    page.mouse.move(cx, cy)
                    page.wait_for_timeout(200)
                    page.mouse.click(cx, cy)
                    page.wait_for_timeout(800)
                    if not page.locator('text=保存登录信息').is_visible(timeout=500):
                        _log("  [~] 弹窗已关闭（mouse click）")
                        break
            # 方式 2：dispatchEvent bubbles=true（触发 React onClick）
            page.evaluate("""
                () => {
                    const all = [...document.querySelectorAll('*')].reverse();
                    for (const el of all) {
                        if (el.childElementCount === 0 &&
                            el.textContent.trim() === '取消') {
                            const r = el.getBoundingClientRect();
                            if (r.width > 0 && r.height > 0) {
                                el.dispatchEvent(new MouseEvent('mousedown',
                                    {bubbles:true, cancelable:true}));
                                el.dispatchEvent(new MouseEvent('mouseup',
                                    {bubbles:true, cancelable:true}));
                                el.dispatchEvent(new MouseEvent('click',
                                    {bubbles:true, cancelable:true}));
                                return;
                            }
                        }
                    }
                }
            """)
            page.wait_for_timeout(800)
            if not page.locator('text=保存登录信息').is_visible(timeout=500):
                _log("  [~] 弹窗已关闭（dispatchEvent）")
                break
            # 方式 3：Playwright force click
            page.get_by_text('取消', exact=True).last.click(force=True)
            page.wait_for_timeout(800)
        except Exception:
            page.wait_for_timeout(500)
    # ── 其他通用弹窗 ───────────────────────────────────────────────────────
    for sel in ['text=暂不', 'text=不保存', 'text=以后再说', '[aria-label="关闭"]']:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=600):
                el.click()
                page.wait_for_timeout(400)
        except Exception:
            pass


def _screenshot(page, name: str):
    try:
        _DEBUG_DIR.mkdir(exist_ok=True)
        page.screenshot(path=str(_DEBUG_DIR / name))
        _log(f"  [📷] 截图: debug/{name}")
    except Exception:
        pass


def _goto_home(page, screenshot_name: str = "before_dismiss.png"):
    page.goto(DOUYIN_URL, timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    _screenshot(page, screenshot_name)
    _dismiss_popups(page)
    try:
        page.locator('text=保存登录信息').wait_for(state='hidden', timeout=8000)
    except Exception:
        pass


def _send_message(page, friend_name: str, message: str) -> bool:
    try:
        context = page.context

        # 1. 首页 → 点左侧「我的」
        _goto_home(page, f"before_dismiss_{friend_name}.png")

        my_nav = page.locator('text=我的').first
        if not my_nav.is_visible(timeout=5000):
            _screenshot(page, f"fail_mynav_{friend_name}.png")
            _log("  [!] 找不到「我的」导航")
            return False
        my_nav.click()
        page.wait_for_timeout(2000)
        _dismiss_popups(page)

        # 2. 点「粉丝」— 先尝试 JS 点击，再尝试 URL 直跳
        clicked = page.evaluate("""
            () => {
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    if (el.childElementCount === 0 && el.textContent.trim() === '粉丝') {
                        el.click();
                        return true;
                    }
                }
                return false;
            }
        """)
        if not clicked:
            # 直接修改 URL 参数跳转粉丝页
            cur = page.url
            fans_url = cur.split('?')[0] + '?showTab=follower'
            page.goto(fans_url, timeout=15000)
        # 注意：此处不调用 _dismiss_popups，否则会点击粉丝弹窗的关闭按钮，导致弹窗关闭并跳转 404
        page.wait_for_timeout(3000)
        _screenshot(page, f"fans_page_{friend_name}.png")

        # 3. 搜索好友 — 优先在弹窗容器内找搜索框，再按 placeholder 关键字匹配
        pos = page.evaluate("""
            () => {
                // 第一优先：placeholder 含「用户名字」或「抖音号」（粉丝弹窗专属）
                const allInputs = document.querySelectorAll(
                    'input, [role="textbox"], [role="searchbox"]'
                );
                for (const el of allInputs) {
                    const ph = el.placeholder || el.getAttribute('placeholder') || '';
                    if (ph.includes('用户名字') || ph.includes('抖音号')) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 30 && r.height > 10)
                            return {x: r.x + r.width/2, y: r.y + r.height/2,
                                    tag: el.tagName, ph: ph};
                    }
                }
                // 第二优先：弹窗容器内的第一个 input
                const containers = document.querySelectorAll(
                    '[class*="dialog"],[class*="modal"],[class*="follow"],[class*="overlay"],[class*="popup"]'
                );
                for (const c of containers) {
                    const cr = c.getBoundingClientRect();
                    if (cr.width > 0 && cr.height > 0) {
                        const input = c.querySelector('input, [role="textbox"]');
                        if (input) {
                            const r = input.getBoundingClientRect();
                            if (r.width > 30 && r.height > 10)
                                return {x: r.x + r.width/2, y: r.y + r.height/2,
                                        tag: input.tagName,
                                        ph: input.placeholder || ''};
                        }
                    }
                }
                return null;
            }
        """)

        if not pos:
            _screenshot(page, f"fail_search_{friend_name}.png")
            _log("  [!] JS 找不到粉丝弹窗搜索框")
            return False

        _log(f"  [~] 找到搜索框: tag={pos['tag']} ph={pos['ph']} ({pos['x']:.0f},{pos['y']:.0f})")
        # 三击选全 → 直接键入，避免 Control/Meta+A 的系统差异
        page.mouse.click(pos['x'], pos['y'], click_count=3)
        page.wait_for_timeout(300)
        page.keyboard.type(friend_name)

        # 等待搜索结果加载：先等加载动画消失，再额外等渲染完成
        try:
            page.wait_for_function(
                """(name) => {
                    for (const el of document.querySelectorAll('*')) {
                        if (el.childElementCount === 0 &&
                            el.textContent.trim() === name &&
                            el.tagName !== 'INPUT' &&
                            !el.closest('input')) {
                            const r = el.getBoundingClientRect();
                            if (r.width > 0 && r.height > 0) return true;
                        }
                    }
                    return false;
                }""",
                arg=friend_name,
                timeout=8000,
            )
        except Exception:
            page.wait_for_timeout(3000)  # 降级：固定等待
        _screenshot(page, f"after_search_{friend_name}.png")

        # 4. 点击结果列表里的好友名字（排除搜索框内的同名文字）
        friend_pos = page.evaluate("""
            (name) => {
                for (const el of document.querySelectorAll('*')) {
                    if (el.childElementCount === 0 &&
                        el.textContent.trim() === name &&
                        el.tagName !== 'INPUT' &&
                        !el.closest('input')) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0)
                            return {x: r.x + r.width / 2, y: r.y + r.height / 2};
                    }
                }
                return null;
            }
        """, friend_name)

        if not friend_pos:
            _screenshot(page, f"fail_friend_{friend_name}.png")
            _log(f"  [!] 未找到好友「{friend_name}」的名字元素")
            return False

        _log(f"  [~] 点击好友名字坐标: ({friend_pos['x']:.0f}, {friend_pos['y']:.0f})")
        with context.expect_page() as new_page_info:
            page.mouse.click(friend_pos['x'], friend_pos['y'])
        profile_page = new_page_info.value
        profile_page.wait_for_load_state("domcontentloaded")
        # 静默等待 10 秒，让好友主页完全渲染
        _log("  [~] 等待好友主页渲染（10 秒）...")
        profile_page.wait_for_timeout(10000)
        _dismiss_popups(profile_page)
        profile_url = profile_page.url
        _log(f"  [~] 好友主页: {profile_url}")
        _screenshot(profile_page, f"profile_{friend_name}.png")

        # 5. 点击「私信」按钮一次（y ≥ 50px 排除 header 图标）
        dm_btn_box = None
        try:
            for el in profile_page.locator('text=私信').all():
                box = el.bounding_box()
                if box and box['y'] >= 50:
                    dm_btn_box = box
                    _log(f"  [~] 私信按钮坐标: ({box['x']:.0f}, {box['y']:.0f})")
                    break
        except Exception as e:
            _log(f"  [~] 查找私信按钮异常: {e}")

        if not dm_btn_box:
            _screenshot(profile_page, f"fail_dmbtn_{friend_name}.png")
            _log("  [!] 找不到私信按钮")
            profile_page.close()
            return False

        cx = dm_btn_box['x'] + dm_btn_box['width'] / 2
        cy = dm_btn_box['y'] + dm_btn_box['height'] / 2
        profile_page.mouse.move(cx, cy)
        profile_page.wait_for_timeout(300)

        # 点击一次，判断是新标签还是内联弹窗
        dm_page = profile_page
        try:
            with context.expect_page(timeout=4000) as p:
                profile_page.mouse.click(cx, cy)
            dm_page = p.value
            dm_page.wait_for_load_state("domcontentloaded")
            _log("  [~] 私信窗口在新标签打开")
        except Exception:
            profile_page.wait_for_timeout(3000)
            dm_page = profile_page
            _log("  [~] 私信窗口为内联弹窗，在当前页查找输入框")

        _screenshot(dm_page, f"after_dm_click_{friend_name}.png")

        # 6. 输入消息并发送
        msg_input = None
        try:
            el = dm_page.locator(_MSG_INPUT_SELECTOR).last
            if el.is_visible(timeout=5000):
                msg_input = el
        except Exception:
            pass

        if not msg_input:
            _screenshot(dm_page, f"fail_input_{friend_name}.png")
            _log("  [!] 找不到消息输入框")
            dm_page.close()
            if dm_page is not profile_page:
                profile_page.close()
            return False

        # 点击聚焦，清空旧内容，用键盘逐字输入（对 contenteditable 更可靠）
        msg_input.click()
        dm_page.wait_for_timeout(300)
        # 全选清空
        dm_page.keyboard.press("Meta+a")
        dm_page.keyboard.press("Backspace")
        dm_page.wait_for_timeout(200)
        # 逐字输入
        dm_page.keyboard.type(message, delay=50)
        dm_page.wait_for_timeout(500)
        # 发送
        dm_page.keyboard.press("Enter")
        dm_page.wait_for_timeout(1000)
        _screenshot(dm_page, f"after_send_{friend_name}.png")

        _log(f"  [✓] 已发送给 {friend_name}: {message}")
        dm_page.close()
        if dm_page is not profile_page:
            profile_page.close()
        return True
    except Exception as e:
        _log(f"  [✗] 发送给 {friend_name} 失败: {e}")
        return False


def _wait_for_login(page, timeout_ms: int = 180000) -> bool:
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        try:
            url = page.url
            if "passport" not in url and "login" not in url:
                if not page.locator('text=登录').first.is_visible(timeout=1000):
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def do_login(cookies_path: Path):
    _log("[!] 正在打开浏览器，请稍候…")
    try:
        _do_login_inner(cookies_path)
    except Exception as e:
        _log(f"[✗] 登录出错: {e}")
        import traceback
        _log(traceback.format_exc())


def _do_login_inner(cookies_path: Path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=_BROWSER_ARGS)
        context = browser.new_context(**_CONTEXT_OPTS)
        page = context.new_page()
        page.add_init_script(_STEALTH_SCRIPT)
        page.goto(DOUYIN_URL)
        _log("[~] 浏览器已打开，请完成登录和验证，完成后会自动保存")

        if _wait_for_login(page, timeout_ms=300000):
            _log("[✓] 检测到已登录，正在保存 Cookie…")
            page.wait_for_timeout(2000)
            _save_cookies(context, cookies_path)
        else:
            _log("[✗] 等待超时（5 分钟），请重试")
        browser.close()


def run_task(config: dict, cookies_path: Path):
    friends = config.get("friends", [])
    messages = config.get("messages", ["嗨！"])
    headless = config.get("headless", False)

    _log(f"\n[→] 开始续火花任务，共 {len(friends)} 位好友")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=_BROWSER_ARGS)
        context = browser.new_context(**_CONTEXT_OPTS)
        page = context.new_page()
        page.add_init_script(_STEALTH_SCRIPT)
        _register_popup_handler(page)

        if _load_cookies(context, cookies_path):
            _log("[✓] Cookie 已加载，验证登录状态...")

        if not _is_logged_in(page):
            _log("[✗] 未登录，请先点「登录」按钮扫码")
            browser.close()
            return

        ok = fail = 0
        for friend in friends:
            msg = random.choice(messages)
            _log(f"[→] 正在给 {friend} 发消息...")
            if _send_message(page, friend, msg):
                ok += 1
            else:
                fail += 1
            delay = random.uniform(3, 8)
            _log(f"  [~] 等待 {delay:.1f}s...")
            time.sleep(delay)

        _save_cookies(context, cookies_path)
        browser.close()
        _log(f"[✓] 任务完成  成功 {ok} · 失败 {fail} · 共 {len(friends)} 位\n")
