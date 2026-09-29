#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把旧版「根目录平铺」的数据迁移到新版 runs/<批次>/ 目录结构。

旧结构（v1）：
    BASE/report.csv, BASE/images/, BASE/state.json, BASE/logs/, BASE/report_images.xlsx

新结构（v2）：
    BASE/runs/<批次名>/{report.csv, images/, state.json, logs/, <批次名>.xlsx}

用法：
    python migrate_to_runs.py [BASE] [--run-name 名称] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from fetch_main_images import norm_path, sanitize_run_name  # noqa: E402
except Exception:
    def norm_path(p):
        s = str(p)
        if len(s) >= 3 and s[0] == "/" and s[2] == "/" and s[1].isalpha():
            s = f"{s[1].upper()}:{s[2:]}"
        return s.replace("\\", "/")

    def sanitize_run_name(n):
        import re
        return re.sub(r'[<>:"/\\|?*]', "_", n).strip("_ .") or "批次"


def main():
    ap = argparse.ArgumentParser(description="迁移到 runs/ 批次目录结构")
    ap.add_argument("base", nargs="?", default=".")
    ap.add_argument("--run-name", default="历史批次",
                    help="迁入的批次目录名（默认「历史批次」）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    BASE = Path(norm_path(args.base)).resolve()
    target = BASE / "runs" / sanitize_run_name(args.run_name)

    # 判断是否还有旧结构残留
    old_items = []
    if (BASE / "report.csv").exists():
        old_items.append(BASE / "report.csv")
    if (BASE / "state.json").exists():
        old_items.append(BASE / "state.json")
    if (BASE / "images").is_dir() and any((BASE / "images").iterdir()):
        old_items.append(BASE / "images")
    if (BASE / "logs").is_dir() and any((BASE / "logs").iterdir()):
        old_items.append(BASE / "logs")
    xlsx = sorted(BASE.glob("report_images*.xlsx"))
    old_items.extend(xlsx)

    if not old_items:
        print("[信息] 没有需要迁移的旧结构数据，已是新版结构。")
        return 0

    print("=" * 62)
    print(f"  迁移到：{target.relative_to(BASE)}")
    print(f"  待迁移 {len(old_items)} 项：")
    for p in old_items:
        kind = "目录" if p.is_dir() else "文件"
        n = len(list(p.iterdir())) if p.is_dir() else 1
        print(f"    - {p.name:<28} ({kind}, {n})")
    print("=" * 62)

    if args.dry_run:
        print("（dry-run，未执行。去掉 --dry-run 生效）")
        return 0

    target.mkdir(parents=True, exist_ok=True)

    for p in old_items:
        dst = target / p.name
        if dst.exists():
            print(f"  [跳过] {p.name} 目标已存在")
            continue
        shutil.move(str(p), str(dst))
        print(f"  [移动] {p.name}")

    # xlsx 改名成「批次目录同名.xlsx」，一眼知道是哪批
    for x in target.glob("report_images*.xlsx"):
        newname = target / f"{target.name}.xlsx"
        if x.name != newname.name and not newname.exists():
            x.rename(newname)
            print(f"  [改名] {x.name} → {newname.name}")

    print()
    print(f"[完成] 已迁入 {target}")
    print(f"        现在结构：")
    for sub in sorted(target.iterdir()):
        if sub.is_dir():
            print(f"          {target.name}/{sub.name}/  ({len(list(sub.iterdir()))} 项)")
        else:
            print(f"          {target.name}/{sub.name}")
    print()
    print("  验证：python fetch_stats.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
