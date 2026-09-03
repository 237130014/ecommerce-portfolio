"""
小红书登录模块：扫码登录 + Cookie 持久化 + 登录态校验

登录弹窗会自动弹出，二维码以 base64 形式渲染在 .qrcode-img 里。
本模块会把二维码落盘成 login_qr.png，并每 2 秒刷新一次（保证扫描的始终是最新二维码），
同时保持浏览器窗口打开，检测到登录成功后自动保存登录态。

用法：
    from login import ensure_login
    pw, context, page = ensure_login()   # 有头模式，弹窗扫码
"""
import base64
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = ROOT / ".browser_profile"   # 登录态持久化目录（不提交，Cookie 存这里）
QR_PNG = ROOT / "login_qr.png"            # 二维码落盘路径

HOME_URL = "https://www.xiaohongshu.com"
EXPLORE_URL = "https://www.xiaohongshu.com/explore"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def launch_context(headless: bool = False, profile_dir: Path = PROFILE_DIR):
    """启动持久化浏览器上下文，登录态自动保存到 profile_dir。"""
    profile_dir.mkdir(parents=True, exist_ok=True)
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=headless,
        viewport={"width": 1280, "height": 800},
        user_agent=UA,
        args=["--disable-blink-features=AutomationControlled"],
    )
    return pw, context


def is_logged_in(page) -> bool:
    """校验是否已登录：未登录时页面存在 .login-btn 登录入口，已登录则消失。"""
    try:
        return page.locator(".login-btn").count() == 0
    except Exception:
        return False


def _extract_qr_base64(page) -> str | None:
    """从登录弹窗抓取二维码 base64（不含 data: 前缀）。"""
    try:
        data = page.evaluate(
            """() => {
                const el = document.querySelector('img.qrcode-img');
                if (!el) return null;
                const src = el.src || '';
                const m = src.match(/^data:image\\/png;base64,(.+)$/);
                return m ? m[1] : (src.startsWith('data:') ? src.split(',')[1] : null);
            }"""
        )
        return data
    except Exception:
        return None


def save_qr(page) -> bool:
    """抓取二维码并落盘，返回是否成功。"""
    b64 = _extract_qr_base64(page)
    if not b64:
        return False
    try:
        QR_PNG.write_bytes(base64.b64decode(b64))
        return True
    except Exception:
        return False


def ensure_login(headless: bool = False, timeout: int = 300):
    """确保已登录；未登录则弹窗引导扫码。返回 (pw, context, page)。"""
    pw, context = launch_context(headless=headless)
    page = context.new_page()
    page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    if is_logged_in(page):
        print("[login] 已登录，复用本地登录态")
        return pw, context, page

    if headless:
        print("[login] 无头模式无法扫码，请改用有头模式：python scripts/login.py")
        raise RuntimeError("无头模式无法扫码登录")

    print("[login] 未登录 —— 登录弹窗已自动弹出，二维码已保存到 login_qr.png")
    print("[login] 请用小红书 App 扫描 login_qr.png（或弹出的浏览器窗口里的二维码）")
    page.goto(EXPLORE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2500)

    # 若弹窗未自动弹出，尝试点击登录按钮（忽略遮罩拦截）
    if page.locator("img.qrcode-img").count() == 0 and page.locator(".login-btn").count() > 0:
        try:
            page.locator(".login-btn").first.click(force=True)
            page.wait_for_timeout(1500)
        except Exception:
            pass

    start = time.time()
    last_qr_save = 0.0
    saved_any = False
    while time.time() - start < timeout:
        # 每 2 秒刷新一次二维码落盘
        if time.time() - last_qr_save >= 2.0:
            if save_qr(page):
                saved_any = True
            last_qr_save = time.time()

        if is_logged_in(page):
            print("[login] 登录成功，登录态已保存到 .browser_profile/")
            return pw, context, page

        page.wait_for_timeout(1000)
        elapsed = int(time.time() - start)
        if elapsed > 0 and elapsed % 20 == 0:
            print(f"[login] 等待扫码中...（已等待 {elapsed} 秒）")

    if not saved_any:
        raise RuntimeError("未能获取二维码，登录超时")
    raise RuntimeError("登录超时，请重新运行")


if __name__ == "__main__":
    pw, context, page = ensure_login(headless=False)
    print("当前登录态有效。")
    context.close()
    pw.stop()
