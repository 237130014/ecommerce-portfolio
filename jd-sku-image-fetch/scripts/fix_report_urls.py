#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""修复 report.csv：从备份 / state.json / 本地图片补齐缺失的 image_url。

背景
----
fetch_main_images.py 早期版本保存 state.json 时只存了
image / title / price / ts，没存 image_url / page_url / shop / img_count。
后来加入的「对账补录」逻辑发现 state 里的 SKU 不在 report 中时，
会把这些字段写成空字符串，导致 report.csv 里的图片 URL 被清空。

本脚本按优先级恢复：
  1) 备份报告（_backup_*.csv / report_*.csv 等历史副本）
  2) 抓取日志（若曾记录 URL）
  3) 仅作为最后手段：标记为「本地图」（xlsx 导出时改指向本地文件）

用法
----
    python fix_report_urls.py [BASE] [--apply]
    不加 --apply 只做体检（dry-run），加了才真正写回 report.csv
"""

from __future__ import annotations

import argparse
import csv
import glob
import io
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

FIELDS = ["sku", "status", "title", "price", "comment_count", "promo",
          "shop", "img_count", "image_file", "image_url", "page_url",
          "note", "ts"]


def _load_resolver():
    """借用批次目录解析逻辑（与其它脚本保持一致）。"""
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


resolve_run_dir = _load_resolver()


def default_base() -> Path:
    """默认 BASE：脚本平铺时=所在目录；技能包布局（scripts/）时=包根目录。"""
    here = Path(__file__).resolve().parent
    return here.parent if here.name == "scripts" else here


def norm_path(p: str) -> str:
    if not p:
        return p
    s = str(p)
    if len(s) >= 3 and s[0] == "/" and s[2] == "/" and s[1].isalpha():
        s = f"{s[1].upper()}:{s[2:]}"
    return s.replace("\\", "/")


def flat(v) -> str:
    if v is None:
        return ""
    s = str(v).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    s = s.replace("\u00a0", " ").replace("\u2007", " ").replace("\u202f", " ")
    while "  " in s:
        s = s.replace("  ", " ")
    return s.strip()


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))


def write_csv(path: Path, rows: list[dict]):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: flat(v) for k, v in r.items()})


def harvest_backups(base: Path) -> tuple[dict, list[Path]]:
    """扫描目录下所有历史报告副本，收集 sku → 最完整的行。"""
    best: dict[str, dict] = {}
    used: list[Path] = []
    pats = ["_backup_*.csv", "report_[0-9]*.csv", "report_backup*.csv", "*.bak.csv"]
    seen = set()
    for pat in pats:
        for p in glob.glob(str(base / pat)):
            pp = Path(p)
            if pp.resolve() == (base / "report.csv").resolve():
                continue
            if pp.name in seen:
                continue
            seen.add(pp.name)
            rows = read_csv(pp)
            if not rows:
                continue
            n_url = sum(1 for r in rows if (r.get("image_url") or "").strip())
            if n_url == 0:
                continue
            used.append(pp)
            for r in rows:
                sku = (r.get("sku") or "").strip()
                if not sku:
                    continue
                cur = best.get(sku)
                score = sum(1 for k in ("image_url", "page_url", "title", "shop", "img_count")
                            if (r.get(k) or "").strip())
                if cur is None or score > cur["_score"]:
                    r = dict(r)
                    r["_score"] = score
                    best[sku] = r
    return best, used


def parse_log_urls(base: Path) -> dict[str, str]:
    """从抓取日志里捞 sku→图片URL。

    只认图片 CDN 地址（360buyimg / jfs）。京东的风控页地址形如
    https://pc-frequent-pro.pf.jd.com/?from=pc_item&reason=403，
    绝不能当成图片 URL 写进报告（历史踩坑）。
    """
    out: dict[str, str] = {}
    log_dir = base / "logs"
    if not log_dir.exists():
        return out

    BAD = ("pf.jd.com", "reason=403", "risk_handler", "passport.jd.com")
    IMG_OK = re.compile(r"^https?://[\w.-]*360buyimg\.com/\S+$|^https?://[\w.-]*jd\.com/\S*jfs/\S+$")

    for lf in sorted(log_dir.glob("fetch_*.log")):
        try:
            txt = lf.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in re.finditer(r"\[(\d+)/(\d+)\]\s+(\d{6,})[^\n]*\n[^\n]*?(https://[^\s)\"']+)", txt):
            sku, url = m.group(3), m.group(4).rstrip(".,;")
            if any(b in url for b in BAD):
                continue
            if not IMG_OK.match(url):
                continue
            if not out.get(sku):
                out[sku] = url
    return out


def main():
    ap = argparse.ArgumentParser(description="修复 report.csv：URL 缺失 / 失败行被覆盖")
    ap.add_argument("base", nargs="?", default=None,
                    help="项目根目录或批次目录（默认：工具目录）")
    ap.add_argument("--run", help="指定批次目录名（默认最新批次）")
    ap.add_argument("--csv", default="report.csv")
    ap.add_argument("--apply", action="store_true", help="真正写回（默认只体检）")
    args = ap.parse_args()

    ROOT = Path(norm_path(args.base)).resolve() if args.base else default_base()

    # 定位批次目录：传入 [[[BASE 根]]] 时自动找最新批次；传入批次目录时直接用
    if (ROOT / "report.csv").exists() or ((ROOT / "state.json").exists() and not (ROOT / "runs").is_dir()):
        BASE = ROOT
    else:
        BASE = resolve_run_dir(ROOT, args.run, need_data=True) or ROOT

    target = BASE / args.csv
    rows = read_csv(target)
    if not rows:
        print(f"[错误] 读不到 {target}")
        print("       若项目使用 runs/ 批次结构，请用 --run 指定批次名，或直接传批次目录。")
        return 2

    print("=" * 64)
    print(f"  report 体检：{target.name}（{len(rows)} 行）")
    try:
        print(f"  批次目录：{BASE.relative_to(ROOT)}")
    except ValueError:
        print(f"  批次目录：{BASE}")

    # ---- 检查 1：失败行其实有本地成功记录（被重抓覆盖） ----
    st_file = BASE / "state.json"
    done = {}
    if st_file.exists():
        try:
            done = json.loads(st_file.read_text(encoding="utf-8")).get("done", {})
        except Exception:
            pass

    imgs = {p.stem: p.name for p in (BASE / "images").iterdir() if p.is_file()}
    restored = 0
    for r in rows:
        if r.get("status") == "ok":
            continue
        v = done.get(r["sku"])
        if not v or not v.get("image"):
            continue
        if not (BASE / "images" / v["image"]).exists():
            continue
        u = v.get("image_url", "")
        if any(b in u for b in ("pf.jd.com", "reason=403", "risk_handler", "passport.jd.com")):
            u = ""
        r.update({
            "status": "ok",
            "title": v.get("title", ""), "price": v.get("price", ""),
            "comment_count": v.get("comment_count", ""),
            "promo": v.get("promo", ""),
            "shop": v.get("shop", ""), "img_count": v.get("img_count", ""),
            "image_file": v["image"], "image_url": u,
            "page_url": v.get("page_url", ""),
            "note": "由state恢复", "ts": v.get("ts", ""),
        })
        restored += 1
    if restored:
        print(f"[0] 恢复被覆盖的成功行：{restored} 行（state.json + 本地图片都在）")

    # ---- 检查 2：URL 缺失（从备份 / 日志恢复） ----
    miss_before = [r["sku"] for r in rows if not (r.get("image_url") or "").strip()]
    print(f"  URL 缺失：{len(miss_before)} 行")
    print("=" * 64)

    if not miss_before:
        if not restored:
            print("  无需修复。")
            if not args.apply:
                return 0
        if restored and not args.apply:
            print("\n（dry-run，未写回。加 --apply 生效）")
            return 0
        if args.apply:
            stamp = datetime.now().strftime("%H%M%S")
            bak = BASE / f"report_before_fix_{stamp}.csv"
            shutil.copy2(target, bak)
            write_csv(target, rows)
            print(f"\n[完成] 已写回（备份 {bak.name}）")
        return 0

    best, used = harvest_backups(BASE)
    if used:
        print(f"\n[1] 可用备份：{', '.join(p.name for p in used)}")
    log_urls = parse_log_urls(BASE)
    if log_urls:
        print(f"[2] 日志捞到 {len(log_urls)} 条 sku→URL")

    fixed_from_backup = fixed_from_log = 0
    for r in rows:
        sku = r["sku"]
        if (r.get("image_url") or "").strip():
            continue
        b = best.get(sku)
        if b and (b.get("image_url") or "").strip():
            r["image_url"] = b["image_url"].strip()
            for k in ("page_url", "title", "shop", "img_count"):
                if not (r.get(k) or "").strip() and (b.get(k) or "").strip():
                    r[k] = b[k].strip()
            if r.get("note") == "由 state.json 补录":
                r["note"] = ""
            fixed_from_backup += 1
            continue
        u = log_urls.get(sku)
        if u:
            r["image_url"] = u
            if r.get("note") == "由 state.json 补录":
                r["note"] = ""
            fixed_from_log += 1

    miss_after = [r["sku"] for r in rows if not (r.get("image_url") or "").strip()]
    print(f"\n[3] 备份补回 {fixed_from_backup} 行，日志补回 {fixed_from_log} 行")
    print(f"    仍缺 URL：{len(miss_after)} 行 {miss_after}")

    if miss_after:
        print("\n    这些 SKU 的 URL 已无从恢复。xlsx 导出时会自动改为")
        print("    点击打开本地原图（images/<sku>.*，画质与 CDN 原图一致）。")
        for r in rows:
            if r["sku"] in miss_after:
                local = imgs.get(r["sku"])
                if local:
                    note = r.get("note") or ""
                    if "URL缺失" not in note:
                        r["note"] = (note + "|URL缺失(有本地原图)").strip("|")
                    if not (r.get("image_file") or "").strip():
                        r["image_file"] = local

    if not args.apply:
        print("\n（dry-run，未写回。加 --apply 生效）")
        return 0

    stamp = datetime.now().strftime("%H%M%S")
    bak = BASE / f"report_before_fix_{stamp}.csv"
    shutil.copy2(target, bak)
    write_csv(target, rows)
    print(f"\n[完成] 已写回 {target.name}（备份 {bak.name}）")
    print(f"        现在有 URL：{len(rows) - len(miss_after)}/{len(rows)} 行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
