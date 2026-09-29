#!/usr/bin/env python3
"""京东SKU主图抓取 · 探针脚本（probe）

目的：全量抓取前，用少量测试SKU验证——
  1) 匿名访问 item.jd.com/{sku}.html 能否拿到第一主图 / 标题 / 价格
  2) 第一主图最稳的提取锚点（og:image 或 轮播图选择器）
  3) 是否触发登录墙 / 滑块等风控信号

用法:
  python probe.py --sku 100012043978 10098765432
  （用你项目自己的 Python 环境；依赖 playwright）
可选:
  --headless   无头模式（默认有头，便于人工观察是否弹滑块）
  --base DIR   产物根目录（默认脚本所在目录）

产物（logs/probe/{sku}/）:
  snapshot.html    整页HTML快照（供回填选择器分析）
  screenshot.png   首屏截图
  extract.json     结构化提取结果 + 风控信号
"""
import argparse
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parent

# 候选选择器（探针会逐个试，命中哪个全记下来，供全量脚本回填）
SEL_TITLE = [".sku-name", ".itemInfo-wrap .sku-name", ".product-title", "h1"]
SEL_IMAGE = [
    "#spec-list img",
    ".product-imgs img",
    "#J-detail-content img",
    '[class*="spec"] img',
    '[id*="spec"] img',
]
SEL_PRICE = [".p-price .price", ".p-price", "#jd-price", ".price", '[class*="price"]']


def norm_path(p: str) -> str:
    """兼容 Git Bash 风格 /c/... → C:/..."""
    if re.match(r"^/[a-zA-Z]/", p):
        return p[1].upper() + ":" + p[2:]
    return p


# 京东榜单导出表格的列名（表头识别用，兼容商家/商智两套叫法）
HEADER_ALIASES = {
    "sku": ["SKU ID", "SKU", "skuId", "商品ID", "商品编号"],
    "title": ["商品名称", "商品标题", "名称"],
    "shop": ["店铺名称", "店铺"],
    "rank": ["排名"],
}


def _col_index(header_row, aliases):
    """在表头行里找到列下标（0-based）；找不到返回 None"""
    for j, cell in enumerate(header_row):
        text = (cell or "").strip() if isinstance(cell, str) else ""
        for a in aliases:
            if text == a or (a in text and a in {"SKU ID", "SKU"}):
                return j
    return None


def read_skus_from_xlsx(path: str):
    """从京东榜单导出 xlsx 读取 SKU 列。

    注意：京东导出的 xlsx 常把 <dimension ref="A1"/> 写坏（只声明 A1），
    openpyxl 会因此只读到 A 列。故此处直接解析 sheet1.xml 原始 XML，
    不依赖 dimension 声明，也不依赖 sharedStrings（导出用的是 inlineStr）。
    """
    import zipfile
    from xml.etree import ElementTree as ET

    NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    z = zipfile.ZipFile(path)
    sheet_name = "xl/worksheets/sheet1.xml"
    root = ET.fromstring(z.read(sheet_name))
    z.close()

    def col_letters(ref):
        return re.match(r"^([A-Z]+)", ref).group(1)

    def col_to_idx(letters):
        n = 0
        for ch in letters:
            n = n * 26 + (ord(ch) - ord("A") + 1)
        return n - 1

    def cell_text(c):
        t = c.get("t")
        if t == "inlineStr":
            is_el = c.find(f"{NS}is")
            if is_el is None:
                return ""
            parts = [it.text or "" for it in is_el.iter(f"{NS}t")]
            return "".join(parts)
        v = c.find(f"{NS}v")
        return (v.text or "") if v is not None else ""

    rows = []
    for row in root.iter(f"{NS}row"):
        cells = {}
        for c in row.findall(f"{NS}c"):
            ref = c.get("r") or ""
            m = re.match(r"^([A-Z]+)\d+$", ref)
            if not m:
                continue
            cells[col_to_idx(m.group(1))] = cell_text(c)
        width = (max(cells) + 1) if cells else 0
        rows.append([cells.get(i, "") for i in range(width)])
    if not rows:
        return []

    header = rows[0]
    sku_idx = _col_index(header, HEADER_ALIASES["sku"])
    if sku_idx is None:
        # 兜底：全表扫描，找一列几乎全是纯数字的
        ncols = max(len(r) for r in rows[1:]) if len(rows) > 1 else 0
        best, best_hit = None, 0
        for j in range(ncols):
            hit = sum(
                1
                for r in rows[1:]
                if j < len(r) and str(r[j]).strip().split(".")[0].isdigit()
                and len(str(r[j]).strip()) >= 7
            )
            if hit > best_hit:
                best, best_hit = j, hit
        sku_idx = best
    if sku_idx is None:
        return []

    out, seen = [], set()
    for r in rows[1:]:
        if sku_idx >= len(r):
            continue
        s = str(r[sku_idx]).strip().split(".")[0].replace(",", "")
        if s.isdigit() and len(s) >= 6 and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def collect(page, sels, limit=5, attr_mode=False):
    """逐个选择器尝试提取，记录命中情况"""
    found = []
    for sel in sels:
        try:
            els = page.query_selector_all(sel)
            vals = []
            for el in els[:limit]:
                if attr_mode:
                    v = el.get_attribute("src") or el.get_attribute("data-origin") or ""
                    v = v.strip()
                else:
                    v = (el.inner_text() or "").strip()[:100]
                if v:
                    vals.append(v)
            if vals:
                found.append({"selector": sel, "hits": vals})
        except Exception:
            continue
    return found


