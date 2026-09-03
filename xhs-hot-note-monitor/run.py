"""
小红书热门笔记抓取 — 一键执行入口

用法：
    python run.py                          # 用 references/keywords.json 里的关键词
    python run.py 黄金项链 银饰耳环        # 命令行指定关键词
    python run.py --headless 黄金项链      # 无头模式（已登录时无打扰跑，首次扫码请用有头）
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))

from login import ensure_login
from search import search_keyword, save_items, load_keywords
from fix_images import download_images
from gen_dashboard import gen_dashboard

DATA_DIR = ROOT / "xhs-baseline"


def main():
    args = sys.argv[1:]
    headless = "--headless" in args
    keywords = [a for a in args if not a.startswith("-")] or load_keywords()
    if not keywords:
        print("[run] 没有关键词：请在 references/keywords.json 配置，或命令行传入")
        return

    print(f"[run] 本次关键词：{keywords}（headless={headless}）")
    img_dir = DATA_DIR / "images"
    pw, context, page = ensure_login(headless=headless)
    try:
        for kw in keywords:
            try:
                items = search_keyword(page, kw)
                # 搜索页仍开着，复用同一 page 立即抓封面图（避免 CDN 签名过期）
                download_images(page, items, kw, img_dir)
                # 抓图后再保存，JSON 里带上 local_image 字段
                save_items(items, kw, DATA_DIR)
            except Exception as e:
                print(f"[run] 关键词「{kw}」失败：{e}")
    finally:
        context.close()
        pw.stop()

    gen_dashboard(DATA_DIR)
    print("[run] 全部完成")


if __name__ == "__main__":
    main()
