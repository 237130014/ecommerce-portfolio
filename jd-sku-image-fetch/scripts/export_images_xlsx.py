#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 report.csv 导出成带嵌入图片的 xlsx。

设计要点
--------
1. CSV 是纯文本格式，单元格里塞不下图片，所以必须转成 xlsx。
2. 京东主图是 AVIF 格式（Pillow 能解码，但 Excel 不认），
   嵌入前统一转成 JPEG 缩略图。原图仍留在 images/ 目录，不做改动。
3. 需求：格子里是 90x90 缩略图，但点开要看原图清晰度。
   做法 = 嵌入 90x90 缩略图 + 给图片挂指向「原图 URL」的超链接。
   Excel 里点图会打开浏览器看原图，画质不受缩略图影响。
4. 原 URL 文本按需求删掉，不再单独占一列（信息保留在超链接里）。
5. 批次重构后默认输出与批次目录同名（`<批次名>.xlsx`），便于分辨批次。
   缩略图列位置由列定义决定，v2.0 在「价格」后插入「累计评价数」「营销活动」
   两列后，缩略图列已由 H 顺移到 J —— 不要再硬编码列号。

用法
----
    python export_images_xlsx.py [BASE] [--run <批次名>] [--all-runs]
                                 [--csv report.csv] [--out <文件名>.xlsx]
                                 [--size 90] [--quality 88] [--keep-url]

    BASE 默认当前目录；不传 --run 自动取 runs/ 下最新批次，
    输出为 `<批次目录名>.xlsx`。
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from datetime import datetime
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("[错误] 缺少 Pillow，无法生成缩略图。请先 pip install Pillow")
    sys.exit(2)

try:
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    print("[错误] 缺少 openpyxl。请先 pip install openpyxl")
    sys.exit(2)


def norm_path(p: str) -> str:
    """兼容 Git Bash 风格路径 /c/Users/... → C:/Users/..."""
    if not p:
        return p
    s = str(p)
    if len(s) >= 3 and s[0] == "/" and s[2] == "/" and s[1].isalpha():
        s = f"{s[1].upper()}:{s[2:]}"
    return s.replace("\\", "/")


def _load_resolver():
    """从同目录的 fetch_main_images 借用批次目录解析逻辑（避免重复实现）。"""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from fetch_main_images import resolve_run_dir  # noqa: WPS433
        return resolve_run_dir
    except Exception:
        def _fallback(base: Path, run=None, need_data=False):
            runs = base / "runs"
            if runs.is_dir():
                cands = [d for d in runs.iterdir() if d.is_dir()]
                if need_data:
                    cands = [d for d in cands if (d / "report.csv").exists()]
                if cands:
                    return max(cands, key=lambda d: d.stat().st_mtime)
            return base
        return _fallback


def default_base() -> Path:
    """默认 BASE：脚本平铺时=所在目录；技能包布局（scripts/）时=包根目录。"""
    here = Path(__file__).resolve().parent
    return here.parent if here.name == "scripts" else here


resolve_run_dir = _load_resolver()


def log(msg: str, logfile: Path | None = None):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if logfile:
        logfile.parent.mkdir(parents=True, exist_ok=True)
        with open(logfile, "a", encoding="utf-8") as f:
            f.write(line + "\n")


# 表头中文名（导出给人看，所以用中文）
HEADER_CN = {
    "sku": "SKU",
    "status": "状态",
    "title": "商品标题",
    "price": "价格",
    "comment_count": "累计评价数",
    "promo": "营销活动",
    "shop": "店铺",
    "img_count": "图数",
    "image_file": "本地图片",
    "image": "主图",          # 嵌入图所在列（替换原 image_url 的位置）
    "page_url": "商品链接",
    "note": "备注",
    "ts": "抓取时间",
}

STATUS_CN = {
    "ok": "成功",
    "risk": "风控",
    "no_image": "无主图",
    "img_download_failed": "图下载失败",
}

# 列宽（单位：Excel 字符宽）。图片列要跟缩略图宽度匹配才好看。
COL_WIDTH = {
    "sku": 18,
    "status": 10,
    "title": 46,
    "price": 12,
    "comment_count": 13,
    "promo": 42,
    "shop": 18,
    "img_count": 7,
    "image_file": 20,
    "page_url": 34,
    "note": 16,
    "ts": 20,
}


def load_rows(csv_path: Path) -> list[dict]:
    if not csv_path.exists():
        raise FileNotFoundError(f"找不到 {csv_path}")
    raw = csv_path.read_text(encoding="utf-8-sig")
    return list(csv.DictReader(io.StringIO(raw)))


def make_thumb(src: Path, px: int, quality: int) -> bytes | None:
    """把任意格式（含 AVIF）图片转成 px×px 内的 JPEG 缩略图字节。"""
    try:
        with Image.open(src) as im:
            im = im.convert("RGB")
            im.thumbnail((px, px), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=quality, optimize=True)
            return buf.getvalue()
    except Exception:
        return None


