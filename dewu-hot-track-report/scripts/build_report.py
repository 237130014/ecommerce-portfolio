# -*- coding: utf-8 -*-
"""编排：接口数据 → 16 列 CSV → 清洗漏斗 → 八章分析报告（MD + HTML）。

    python build_report.py --data-dir runs/2026-10-20/data --week-dir runs/2026年10月第四周-2026-10-20
    python build_report.py --csv <已有CSV> --week-dir <周目录>       # 跳过抓取数据转换

产出：
    <周目录>/原始数据/得物商机推荐_<date>.csv
    <周目录>/分析报告/得物商机推荐市场趋势分析报告-<周标签>.{md,html}
    <周目录>/分析报告/assets/*.jpg
    <周目录>/过程记录/clean_funnel.json
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import to_csv as tcsv  # noqa: E402
from analysis import load_csv, clean_pipeline, compute_stats  # noqa: E402
from render_report import render_md, render_html  # noqa: E402

REPORT_PREFIX = "得物商机推荐市场趋势分析报告"


def derive_week_label(path_or_name):
    """从周目录名推周标签：'2026年10月第四周-2026年10月20日' -> '2026年10月第四周'。"""
    name = os.path.basename(os.path.normpath(path_or_name))
    m = re.match(r"^(\d{4}年\d{1,2}月第[零一二三四五六七八九十\d]{1,3}周)", name)
    if m:
        return m.group(1)
    return name.rsplit("-", 1)[0]


def download_hotspot_images(stats, out_dir):
    assets_dir = os.path.join(out_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Referer": "https://www.dewu.com/",
    }
    idx = ok = fail = skip = 0
    for grp in ("high", "low"):
        for r in stats["groups"][grp]:
            url = (r.get("热点图链接") or "").strip()
            if not url:
                skip += 1
                continue
            idx += 1
            ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
            if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                ext = ".jpg"
            fname = "hotspot_%03d%s" % (idx, ext)
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = resp.read()
                with open(os.path.join(assets_dir, fname), "wb") as fp:
                    fp.write(data)
                r["热点图链接"] = "assets/%s" % fname
                ok += 1
            except Exception as e:  # noqa: BLE001
                fail += 1
                print("  [热点图] 失败 #%d: %s" % (idx, e))
    print("热点图：成功 %d / 失败 %d / 无链接 %d" % (ok, fail, skip))


def patch_growth(df, stats):
    """用接口原始环比字段填「增长趋势」，避免报告写「数据未提供」。"""
    def asnum(v):
        try:
            return float(str(v).replace(",", "").strip())
        except Exception:
            return None

    s_vals, d_vals, weeks = [], [], []
    for _, r in df.iterrows():
        s, d, w = asnum(r.get("搜索环比", "")), asnum(r.get("成交环比", "")), asnum(r.get("搜索连涨周数", ""))
        if s is not None:
            s_vals.append(s / 100.0)
        if d is not None:
            d_vals.append(d / 100.0)
        if w:
            weeks.append(w)

    if not s_vals:
        return
    n = len(df)
    up = sum(1 for v in s_vals if v > 0)
    avg_s = sum(s_vals) / len(s_vals)
    avg_d = (sum(d_vals) / len(d_vals)) if d_vals else None
    ge2 = sum(1 for w in weeks if w >= 2)
    ge3 = sum(1 for w in weeks if w >= 3)
    ev = ("分析集 %d 个热点中 %d 个有搜索环比数据，均值 %+.1f%%，其中 %d 个为正增长；"
          "搜索连涨 ≥2 周 %d 个、≥3 周 %d 个" % (n, len(s_vals), avg_s, up, ge2, ge3))
    if avg_d is not None:
        ev += "；%d 个有成交环比数据，均值 %+.1f%%" % (len(d_vals), avg_d)
    ev += "。详见 CSV 附加字段（搜索环比/成交环比/搜索连涨周数）"
    stats["decision"]["增长趋势"] = {"status": "ok", "evidence": ev}
    print("增长趋势：", ev)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="", help="已有的 16 列 CSV（给了就跳过接口转换）")
    ap.add_argument("--data-dir", default="", help="scrape.py 的 <out>/data")
    ap.add_argument("--week-dir", default="", help="周目录；不给则按 --base + 抓取日期自动建")
    ap.add_argument("--base", default="./dewu-runs", help="周目录的父目录（默认 ./dewu-runs）")
    ap.add_argument("--capture-date", default="", help="抓取日期 YYYY-MM-DD，默认今天")
    ap.add_argument("--no-images", action="store_true", help="不下载热点图")
    args = ap.parse_args()

    capture_date = args.capture_date or dt.date.today().strftime("%Y-%m-%d")
    if args.csv and not args.capture_date and not args.week_dir:
        # 没给日期也没给周目录时，从 CSV 里读抓取日期，保证目录落到正确的一周
        try:
            import csv as _csv
            with open(args.csv, encoding="utf-8-sig") as fp:
                first = next(_csv.DictReader(fp))
            if first.get("抓取日期"):
                capture_date = str(first["抓取日期"]).strip()
        except Exception:
            pass
    week_dir = args.week_dir or os.path.join(args.base, tcsv.week_label(
        dt.datetime.strptime(capture_date, "%Y-%m-%d").date()))
    week_label = derive_week_label(week_dir)
    out_dir = os.path.join(week_dir, "分析报告")
    proc_dir = os.path.join(week_dir, "过程记录")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(proc_dir, exist_ok=True)

    if args.csv:
        csv_path = args.csv
    else:
        if not args.data_dir:
            raise SystemExit("要么给 --csv，要么给 --data-dir")
        csv_path, _ = tcsv.build(args.data_dir, week_dir, args.capture_date or None)

    print("周目录:", week_dir)
    print("数据文件:", csv_path)

    df = load_csv(csv_path)
    clean_df, similar, funnel = clean_pipeline(df)
    print("清洗漏斗: 原始 %s -> 类目 %s -> 大牌 %s -> 热度 %s（高成交 %s / 低成交 %s）" % (
        funnel["rawRows"], funnel["step1Category"]["kept"], funnel["step2Luxury"]["kept"],
        funnel["step3Heat"]["kept"], funnel["step3Heat"]["highCount"], funnel["step3Heat"]["lowCount"]))

    capture_date = df["抓取日期"].iloc[0] if "抓取日期" in df.columns else ""
    stats = compute_stats(clean_df, similar, funnel, os.path.basename(csv_path), week_label, capture_date)

    patch_growth(clean_df, stats)
    if not args.no_images:
        download_hotspot_images(stats, out_dir)

    funnel_path = os.path.join(proc_dir, "clean_funnel.json")
    with open(funnel_path, "w", encoding="utf-8") as fp:
        json.dump({"sourceCsv": csv_path, "weekLabel": week_label,
                   "generatedAt": stats["meta"]["generatedAt"], **funnel}, fp,
                  ensure_ascii=False, indent=2)
    print("过程记录:", funnel_path)

    md = render_md(stats)
    html = render_html(stats)
    md_path = os.path.join(out_dir, "%s-%s.md" % (REPORT_PREFIX, week_label))
    html_path = os.path.join(out_dir, "%s-%s.html" % (REPORT_PREFIX, week_label))
    with open(md_path, "w", encoding="utf-8") as fp:
        fp.write(md)
    with open(html_path, "w", encoding="utf-8") as fp:
        fp.write(html)

    assert os.path.getsize(md_path) > 0 and os.path.getsize(html_path) > 0, "报告为空"
    assert funnel["finalCount"] > 0, "最终分析集为空，检查清洗规则与热度阈值"

    print("\n=== 完成 ===")
    print("MD   :", md_path)
    print("HTML :", html_path)
    print("分析集 %d 热点 | 相似机会品 %d 条" % (funnel["finalCount"], len(similar)))


if __name__ == "__main__":
    main()
