#!/usr/bin/env python3
"""把表格里的图片 URL 自动转成单元格内嵌的图片预览。

扫描表格中所有以 jpg / png / webp 等后缀结尾的链接，并发下载后统一缩放成
正方形缩略图，再作为一个新列插到原 URL 列的右侧。原文件和原 URL 列都保留。

用法：
    python url2img.py 商品表.xlsx
    python url2img.py 商品表.xlsx -o 出图版.xlsx -s 120 -w 12
    python url2img.py 商品表.xlsx --column 主图链接 --column 详情图
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image as PILImage
from PIL import ImageOps
from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Font
from openpyxl.utils import column_index_from_string, get_column_letter

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# 真正的 URL 边界只有这些：空白、引号、括号、竖线、中文与全角标点。
# 半角逗号/分号不能当边界——阿里云 OSS 的 x-oss-process=image/resize,m_mfit 常带未转义的
# 裸逗号，在这里截断就会得到残缺链接，而带签名的链接又不允许去掉查询串重试（会 403），
# 只能直接失败。同一格里的多个链接改由 find_urls 按 http 起始切分来处理。
_CJK = r"\u2e80-\u9fff\u3000-\u303f\uff00-\uffef"
_CHARS = rf"[^\s\"'<>()\\|{_CJK}]"
_SINGLE_URL = re.compile(
    rf"https?://{_CHARS}+?\.(?:jpe?g|png|gif|bmp|webp|tiff?){_CHARS}*",
    re.IGNORECASE,
)


def find_urls(text: str) -> list[str]:
    """从任意文本里按出现顺序提取所有图片 URL。

    先按 http 起始把文本切成若干段分别匹配，避免同一格里的多个链接粘成一条；
    匹配结果再剥掉尾部的逗号/分号/句点，这样"逗号究竟是参数还是分隔符"就不必猜了。
    """
    if not isinstance(text, str) or "http" not in text:
        return []
    urls = []
    for chunk in re.split(r"(?=https?://)", text):
        match = _SINGLE_URL.search(chunk)
        if match:
            url = match.group(0).rstrip(",;.")
            if url:
                urls.append(url)
    return urls

FAIL_FONT = Font(color="FFC00000", size=9)


@dataclass
class Config:
    size: int = 100
    workers: int = 8
    timeout: float = 10.0
    retries: int = 2
    referer: str = "auto"
    header_row: int = 1
    columns: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# 表格读取
# --------------------------------------------------------------------------

def detect_embedded_media(path: Path) -> int:
    """统计 xlsx 里已嵌入的图片数量（openpyxl 保存时会丢弃它们）。"""
    if path.suffix.lower() not in (".xlsx", ".xlsm", ".xltx"):
        return 0
    try:
        with zipfile.ZipFile(path) as z:
            return sum(1 for n in z.namelist()
                       if n.startswith("xl/media/") and not n.endswith("/"))
    except (zipfile.BadZipFile, OSError):
        return 0


def load_csv(path: Path) -> Workbook:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            with path.open("r", encoding=encoding, newline="") as fh:
                rows = list(csv.reader(fh))
            break
        except UnicodeDecodeError:
            continue
    else:
        raise SystemExit(f"无法识别编码：{path.name}")

    wb = Workbook()
    ws = wb.active
    ws.title = path.stem[:31] or "Sheet1"
    for r, row in enumerate(rows, 1):
        for c, value in enumerate(row, 1):
            if value:
                ws.cell(r, c).value = value
    return wb


def load_table(path: Path) -> Workbook:
    if path.suffix.lower() == ".csv":
        return load_csv(path)
    return load_workbook(path, keep_vba=path.suffix.lower() == ".xlsm")


# --------------------------------------------------------------------------
# 扫描
# --------------------------------------------------------------------------

def cell_urls(cell) -> list[str]:
    """取一个单元格里的图片链接，优先看文本内容，没有再退回超链接目标。"""
    value = cell.value
    if isinstance(value, str) and value:
        urls = find_urls(value)
        if urls:
            return urls
    target = getattr(getattr(cell, "hyperlink", None), "target", None)
    if target:
        return find_urls(str(target))
    return []


def resolve_columns(ws, header_row: int, names: list[str]) -> set[int] | None:
    """把 --column 的列名/列字母解析成列号；没指定就返回 None 表示全表扫描。"""
    if not names:
        return None
    by_name = {}
    for cell in ws[header_row]:
        if isinstance(cell.value, str) and cell.value.strip():
            by_name[cell.value.strip()] = cell.column

    picked: set[int] = set()
    for name in names:
        if name in by_name:
            picked.add(by_name[name])
        elif re.fullmatch(r"[A-Za-z]{1,3}", name):
            picked.add(column_index_from_string(name.upper()))
        else:
            print(f"  [警告] 工作表「{ws.title}」里找不到列：{name}")
    return picked or None


def scan_sheet(ws, cfg: Config) -> tuple[dict[int, dict[int, str]], int]:
    """返回 ({列号: {行号: url}}, 含多个链接的单元格数)。

    一个单元格里有多个链接时取第一个——电商导出常把同一张图的多种尺寸塞在一起，
    排在最前面的通常是主图或尺寸最合适的那版。
    """
    wanted = resolve_columns(ws, cfg.header_row, cfg.columns)
    hits: dict[int, dict[int, str]] = {}
    multi = 0
    for row in ws.iter_rows():
        for cell in row:
            if wanted is not None and cell.column not in wanted:
                continue
            urls = cell_urls(cell)
            if not urls:
                continue
            if len(urls) > 1:
                multi += 1
            hits.setdefault(cell.column, {})[cell.row] = urls[0]
    return hits, multi


# --------------------------------------------------------------------------
# 下载与缩略图
# --------------------------------------------------------------------------

def referer_for(url: str, mode: str) -> str | None:
    if mode == "none":
        return None
    if mode != "auto":
        return mode
    parts = urlparse(url)
    return f"{parts.scheme}://{parts.netloc}/" if parts.netloc else None


def fetch_bytes(url: str, cfg: Config) -> bytes | None:
    headers = {"User-Agent": UA, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}
    referer = referer_for(url, cfg.referer)
    if referer:
        headers["Referer"] = referer

    candidates = [url]
    # 带查询串的地址常常是缩略图参数或防盗链签名，失败后回退到裸路径再试一次
    if "?" in url:
        candidates.append(url.split("?", 1)[0])

    for candidate in candidates:
        for attempt in range(cfg.retries + 1):
            try:
                resp = requests.get(candidate, headers=headers, timeout=cfg.timeout)
                if resp.status_code == 200 and resp.content:
                    return resp.content
            except requests.RequestException:
                pass
            if attempt < cfg.retries:
                time.sleep(0.4 * (attempt + 1))
    return None


def build_thumb(data: bytes, size: int, dest: str) -> None:
    """等比缩放后居中贴到白色方画布上，统一存成 JPEG。"""
    img = PILImage.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    if getattr(img, "n_frames", 1) > 1:
        img.seek(0)
    if img.mode == "P":
        img = img.convert("RGBA" if "transparency" in img.info else "RGB")
    elif img.mode in ("RGBA", "LA"):
        img = img.convert("RGBA")
    elif img.mode != "RGB":
        img = img.convert("RGB")

    img.thumbnail((size, size), PILImage.Resampling.LANCZOS)
    offset = ((size - img.width) // 2, (size - img.height) // 2)
    canvas = PILImage.new("RGB", (size, size), (255, 255, 255))
    if img.mode == "RGBA":
        canvas.paste(img, offset, img)          # alpha 当蒙版，透明区域留白
    else:
        canvas.paste(img, offset)
    canvas.save(dest, "JPEG", quality=88, optimize=True)


def prepare_thumb(url: str, cfg: Config, tmpdir: str) -> str | None:
    data = fetch_bytes(url, cfg)
    if not data:
        return None
    dest = str(Path(tmpdir) / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".jpg"))
    try:
        build_thumb(data, cfg.size, dest)
    except (OSError, ValueError):
        return None
    return dest


def download_all(urls: set[str], cfg: Config, tmpdir: str) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    total = len(urls)
    started = time.time()
    with ThreadPoolExecutor(max_workers=cfg.workers) as pool:
        futures = {pool.submit(prepare_thumb, u, cfg, tmpdir): u for u in urls}
        for done, future in enumerate(as_completed(futures), 1):
            try:
                result[futures[future]] = future.result()
            except Exception:
                result[futures[future]] = None
            sys.stdout.write(f"\r  下载并转码 {done}/{total}（{time.time()-started:.0f}s）")
            sys.stdout.flush()
    sys.stdout.write("\r" + " " * 52 + "\r")
    return result


# --------------------------------------------------------------------------
# 写回
# --------------------------------------------------------------------------

def write_images(ws, hits: dict[int, dict[int, str]], thumbs: dict[str, str | None],
                 cfg: Config) -> tuple[int, int]:
    ok = failed = 0
    # 从右往左插列，否则前面插入后后面记录的列号全部偏移
    for col in sorted(hits, reverse=True):
        rows = hits[col]
        new_col = col + 1
        ws.insert_cols(new_col)
        ws.column_dimensions[get_column_letter(new_col)].width = cfg.size / 7 + 0.7

        source_title = ws.cell(cfg.header_row, col).value
        title = (f"{source_title} 图片"
                 if isinstance(source_title, str) and source_title.strip() else "图片预览")
        header = ws.cell(cfg.header_row, new_col)
        header.value = title
        header.font = Font(bold=True)

        for row, url in rows.items():
            cell = ws.cell(row, new_col)
            path = thumbs.get(url)
            if not path:
                cell.value = "下载失败"
                cell.font = FAIL_FONT
                failed += 1
                continue
            ws.add_image(XLImage(path), cell.coordinate)
            ws.row_dimensions[row].height = cfg.size * 0.75 + 3
            ok += 1
    return ok, failed


def process(src: Path, dst: Path, cfg: Config, tmpdir: str,
            reveal_output: bool = False) -> int:
    started = time.time()
    print(f"读取：{src}")

    media = detect_embedded_media(src)
    if media:
        print(f"  [警告] 原表已含 {media} 张嵌入图片，openpyxl 保存时会丢失它们，"
              f"请确认原文件另有备份。")

    wb = load_table(src)
    plans, all_urls, cells, multi = [], set(), 0, 0
    for ws in wb.worksheets:
        if ws.merged_cells.ranges:
            print(f"  [提示] 工作表「{ws.title}」含合并单元格，插入图片列后可能需手工调整。")
        hits, sheet_multi = scan_sheet(ws, cfg)
        if not hits:
            continue
        plans.append((ws, hits))
        multi += sheet_multi
        for rows in hits.values():
            all_urls.update(rows.values())
            cells += len(rows)

    if not all_urls:
        print("没有找到图片链接，未生成新文件。")
        return 1

    print(f"命中：{len(plans)} 个工作表 / {cells} 个单元格 / {len(all_urls)} 个不重复链接")
    if multi:
        print(f"  [提示] {multi} 个单元格里含多个链接，每个只取第一个"
              f"（通常是尺寸最合适的那张）。")
    thumbs = download_all(all_urls, cfg, tmpdir)
    good = sum(1 for v in thumbs.values() if v)
    print(f"下载：成功 {good} 张，失败 {len(all_urls) - good} 张，耗时 {time.time()-started:.1f}s")

    ok = failed = 0
    for ws, hits in plans:
        sheet_ok, sheet_failed = write_images(ws, hits, thumbs, cfg)
        ok += sheet_ok
        failed += sheet_failed

    wb.save(dst)
    size_mb = dst.stat().st_size / 1024 / 1024
    print(f"完成：写入 {ok} 张图片，{failed} 个单元格标记为下载失败")
    print(f"输出：{dst}（{size_mb:.1f} MB，总耗时 {time.time()-started:.1f}s）")
    if reveal_output and sys.stdout.isatty():
        reveal(dst)
    return 0


def ask_for_path() -> Path:
    print("\n把表格文件拖到本窗口（或粘贴完整路径），然后按回车：")
    while True:
        try:
            raw = input("表格路径 > ").strip()
        except EOFError:
            raise SystemExit("没有收到路径，已退出。")
        raw = raw.strip().strip('"').strip("'").strip()
        if not raw:
            print("没有输入内容，请重新输入（Ctrl+C 可退出）。")
            continue
        candidate = Path(raw)
        if candidate.is_file():
            return candidate
        if candidate.is_dir():
            print(f"这是文件夹，不是表格文件：{candidate}")
        else:
            print(f"找不到这个文件：{candidate}")
        print("请检查路径，或直接把文件拖进来。")


def reveal(path: Path) -> None:
    """在文件管理器里定位到刚生成的文件。"""
    try:
        if sys.platform == "win32":
            subprocess.Popen(f'explorer /select,"{path}"')
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path.parent)])
    except OSError:
        pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="把表格里的图片 URL 转成单元格内嵌的图片预览。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n"
               "  python url2img.py                      交互式，拖入或粘贴表格路径\n"
               "  python url2img.py 商品表.xlsx\n"
               "  python url2img.py 商品表.csv -s 140 -w 16\n"
               "  python url2img.py 商品表.xlsx --column 主图链接 --referer none\n")
    parser.add_argument("input", nargs="?", help="输入表格，支持 .xlsx / .xlsm / .csv；"
                                                 "留空则进入交互式输入")
    parser.add_argument("-o", "--output", help="输出文件，默认在原文件名后加「_图片版」")
    parser.add_argument("-s", "--size", type=int, default=100,
                        help="缩略图边长（像素），默认 100")
    parser.add_argument("-w", "--workers", type=int, default=8,
                        help="并发下载线程数，默认 8")
    parser.add_argument("-t", "--timeout", type=float, default=10.0,
                        help="单张图片下载超时秒数，默认 10")
    parser.add_argument("-r", "--retries", type=int, default=2,
                        help="失败重试次数，默认 2")
    parser.add_argument("--referer", default="auto",
                        help="防盗链用的 Referer：auto（按图片域名自动生成，默认）、"
                             "none（不发送）、或直接给一个地址")
    parser.add_argument("--column", action="append", default=[], metavar="名称或列号",
                        help="只处理指定列，可重复；默认扫描全表")
    parser.add_argument("--header-row", type=int, default=1,
                        help="表头所在行号，默认 1")
    parser.add_argument("--open", action="store_true",
                        help="处理完成后在文件管理器里定位到输出文件")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.size < 16:
        raise SystemExit("缩略图边长至少 16 像素")

    if args.input:
        src = Path(args.input)
    else:
        print("=" * 48)
        print("  表格图片链接 → 单元格内图片预览")
        print("=" * 48)
        src = ask_for_path()
    if not src.exists():
        raise SystemExit(f"找不到输入文件：{src}")

    suffix = ".xlsm" if src.suffix.lower() == ".xlsm" else ".xlsx"
    dst = Path(args.output) if args.output else src.with_name(f"{src.stem}_图片版{suffix}")
    if src.resolve() == dst.resolve():
        raise SystemExit("输出路径不能和输入文件相同，请用 -o 指定别的文件名")

    cfg = Config(size=args.size, workers=max(1, args.workers), timeout=args.timeout,
                 retries=max(0, args.retries), referer=args.referer,
                 header_row=max(1, args.header_row), columns=args.column)

    tmpdir = tempfile.mkdtemp(prefix="url2img_")
    try:
        return process(src, dst, cfg, tmpdir, reveal_output=args.open)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已中断")
        sys.exit(130)
