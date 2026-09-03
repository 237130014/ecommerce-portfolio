"""
封面图下载模块：浏览器原生抓图（goto https 图片 URL → 元素截图）

为什么不用 context.request / urllib：
    封面 CDN 是 http:// 链接，走系统代理会 connect ETIMEDOUT（198.18.0.x fake-ip），
    而 https + 浏览器网络栈能正常加载（和搜索页 <img> 加载同一套网络）。
    所以用 page.goto 直接导航到图片 URL，再对 <img> 元素截图，最稳。

用法（独立）：
    python scripts/fix_images.py [数据目录]

用法（被 run.py 复用 page）：
    from fix_images import download_images
    download_images(page, items, "黄金项链", img_dir)
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "xhs-baseline"
PROFILE_DIR = ROOT / ".browser_profile"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def normalize_image_url(url: str) -> str:
    """规整封面 URL：http→https。保留 ! 后缀（webp 中等尺寸，够看板用）。"""
    if not url:
        return url
    url = url.strip()
    if url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    return url


def _fetch_one(page, url: str, out: Path) -> bool:
    """导航到图片 URL，等图片渲染，元素截图落盘。返回是否成功。"""
    try:
        page.goto(url, wait_until="commit", timeout=30000)
        # 等图片真实加载（naturalWidth > 0），最多约 6 秒
        for _ in range(12):
            try:
                w = page.evaluate(
                    "() => { const i = document.querySelector('img');"
                    " return i ? i.naturalWidth : 0; }")
                if w and w > 0:
                    break
            except Exception:
                pass
            page.wait_for_timeout(500)
        img = page.locator("img").first
        img.screenshot(path=str(out))
        return out.exists() and out.stat().st_size > 0
    except Exception as e:
        print(f"  [img] 抓图失败 {url[:60]}：{str(e)[:120]}")
        return False


def download_images(page, items, keyword: str, img_dir: Path) -> int:
    """用给定 page 逐张抓封面图，写回 items 的 local_image 字段。返回成功数。"""
    img_dir.mkdir(parents=True, exist_ok=True)
    safe_kw = keyword.replace("/", "_").replace("\\", "_")
    ok = 0
    seen = {}  # url -> local_path（重复封面复用已下载图）
    idx = 0
    for it in items:
        url = normalize_image_url(it.get("cover", ""))
        if not url:
            continue
        if url in seen:
            it["local_image"] = seen[url]
            ok += 1
            continue
        idx += 1
        tag = (it.get("note_id") or "")[:10] or f"{idx:03d}"
        local = img_dir / f"{safe_kw}_{tag}.jpg"
        if local.exists() and local.stat().st_size > 0:
            it["local_image"] = local.relative_to(img_dir.parent).as_posix()
            seen[url] = it["local_image"]
            ok += 1
            continue
        if _fetch_one(page, url, local):
            it["local_image"] = local.relative_to(img_dir.parent).as_posix()
            seen[url] = it["local_image"]
            ok += 1
    print(f"[img] 「{keyword}」封面图：成功 {ok} / 共 {idx}")
    return ok


def process_files(base: Path):
    """独立模式：重新起浏览器，从 notes_*.json 读数据抓图并写回。"""
    img_dir = base / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=True,
        viewport={"width": 1280, "height": 800},
        user_agent=UA,
        args=["--disable-blink-features=AutomationControlled"],
    )
    page = context.pages[0] if context.pages else context.new_page()
    try:
        for jf in sorted(base.glob("notes_*.json")):
            data = json.loads(jf.read_text(encoding="utf-8"))
            keyword = data.get("keyword", jf.stem.replace("notes_", ""))
            items = data.get("items", [])
            print(f"[img] 处理「{keyword}」：{len(items)} 条")
            download_images(page, items, keyword, img_dir)
            jf.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        context.close()
        pw.stop()


if __name__ == "__main__":
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_DIR
    process_files(base)