def probe_one(page, sku: str, probe_root: Path) -> dict:
    result = {"sku": sku, "ok": False, "signals": [], "extract": {}}
    url = f"https://item.jd.com/{sku}.html"
    out_dir = probe_root / sku
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
        result["http_status"] = resp.status if resp else None
        page.wait_for_timeout(4000)  # 等价格/主图异步渲染
        final_url = page.url
        result["final_url"] = final_url

        # ---- 风控 / 登录墙信号 ----
        if "passport.jd.com" in final_url:
            result["signals"].append("redirect_passport_login")
        body = page.evaluate(
            "document.body ? document.body.innerText.slice(0, 3000) : ''"
        )
        for kw, sig in [
            ("登录后可见", "price_needs_login"),
            ("请登录", "login_wall_text"),
            ("访问过于频繁", "rate_limit"),
            ("安全验证", "captcha_text"),
        ]:
            if kw in body:
                result["signals"].append(sig)

        # ---- 结构化提取 ----
        ex = {"page_title": page.title()}
        og = page.evaluate(
            """() => {
                const m = document.querySelector('meta[property="og:image"]');
                return m ? m.content : null;
            }"""
        )
        ex["og_image"] = og
        ex["title_hits"] = collect(page, SEL_TITLE)
        ex["image_hits"] = collect(page, SEL_IMAGE, attr_mode=True)
        ex["price_hits"] = collect(page, SEL_PRICE)
        result["extract"] = ex
        result["ok"] = True
    except Exception as e:
        result["error"] = repr(e)

    # ---- 落盘 ----
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        if result["ok"]:
            (out_dir / "snapshot.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
    try:
        page.screenshot(path=str(out_dir / "screenshot.png"), full_page=False)
    except Exception:
        pass
    (out_dir / "extract.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def main():
    ap = argparse.ArgumentParser(description="京东SKU主图抓取·探针")
    ap.add_argument("--sku", nargs="+", help="2~3个测试SKU（纯数字）")
    ap.add_argument("--from-xlsx", default=None, help="从京东榜单导出xlsx的E列SKU ID首行取测试SKU（需 openpyxl）")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--base", default=None, help="产物根目录")
    args = ap.parse_args()

    skus = list(args.sku or [])
    if args.from_xlsx:
        try:
            found = read_skus_from_xlsx(norm_path(args.from_xlsx))
            if found:
                step = max(1, len(found) // 2)
                skus = [found[0], found[len(found) // 2], found[-1]]
                print(f"从xlsx取到 {len(found)} 个SKU，抽样测试: {skus}", flush=True)
            else:
                print("未能从xlsx解析出SKU", flush=True)
        except Exception as e:
            print(f"解析xlsx失败: {e!r}", flush=True)

    if not skus:
        print("请提供测试SKU：--sku <数字> 或 --from-xlsx <路径>", file=sys.stderr)
        return 2
    args.sku = skus

    probe_root = Path(norm_path(args.base)) / "logs" / "probe" if args.base else BASE / "logs" / "probe"
    probe_root.mkdir(parents=True, exist_ok=True)

    summary = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
        )
        page = ctx.new_page()
        for i, sku in enumerate(args.sku):
            sku = str(sku).strip()
            if not sku.isdigit():
                print(f"[{i + 1}/{len(args.sku)}] sku={sku} 跳过：非纯数字", flush=True)
                continue
            r = probe_one(page, sku, probe_root)
            summary.append(r)
            print(
                f"[{i + 1}/{len(args.sku)}] sku={sku} ok={r['ok']} "
                f"signals={r['signals'] or '无'} "
                f"og_image={'有' if r['extract'].get('og_image') else '无'}",
                flush=True,
            )
            if i < len(args.sku) - 1:
                page.wait_for_timeout(4000)
        browser.close()

    (probe_root / "probe_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n探针完成，产物在: {probe_root}")
    print("把 probe_summary.json / extract.json 交回分析，回填全量脚本选择器。")


if __name__ == "__main__":
    sys.exit(main())
