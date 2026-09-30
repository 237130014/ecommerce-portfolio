#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""环境自检 —— 首次使用、或出问题时，先跑这个。

纯标准库实现（不 import openpyxl / Pillow），所以**任何 Python 3.8+ 都能跑起来**，
哪怕依赖还没装 —— 它自己会告诉你缺什么、怎么补。

用法
----
    python doctor.py            # 自检并给修复建议
    python doctor.py --quiet    # 只输出问题项（AI / 脚本调用友好）

退出码
------
    0 = 全部就绪（可能有 WARN，不影响抓取）
    1 = 有 FAIL，需要按提示处理
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def default_base() -> Path:
    """默认被检查的目录。

    源码布局：脚本平铺 → 脚本所在目录
    技能包布局：脚本在 <包>/scripts/ 下 → 包根目录
    """
    return HERE.parent if HERE.name == "scripts" else HERE

OK, WARN, FAIL = "ok", "warn", "fail"
_MARK = {OK: ("[ OK ]", "OK  "), WARN: ("[WARN]", "WARN"), FAIL: ("[FAIL]", "FAIL")}

PY_MIN = (3, 8)
BSK_INSTALL_PS = "irm https://raw.githubusercontent.com/Tencent/BrowserSkill/main/install.ps1 | iex"
BSK_INSTALL_SH = "curl -fsSL https://raw.githubusercontent.com/Tencent/BrowserSkill/main/install.sh | sh"


def _force_utf8() -> None:
    """Windows 控制台默认 GBK，中文会乱码 —— 尽量切到 UTF-8。"""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")  # py3.7+
        except Exception:
            pass


def _width(s: str) -> int:
    """显示宽度：中日韩全角字符占 2 格（终端对齐用）。"""
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _pad(s: str, n: int) -> str:
    return s + " " * max(0, n - _width(s))


class Report:
    def __init__(self) -> None:
        self.items: list[tuple[str, str, str, str]] = []   # level, name, detail, hint

    def add(self, level: str, name: str, detail: str = "", hint: str = "") -> None:
        self.items.append((level, name, detail, hint))

    @property
    def worst(self) -> str:
        levels = {lv for lv, *_ in self.items}
        return FAIL if FAIL in levels else (WARN if WARN in levels else OK)

    def render(self, quiet: bool = False) -> None:
        print("=" * 68)
        print("  京东SKU主图抓取 —— 环境自检")
        print("=" * 68)
        print()
        for level, name, detail, hint in self.items:
            if quiet and level == OK:
                continue
            tag = _MARK[level][0]
            line = f"{tag} {_pad(name, 26)}"
            if detail:
                line += f" {detail}"
            print(line.rstrip())
            if hint and level != OK:
                for hl in hint.splitlines():
                    print(f"        -> {hl}")
        print()
        if self.worst == OK:
            print("结论：环境就绪，可以开始抓取。")
        elif self.worst == WARN:
            print("结论：可以抓取，但上面 WARN 项建议处理（通常是体验问题，不阻塞）。")
        else:
            print("结论：有阻断项，按上面 -> 提示处理后重跑本脚本。")
            print()
            print("  最省事的办法：双击 setup.bat（一键装好全部依赖）")


