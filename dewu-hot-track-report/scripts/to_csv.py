# -*- coding: utf-8 -*-
"""把 scrape.py 捕获的接口响应转成「商机推荐分析报告」要求的 16 列标准 CSV。

16 列标准字段（顺序与下游 analysis.py 的列名约定一致）：
    抓取日期 / 类目组 / 页码 / 页内序号 / 热点标题 / 热点图链接 / 商品信息 /
    卖点分析 / 适用人群 / 适用场景 / 成交热度（近30天）/ 搜索热度（近30天）/
    机会类目 / 机会价格 / 相似机会品 / 副标题
其后追加 8 列接口原始字段（环比、连涨周数、社区热度、热门搜索、排名、主图、trackId），
供交叉核对与「增长趋势」章节使用。

用法：
    python to_csv.py --data-dir runs/2026-10-20/data --out runs/2026年10月第四周-2026-10-20
"""
import argparse
import csv
import datetime as dt
import glob
import json
import os

CN_DIGITS = "零一二三四五六七八九十"

STD_COLUMNS = [
    "抓取日期", "类目组", "页码", "页内序号", "热点标题", "热点图链接", "商品信息",
    "卖点分析", "适用人群", "适用场景", "成交热度（近30天）", "搜索热度（近30天）",
    "机会类目", "机会价格", "相似机会品", "副标题",
]
EXTRA_COLUMNS = [
    "社区热度（近30天）", "搜索环比", "成交环比", "搜索连涨周数", "热门搜索",
    "组内排名", "主图链接", "trackId",
]


def week_of_month(d):
    """按周一为一周起点、含当月 1 日的那周算第 1 周。"""
    first = d.replace(day=1)
    return (d.day + first.weekday() - 1) // 7 + 1


def week_label(d):
    """返回周目录名，如 2026年10月第四周-2026年10月20日。"""
    n = week_of_month(d)
    cn = CN_DIGITS[n] if n <= 10 else str(n)
    return "%d年%d月第%s周-%d年%d月%d日" % (d.year, d.month, cn, d.year, d.month, d.day)


def _spu_list(items):
    out = []
    for s in items or []:
        mp = s.get("minPrice")
        price = ""
        if isinstance(mp, (int, float)):
            price = "￥%.0f" % (mp / 100.0)
        elif isinstance(mp, str) and mp.strip():
            price = "￥" + mp.strip()
        out.append({
            "商品标题": s.get("productName", ""),
            "平台最低价": price,
            "主图链接": s.get("productImageUrl", ""),
        })
    return out


def rows_from_pages(payload, capture_date, label_override=None):
    label = label_override or payload.get("label") or payload.get("group") or ""
    rows, seen = [], set()
    for pn in sorted(payload.get("pages", {}), key=lambda x: int(x)):
        try:
            contents = json.loads(payload["pages"][pn]["resp"])["data"]["contents"]
        except Exception:
            continue
        for i, it in enumerate(contents, 1):
            tid = it.get("trackId")
            key = (label, tid, it.get("trackName"))
            if key in seen:
                continue
            seen.add(key)
            td = it.get("trackDescNew") or {}
            rows.append({
                "抓取日期": capture_date,
                "类目组": label,
                "页码": pn,
                "页内序号": i,
                "热点标题": it.get("trackName", ""),
                "热点图链接": it.get("bannerImg", ""),
                "商品信息": json.dumps(td.get("commodityInfo") or {}, ensure_ascii=False),
                "卖点分析": td.get("sellingPoint", ""),
                "适用人群": td.get("suitableCrowd", ""),
                "适用场景": td.get("suitableScene", ""),
                "成交热度（近30天）": it.get("transactionHeat", ""),
                "搜索热度（近30天）": it.get("searchHeat", ""),
                "机会类目": " ".join(it.get("categoryNameList") or []),
                "机会价格": " ".join(it.get("chancePriceSegment") or []),
                "相似机会品": json.dumps(_spu_list(it.get("spuList")), ensure_ascii=False),
                "副标题": it.get("recommendReason", ""),
                "社区热度（近30天）": it.get("communityHeat", ""),
                "搜索环比": it.get("searchHeatQoq", ""),
                "成交环比": it.get("transactionHeatQoq", ""),
                "搜索连涨周数": it.get("searchHeatGrowthWeeks", 0),
                "热门搜索": " ".join(it.get("hotSearchList") or []),
                "组内排名": it.get("rankNum", ""),
                "主图链接": it.get("headImg", ""),
                "trackId": tid if tid is not None else "",
            })
    return rows


def build(data_dir, out_dir, capture_date=None, group_labels=None, quiet=False):
    files = sorted(glob.glob(os.path.join(data_dir, "cap_*.json")))
    if not files:
        raise SystemExit("在 %s 下没有找到 cap_*.json，先跑 scrape.py" % data_dir)

    if not capture_date:
        # 优先用抓取当天日期，其次文件时间
        capture_date = dt.date.today().strftime("%Y-%m-%d")

    rows = []
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            payload = json.load(f)
        label = (group_labels or {}).get(payload.get("group"))
        rows.extend(rows_from_pages(payload, capture_date, label))

    if not rows:
        raise SystemExit("捕获的响应里没有可用条目，检查接口是否变了")

    outdir = os.path.join(out_dir, "原始数据")
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, "得物商机推荐_%s.csv" % capture_date)
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=STD_COLUMNS + EXTRA_COLUMNS)
        w.writeheader()
        w.writerows(rows)

    if not quiet:
        from collections import Counter
        print("条目 %d -> %s" % (len(rows), out))
        for k, v in Counter(r["类目组"] for r in rows).items():
            print("  %-22s %d" % (k, v))
        print("  带相似机会品 %d 条" % sum(1 for r in rows if r["相似机会品"] != "[]"))
    return out, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True, help="scrape.py 的 <out>/data")
    ap.add_argument("--out", required=True, help="周目录（其下自动建 原始数据/）")
    ap.add_argument("--capture-date", default="", help="抓取日期 YYYY-MM-DD，默认今天")
    ap.add_argument("--labels", default="", help='组名覆盖，如 "A=流行饰品/眼镜/服配,B=黄金/珠宝/翡翠/玉石"')
    args = ap.parse_args()

    labels = {}
    for part in args.labels.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            labels[k.strip()] = v.strip()

    build(args.data_dir, args.out, args.capture_date or None, labels)


if __name__ == "__main__":
    main()
