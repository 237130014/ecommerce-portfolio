# -*- coding: utf-8 -*-
"""京东 SKU 主图抓取 · 进度统计

显示已完成 / 待抓 / 失败的情况，以及按当前节奏还要多久。

用法：
    python fetch_stats.py                 # 统计最新批次
    python fetch_stats.py --run <批次名>  # 统计指定批次
    python fetch_stats.py --all           # 列出所有批次概览
    python fetch_stats.py --top 50        # 改目标范围（默认前 50 名）
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_main_images import (  # noqa: E402
    norm_path, read_skus_from_csv, resolve_run_dir,
)

BASE = Path(__file__).resolve().parent


def load_done(state_file: Path) -> dict:
    if not state_file.exists():
        return {}
    try:
        return json.loads(state_file.read_text(encoding="utf-8")).get("done", {})
    except Exception:
        return {}


def find_xlsx(run_dir: Path) -> Path | None:
    """找批次目录里的嵌图表格。

    批次重构后表格与批次目录同名（<批次名>.xlsx），不再是固定 report_images.xlsx，
    这里两种都认，并跳过 Excel 的 ~$ 临时锁文件。
    """
    preferred = run_dir / f"{run_dir.name}.xlsx"
    if preferred.exists():
        return preferred
    for p in sorted(run_dir.glob("*.xlsx")):
        if not p.name.startswith("~$"):
            return p
    return None


def stats_one(run_dir: Path, skus: list[str], top: int) -> int:
    skus = skus[:top] if top > 0 else skus
    done = load_done(run_dir / "state.json")
    done_in_scope = [s for s in skus if s in done]
    pending = [s for s in skus if s not in done]
    img_dir = run_dir / "images"
    imgs = len(list(img_dir.glob("*"))) if img_dir.exists() else 0

    try:
        rel = run_dir.relative_to(BASE)
    except ValueError:
        rel = run_dir

    print("=" * 58)
    print("  京东 SKU 主图抓取 · 进度")
    print("=" * 58)
    print(f"  批次目录：{rel}")
    print(f"  目标范围：前 {top} 名" if top > 0 else "  目标范围：全部")
    print(f"  已完成  ：{len(done_in_scope)} / {len(skus)}")
    print(f"  待抓    ：{len(pending)}")
    print(f"  图片目录：{imgs} 个文件")

    xlsx = find_xlsx(run_dir)
    if xlsx:
        print(f"  表格    ：{xlsx.name}  ({xlsx.stat().st_size / 1024:.0f} KB)")
    print()

    if pending:
        per_batch = 25
        gap_min = 12
        batches = (len(pending) + per_batch - 1) // per_batch
        est = batches * 3 + (batches - 1) * gap_min
        print(f"  建议分 {batches} 批跑（每批 {per_batch} 个，批间冷却 {gap_min} 分钟）")
        print(f"  预计耗时约 {est} 分钟（含冷却）")
        print()
        print("  下一批待抓 SKU（前 5 个）：")
        for s in pending[:5]:
            print(f"    - {s}")
        if len(pending) > 5:
            print(f"    ... 还有 {len(pending) - 5} 个")
    else:
        print(f"  [完成] 前 {top} 名已全部抓完。" if top > 0 else "  [完成] 已全部抓完。")
        print("         要重抓加 --force；要扩到更多名次改 --top。")

    print()
    print("  下一步：双击 run.bat 选 1，按提示输入本次抓取数量。")
    print("=" * 58)
    return 0


def list_all(skus: list[str]) -> int:
    runs_root = BASE / "runs"
    if not runs_root.is_dir():
        print("[提示] 还没有 runs/ 批次目录（用 run.bat 跑一次就会出现）")
        return 0
    dirs = sorted([d for d in runs_root.iterdir() if d.is_dir()],
                  key=lambda d: d.stat().st_mtime, reverse=True)
    if not dirs:
        print("[提示] runs/ 下暂无批次")
        return 0
    print("=" * 74)
    print("  所有批次概览（按时间倒序）")
    print("=" * 74)
    print(f"  {'批次目录':<40} {'已完成':>6} {'图片':>6}  表格")
    print("-" * 74)
    for d in dirs:
        done = load_done(d / "state.json")
        imgs = len(list((d / "images").glob("*"))) if (d / "images").is_dir() else 0
        x = "有" if find_xlsx(d) else "-"
        name = d.name if len(d.name) <= 40 else d.name[:37] + "..."
        print(f"  {name:<40} {len(done):>6} {imgs:>6}  {x}")
    print("=" * 74)
    print("  看某个批次详情：python fetch_stats.py --run <批次目录名>")
    return 0


def main():
    ap = argparse.ArgumentParser(description="抓取进度统计")
    ap.add_argument("--run", help="指定批次目录名（默认最新批次）")
    ap.add_argument("--all", action="store_true", help="列出所有批次概览")
    ap.add_argument("--top", type=int, default=50, help="目标范围：前 N 名（0=全部）")
    args = ap.parse_args()

    csv_path = BASE / "skus.csv"
    skus = read_skus_from_csv(str(csv_path)) if csv_path.exists() else []

    if args.all:
        return list_all(skus)

    if not skus:
        print(f"[警告] 读不到 {csv_path}，将只按 state.json 统计")
    run_dir = resolve_run_dir(BASE, args.run, need_data=True)
    if run_dir is None:
        print("[提示] 还没跑过抓取（找不到任何批次记录）")
        print("       双击 run.bat 选 1 开始。")
        return 0
    return stats_one(run_dir, skus or [], args.top)


if __name__ == "__main__":
    sys.exit(main())