def check(report: Report, base: Path) -> None:
    # ---------- 1. Python ----------
    v = sys.version_info
    if v >= PY_MIN:
        report.add(OK, "Python 版本", f"{v.major}.{v.minor}.{v.micro}")
    else:
        report.add(FAIL, "Python 版本", f"{v.major}.{v.minor}.{v.micro}（需 >= {PY_MIN[0]}.{PY_MIN[1]}）",
                   "去 python.org 装新版 Python，安装时勾选 Add to PATH")
    report.add(OK, "Python 路径", sys.executable)

    # ---------- 2. 依赖 ----------
    # 注意：import 名与 pip 包名常常不同（PIL 的包名是 Pillow），两个都要写对。
    for mod, pkg, minver, why in (
        ("openpyxl", "openpyxl", None, "生成 Excel 表格"),
        ("PIL", "Pillow", (11, 0), "读取 AVIF 图片 + 生成缩略图"),
    ):
        spec = importlib.util.find_spec(mod)
        if spec is None:
            report.add(FAIL, f"依赖 {pkg}", "未安装",
                       f"{sys.executable} -m pip install {pkg}\n或双击 setup.bat 一键安装")
            continue
        try:
            import importlib.metadata as md
            ver = md.version(pkg)
        except Exception:
            ver = "未知版本"
        if minver:
            try:
                parts = tuple(int(x) for x in ver.split(".")[:2])
                if parts < minver:
                    report.add(WARN, f"依赖 {pkg}", f"{ver}（建议 >= {minver[0]}.{minver[1]}）",
                               f"{sys.executable} -m pip install -U {pkg}\n"
                               f"（{why}；旧版可能读不了京东的 AVIF 主图）")
                    continue
            except Exception:
                pass
        report.add(OK, f"依赖 {pkg}", f"{ver}  · {why}")

    # ---------- 3. bsk CLI ----------
    bsk = shutil.which("bsk")
    if not bsk:
        report.add(FAIL, "bsk CLI", "不在 PATH 中",
                   "Windows: " + BSK_INSTALL_PS + "\n"
                   "macOS/Linux: " + BSK_INSTALL_SH + "\n"
                   "装完重开终端再跑本脚本")
        report.add(FAIL, "bsk 守护进程", "未检测（bsk 未安装）")
        report.add(FAIL, "浏览器扩展", "未检测（bsk 未安装）")
        return
    report.add(OK, "bsk CLI", bsk)
    try:
        out = subprocess.run([bsk, "--version"], capture_output=True, text=True, timeout=20)
        ver = (out.stdout or out.stderr).strip().splitlines()
        if ver:
            report.add(OK, "bsk 版本", ver[0])
    except Exception as e:
        report.add(WARN, "bsk 版本", f"读取失败：{e}")

    # ---------- 4. bsk doctor ----------
    try:
        p = subprocess.run([bsk, "doctor"], capture_output=True, text=True,
                           timeout=60, encoding="utf-8", errors="replace")
        text = ((p.stdout or "") + "\n" + (p.stderr or ""))
    except Exception as e:
        report.add(WARN, "bsk doctor", f"执行失败：{e}")
        return

    low = text.lower()

    def _line_of(keyword: str) -> str:
        for ln in text.splitlines():
            if keyword in ln.lower():
                return " ".join(ln.split())
        return ""

    # daemon
    if "daemon running" in low:
        report.add(OK, "bsk 守护进程", _line_of("daemon running"))
    else:
        report.add(FAIL, "bsk 守护进程", "未运行",
                   "双击 start-bsk-daemon.bat，保持那个窗口开着\n"
                   "（或终端执行：bsk daemon start --port 53899）")

    # 扩展 / 浏览器
    if "extension connected" in low:
        ln = _line_of("extension connected")
        if "0 browser" in ln:
            report.add(WARN, "浏览器扩展", ln, "打开 Chrome，确认 BrowserSkill 扩展已启用并自动连接")
        else:
            report.add(OK, "浏览器扩展", ln)
    else:
        report.add(WARN, "浏览器扩展", "未检测到",
                   "在 Chrome/Edge 里安装并启用 BrowserSkill 扩展，"
                   "然后打开浏览器让它连上守护进程")

    # ---------- 5. SKU 清单 ----------
    skus = base / "skus.csv"
    example = base / "skus.example.csv"
    if skus.exists():
        n = 0
        try:
            import csv
            with skus.open(encoding="utf-8-sig", newline="") as f:
                n = sum(1 for r in csv.DictReader(f) if (r.get("sku") or "").strip())
        except Exception:
            pass
        report.add(OK, "SKU 清单 skus.csv", f"{n} 条")
    else:
        report.add(WARN, "SKU 清单 skus.csv", "不存在",
                   f"想用清单方式抓：把 {example.name} 复制成 skus.csv 再填 SKU\n"
                   "直接拖榜单 xlsx 也可以，不用 skus.csv（--from-xlsx）")

    # ---------- 6. 数据目录可写 ----------
    runs = base / "runs"
    try:
        runs.mkdir(parents=True, exist_ok=True)
        probe = runs / ".doctor_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        report.add(OK, "数据目录可写", str(runs))
    except Exception as e:
        report.add(FAIL, "数据目录可写", f"{runs} 不可写：{e}",
                   "换个有写权限的目录，或把工具放到用户目录下再试")


def main() -> int:
    _force_utf8()
    ap = argparse.ArgumentParser(description="京东SKU主图抓取 —— 环境自检")
    ap.add_argument("base", nargs="?", default=None,
                    help="工具目录（默认：脚本所在目录；技能包布局下为包根目录）")
    ap.add_argument("--quiet", action="store_true", help="只输出非 OK 项")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出（供程序/AI 消费）")
    args = ap.parse_args()

    base = Path(args.base).expanduser().resolve() if args.base else default_base()
    report = Report()
    check(report, base)

    if args.json:
        print(json.dumps({
            "base": str(base),
            "status": report.worst,
            "items": [{"level": lv, "name": n, "detail": d, "hint": h}
                      for lv, n, d, h in report.items],
        }, ensure_ascii=False, indent=2))
    else:
        report.render(quiet=args.quiet)

    return 0 if report.worst != FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