def build_workbook(rows: list[dict], base: Path, px: int, quality: int,
                   keep_url_col: bool, logfile: Path | None):
    wb = Workbook()
    ws = wb.active
    ws.title = "主图抓取结果"

    # 列顺序：v2.0 起在 price 后插入「累计评价数」「营销活动」两列，
    #         嵌入图列随之后移（不再固定是 H 列，位置由本列表决定）
    cols = ["sku", "status", "title", "price", "comment_count", "promo",
            "shop", "img_count", "image_file", "image"]
    if keep_url_col:
        cols.append("image_url")
    cols += ["page_url", "note", "ts"]

    # ---- 表头 ----
    head_fill = PatternFill("solid", fgColor="1F4E79")
    head_font = Font(color="FFFFFF", bold=True, size=11)
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for ci, key in enumerate(cols, start=1):
        c = ws.cell(row=1, column=ci, value=HEADER_CN.get(key, key))
        c.fill = head_fill
        c.font = head_font
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = border
    ws.row_dimensions[1].height = 26

    # 设置列宽
    for ci, key in enumerate(cols, start=1):
        if key == "image":
            # 一列 Excel 宽 ≈ 7px，90px 缩略图约需 12.9 字符宽
            ws.column_dimensions[get_column_letter(ci)].width = px / 7.0 + 1.5
        else:
            ws.column_dimensions[get_column_letter(ci)].width = COL_WIDTH.get(key, 16)

    # ---- 数据行 ----
    img_col_idx = cols.index("image") + 1
    ok_cnt = embedded = skipped = 0
    # 行高单位是磅：1 px = 0.75 pt。留 4pt 余量图片才不会被行边裁掉
    row_h = px * 0.75 + 4

    for ri, r in enumerate(rows, start=2):
        for ci, key in enumerate(cols, start=1):
            if key == "image":
                continue
            val = r.get(key, "")
            if key == "status":
                val = STATUS_CN.get(val, val)
            c = ws.cell(row=ri, column=ci, value=val)
            c.border = border
            if key == "title":
                c.alignment = Alignment(vertical="center", wrap_text=False)
            elif key in ("sku", "price", "img_count", "status", "ts"):
                c.alignment = Alignment(horizontal="center", vertical="center")
            else:
                c.alignment = Alignment(vertical="center")

        # 图片列
        icell = ws.cell(row=ri, column=img_col_idx)
        icell.border = border
        icell.alignment = Alignment(horizontal="center", vertical="center")
        # 显式清空，避免继承任何残留文本（URL 文本按需求删除）
        icell.value = None

        fname = r.get("image_file", "").strip()
        src = base / "images" / fname if fname else None
        if src and src.exists():
            data = make_thumb(src, px, quality)
            if data:
                # openpyxl 只认文件路径，所以先写临时缩略图
                thumb_dir = base / ".thumbs"
                thumb_dir.mkdir(exist_ok=True)
                tpath = thumb_dir / f"{Path(fname).stem}_{px}_q{quality}.jpg"
                if not tpath.exists():
                    tpath.write_bytes(data)
                xi = XLImage(str(tpath))
                xi.width, xi.height = px, px
                # ★ 关键：把图片锚到目标单元格（OneCellAnchor）
                from openpyxl.drawing.spreadsheet_drawing import OneCellAnchor, AnchorMarker
                from openpyxl.drawing.xdr import XDRPositiveSize2D

                marker = AnchorMarker(col=img_col_idx - 1, colOff=0,
                                      row=ri - 1, rowOff=0)
                # EMU 单位：1 px = 9525 EMU
                size = XDRPositiveSize2D(cx=px * 9525, cy=px * 9525)
                xi.anchor = OneCellAnchor(_from=marker, ext=size)
                ws.add_image(xi)

                # ★ 点图看原图：优先挂京东原图 URL；URL 缺失时退回指向本地原图文件
                #   本地文件是 800x800+ 的原始下载（AVIF/JPEG），画质等同原图，
                #   且不受 CDN 链接过期影响。
                purl = r.get("image_url", "").strip()
                icell.hyperlink = purl if purl else src.resolve().as_uri()
                # ⚠ openpyxl 的坑：给 hyperlink 赋值时，若 value 为 None，
                #   它会自动把 URL 填进 value（实测确认）。必须在挂完链接后清空，
                #   否则 URL 文本会写在图片下层，看起来 H 列还是字符串。
                icell.value = None
                embedded += 1
            else:
                icell.value = "缩略图失败"
                skipped += 1
        else:
            icell.value = "无图片" if r.get("status") != "risk" else "/"
            skipped += 1

        if r.get("status") == "ok":
            ok_cnt += 1

        # 行高：有图的行撑到图片高度，没图的用默认
        ws.row_dimensions[ri].height = row_h if (src and src.exists()) else 18

    # ---- 冻结首行 + 筛选 ----
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{len(rows) + 1}"

    log(f"  嵌入图片 {embedded} 张，跳过 {skipped} 行，成功行 {ok_cnt}/{len(rows)}", logfile)
    return wb


