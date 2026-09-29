#!/usr/bin/env python3
"""京东前台登录：扫码登录一次，登录态持久化复用。

为什么必须登录：
    实测（2026-09-29）无登录态访问 item.jd.com 会被直接跳转到
    https://pc-frequent-pro.pf.jd.com/?from=pc_item&reason=403 （PC频控页），
    主图/标题/价格全部拿不到。登录态是绕开频控的正道。

    而京东首页对自动化浏览器会返回降级页（只剩搜索框和页脚，
    顶栏登录入口 #ttbar-login 完全不渲染），导致点不出二维码。
    所以还要做反自动化指纹注入。

注意：这里要的是【京东前台消费者账号】（京东 App 可扫），
      与 jd-data-hub 的商智账号（sz.jd.com 商家子账号）不是一套体系。

用法（复用 jd-shop-audit 的 venv）:
    <venv>/Scripts/python.exe login.py            # 弹二维码，手机扫
    <venv>/Scripts/python.exe login.py --check    # 只检查登录态是否还有效

产物:
    auth/state.json    Playwright storage_state（含 localStorage），抓取时直接复用
    auth/cookies.txt   Cookie 字符串，便于人工查看/迁移
    logs/login_step*.png  调试截图
"""
import argparse
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parent
AUTH_DIR = BASE / "auth"
STATE_FILE = AUTH_DIR / "state.json"
COOKIE_FILE = AUTH_DIR / "cookies.txt"
DEBUG_DIR = BASE / "logs"

# 京东前台登录态关键 Cookie（任一命中即视为已登录）
LOGIN_KEYS = ("pt_key", "pt_pin", "pt_token", "pin", "thor", "unick", "pwdt_id")

CHECK_URL = "https://item.jd.com/100312606664.html"
RISK_HOST = "pc-frequent-pro.pf.jd.com"
LOGIN_HOST_MARK = "passport.jd.com"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 反自动化检测脚本：抹掉 Playwright/CDP 暴露的机器人特征
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
try { delete Object.getPrototypeOf(navigator).webdriver; } catch (e) {}

Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });

if (!window.chrome) { window.chrome = {}; }
if (!window.chrome.runtime) { window.chrome.runtime = {}; }

try {
  const origQuery = window.navigator.permissions && window.navigator.permissions.query;
  if (origQuery) {
    window.navigator.permissions.query = (params) => (
      params && params.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : origQuery(params)
    );
  }
} catch (e) {}

