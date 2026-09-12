"""
小红书热门笔记抓取 — 一键执行入口

用法：
    python run.py                          # 用 references/keywords.json 里的关键词
    python run.py 黄金项链 银饰耳环        # 命令行指定关键词
    python run.py --headless 黄金项链      # 无头模式（已登录时无打扰跑，首次扫码请用有头）

产物组织：每次跑在本轮开始时创建一个 xhs-baseline/<日期_时分>/ 子目录，
该目录里存放本轮的 notes_*.json、热门笔记明细.csv、小红书热门笔记-*.html、images/。
不同轮次互不覆盖，可按目录回看历史抓取结果。
"""
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))

from login import ensure_login
from search import search_keyword, save_items, load_keywords
from fix_images import download_images
from gen_dashboard import gen_dashboard

DATA_DIR = ROOT / "xhs-baseline"


def make_run_dir() -> Path:
    """为本轮抓取建一个独立子目录：xhs-baseline/<YYYY-MM-DD_HHMM>/"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    run_dir = DATA_DIR / stamp
    # 同分钟内多次跑（极少发生）追加秒级后缀
    suffix = 0
    while run_dir.exists() and any(run_dir.iterdir()):
        suffix += 1
        run_dir = DATA_DIR / f"{stamp}_{suffix:02d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def main():
    args = sys.argv[1:]
    headless = "--headless" in args
    keywords = [a for a in args if not a.startswith("-")] or load_keywords()
    if not keywords:
        print("[run] 没有关键词：请在 references/keywords.json 配置，或命令行传入")
        return

    run_dir = make_run_dir()
    img_dir = run_dir / "images"
    print(f"[run] 本次关键词：{keywords}（headless={headless}）")
    print(f"[run] 本轮产出目录：{run_dir.relative_to(ROOT)}")

    pw, context, page = ensure_login(headless=headless)
    try:
        for kw in keywords:
            try:
                items = search_keyword(page, kw)
                # 搜索页仍开着，复用同一 page 立即抓封面图（避免 CDN 签名过期）
                download_images(page, items, kw, img_dir)
                # 抓图后再保存，JSON 里带上 local_image 字段
                save_items(items, kw, run_dir)
            except Exception as e:
                print(f"[run] 关键词「{kw}」失败：{e}")
    finally:
        context.close()
        pw.stop()

    gen_dashboard(run_dir)
    print("[run] 全部完成")

    # 自动用默认浏览器打开看板（非技术同事跑完直接看到结果）
    try:
        import webbrowser
        latest = sorted(run_dir.glob("小红书热门笔记-*.html"))
        if latest:
            webbrowser.open(latest[-1].resolve().as_uri())
            print(f"[run] 已自动打开看板：{latest[-1].name}")
    except Exception:
        pass


if __name__ == "__main__":
    main()