def write_with_fallback(wb, out_path: Path, logfile: Path | None) -> Path | None:
    """写 xlsx。被 Excel 占用时自动换名，不让导出失败阻断流程。"""
    try:
        wb.save(out_path)
        return out_path
    except (PermissionError, OSError):
        pass
    for i in range(2, 21):
        alt = out_path.with_name(f"{out_path.stem}_{i}{out_path.suffix}")
        try:
            wb.save(alt)
            log(f"[警告] {out_path.name} 被占用（大概率 Excel 开着），"
                f"已改写到 {alt.name}", logfile)
            return alt
        except (PermissionError, OSError):
            continue
    log(f"[警告] {out_path.name} 及 20 个备用名均写入失败，xlsx 未生成", logfile)
    return None


def main():
    ap = argparse.ArgumentParser(description="report.csv → 带嵌入图片的 xlsx")
    ap.add_argument("base", nargs="?", default=None, help="BASE 数据目录（默认：工具目录）")
    ap.add_argument("--csv", default="report.csv", help="输入 CSV（默认 report.csv）")
    ap.add_argument("--out", default="report_images.xlsx", help="输出 xlsx（默认 report_images.xlsx）")
    ap.add_argument("--size", type=int, default=90, help="缩略图像素边长（默认 90）")
    ap.add_argument("--quality", type=int, default=88, help="缩略图 JPEG 质量（默认 88）")
    ap.add_argument("--keep-url", action="store_true",
                    help="额外保留一列图片 URL 文本（默认删除）")
    ap.add_argument("--run", help="指定批次目录名（默认最新批次）")
    ap.add_argument("--all-runs", action="store_true",
                    help="为 runs/ 下每个批次各导出一份 xlsx")
    args = ap.parse_args()

    # 定位批次目录：支持「BASE 根目录」和「runs/<批次>/」两种结构，
    # 以及外部脚本把批次目录当 base 直接传进来的情况。
    BASE_ARG = Path(norm_path(args.base)).resolve() if args.base else default_base()

    # 传入的本来就是批次目录（有 report.csv）→ 直接用
    looks_like_run = (BASE_ARG / "report.csv").exists()
    if BASE_ARG.name == "runs" or (BASE_ARG / "runs").is_dir() or looks_like_run:
        ROOT = BASE_ARG if looks_like_run else (
            BASE_ARG.parent if BASE_ARG.name == "runs" else BASE_ARG)
    else:
        ROOT = BASE_ARG

    if looks_like_run:
        targets = [BASE_ARG]
    elif args.all_runs:
        runs_root = ROOT / "runs"
        targets = sorted([d for d in runs_root.iterdir()
                          if d.is_dir() and (d / "report.csv").exists()]
                         if runs_root.is_dir() else [],
                         key=lambda d: d.stat().st_mtime)
        if not targets:
            print("[提示] runs/ 下没有含 report.csv 的批次")
            return 0
    else:
        targets = [resolve_run_dir(ROOT, args.run, need_data=True) or ROOT]

    rc = 0
    for RUN_DIR in targets:
        rc |= export_one(RUN_DIR, args)
    return rc


def export_one(RUN_DIR: Path, args) -> int:
    """导出单个批次目录。"""
    csv_path = RUN_DIR / args.csv if not Path(args.csv).is_absolute() else Path(args.csv)
    if args.out and Path(args.out).is_absolute():
        out_path = Path(args.out)
    elif args.out and args.out != "report_images.xlsx":
        out_path = RUN_DIR / args.out
    else:
        # 默认：表格与批次目录同名，便于区分批次
        out_path = RUN_DIR / f"{RUN_DIR.name}.xlsx" if RUN_DIR.name != RUN_DIR.anchor else RUN_DIR / "report_images.xlsx"

    logfile = RUN_DIR / "logs" / f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    log("=" * 62, logfile)
    log(f"  导出带图片的 xlsx：{csv_path.name} → {out_path.name}", logfile)
    log(f"  缩略图 {args.size}x{args.size}px，质量 {args.quality}", logfile)

    try:
        rows = load_rows(csv_path)
    except FileNotFoundError as e:
        log(f"[错误] {e}", logfile)
        return 2

    if not rows:
        log("[错误] CSV 里没有数据", logfile)
        return 2

    log(f"  读到 {len(rows)} 行", logfile)
    wb = build_workbook(rows, RUN_DIR, args.size, args.quality, args.keep_url, logfile)
    written = write_with_fallback(wb, out_path, logfile)

    if written:
        log(f"  完成 → {written}", logfile)
        log(f"  提示：点单元格里的图可直接看原图（挂了原图链接）", logfile)
    log("=" * 62, logfile)
    return 0 if written else 1


if __name__ == "__main__":
    sys.exit(main())