try {
  const getParam = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function (p) {
    if (p === 37445) return 'Intel Inc.';
    if (p === 37446) return 'Intel Iris OpenGL Engine';
    return getParam.apply(this, [p]);
  };
} catch (e) {}
"""


def is_logged_in(cookies) -> bool:
    names = {c["name"].lower() for c in cookies}
    return any(k in names for k in LOGIN_KEYS)


def launch(p, headless=False, use_channel=True):
    """启动浏览器。use_channel=True 优先用系统真实 Chrome（指纹更干净）。"""
    args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-infobars",
        "--disable-dev-shm-usage",
        "--start-maximized" if not headless else "--window-size=1440,900",
    ]
    if use_channel:
        try:
            return p.chromium.launch(headless=headless, channel="chrome", args=args)
        except Exception as e:
            print(f"[提示] 系统 Chrome 启动失败（{type(e).__name__}），改用内置 Chromium")
    return p.chromium.launch(headless=headless, args=args)


def build_context(browser, storage_state=None):
    kwargs = dict(
        user_agent=USER_AGENT,
        viewport={"width": 1440, "height": 900},
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        extra_http_headers={
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "sec-ch-ua": '"Chromium";v="131", "Not_A Brand";v="24", "Google Chrome";v="131"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        },
    )
    if storage_state:
        kwargs["storage_state"] = str(storage_state)
    ctx = browser.new_context(**kwargs)
    ctx.add_init_script(STEALTH_JS)
    return ctx


def save_state(ctx):
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    ctx.storage_state(path=str(STATE_FILE))
    cookies = ctx.cookies()
    parts = [f"{c['name']}={c['value']}" for c in cookies if c.get("value")]
    COOKIE_FILE.write_text("; ".join(parts), encoding="utf-8")
    return len(parts)


def open_login_panel(page) -> bool:
    """尝试点出登录面板；找不到入口就直跳登录页。"""
    candidates = [
        "#ttbar-login .link-login",
        "a.link-login",
        ".link-user",
        "#ttbar-login a",
        "a[href*='passport.jd.com']",
    ]
    for sel in candidates:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                print(f"[信息] 已点击登录入口：{sel}")
                return True
        except Exception:
            continue
    print("[信息] 未找到顶栏登录入口，直接跳转登录页")
    page.goto(
        "https://passport.jd.com/new/login.aspx",
        wait_until="domcontentloaded",
        timeout=60000,
    )
    return True


def do_check(headless=True) -> int:
    if not STATE_FILE.exists():
        print(f"[未登录] 找不到 {STATE_FILE}，请先运行 login.py")
        return 2
    with sync_playwright() as p:
        browser = launch(p, headless=headless, use_channel=False)
        ctx = build_context(browser, storage_state=STATE_FILE)
        page = ctx.new_page()
        try:
            page.goto(CHECK_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4000)
            url, title = page.url, page.title()
        except Exception as e:
            print(f"[异常] 校验失败：{e!r}")
            browser.close()
            return 3
        browser.close()

    if RISK_HOST in url:
        print(f"[失效] 被频控拦截：{url}")
        print("       登录态已过期或不适用，请重新运行 login.py 扫码")
        return 1
    if LOGIN_HOST_MARK in url:
        print(f"[失效] 跳转登录页：{url}")
        return 1
    print(f"[有效] 登录态正常，页面标题：{title}")
    return 0


def do_login():
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 64)
    print("  京东前台登录（扫码）— 登录态将保存并复用")
    print("=" * 64)
    print()
    print("即将打开浏览器：")
    print("  1. 用【京东 App】扫码登录（普通消费者账号即可）")
    print("  2. 登录后停留在京东首页即可，程序自动检测")
    print("  3. 检测到登录态后自动保存")
    print()

    with sync_playwright() as p:
        try:
            browser = launch(p, headless=False, use_channel=True)
        except Exception as e:
            print(f"[错误] 浏览器启动失败：{e}")
            print("  <venv>/Scripts/python.exe -m playwright install chromium")
            return 1

        ctx = build_context(browser)
        page = ctx.new_page()

        print("[1/3] 打开京东首页...")
        page.goto("https://www.jd.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        page.screenshot(path=str(DEBUG_DIR / "login_step1_home.png"))
        body_len = len(page.evaluate("document.body ? document.body.innerText : ''"))
        print(f"      首页正文长度：{body_len} 字符（正常应 >1500）")
        if body_len < 1500:
            print("      [警告] 首页疑似降级渲染，登录入口可能不可见")

        print("[2/3] 尝试打开登录面板...")
        open_login_panel(page)
        page.wait_for_timeout(4000)
        page.screenshot(path=str(DEBUG_DIR / "login_step2_panel.png"))
        print(f"      当前地址：{page.url}")

        print("[3/3] 等待扫码登录中...（最多 5 分钟）")
        deadline = time.time() + 300
        cookies = []
        while time.time() < deadline:
            time.sleep(2)
            try:
                cookies = ctx.cookies()
                cur_url = page.url or ""
            except Exception:
                continue
            if is_logged_in(cookies) and LOGIN_HOST_MARK not in cur_url:
                break

        if not is_logged_in(cookies):
            print()
            print("[失败] 未检测到登录成功，登录态未保存。")
            print(f"       调试截图：{DEBUG_DIR / 'login_step2_panel.png'}")
            print("       若截图里没有二维码，把截图发我，我继续调反检测。")
            input("按回车键关闭浏览器...")
            browser.close()
            return 1

        try:
            page.reload(wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
        except Exception:
            pass

        n = save_state(ctx)
        print()
        print(f"[成功] 已保存 {n} 个 Cookie")
        print(f"        {STATE_FILE}   （抓取时复用）")
        print(f"        {COOKIE_FILE}  （Cookie 字符串）")

        print()
        print("正在验证登录态能否访问商品详情页...")
        try:
            page2 = ctx.new_page()
            page2.goto(CHECK_URL, wait_until="domcontentloaded", timeout=60000)
            page2.wait_for_timeout(5000)
            final_url = page2.url
            if RISK_HOST in final_url:
                print(f"  [警告] 仍被频控：{final_url}")
                print("         该账号可能受限，或登录态未被前台认可。")
            else:
                print(f"  最终地址：{final_url}")
                print(f"  页面标题：{page2.title()}")
                print("  [正常] 登录态可用于商品页访问")
            page2.close()
        except Exception as e:
            print(f"  验证请求失败：{e}")

        print()
        print("登录完成。下一步在 bat 菜单里选 3 跑探针。")
        print()
        input("按回车键关闭浏览器...")
        browser.close()

    return 0


def main():
    ap = argparse.ArgumentParser(description="京东前台登录（扫码 + 登录态持久化）")
    ap.add_argument("--check", action="store_true", help="只校验已保存的登录态是否有效")
    args = ap.parse_args()
    return do_check() if args.check else do_login()


if __name__ == "__main__":
    sys.exit(main())
