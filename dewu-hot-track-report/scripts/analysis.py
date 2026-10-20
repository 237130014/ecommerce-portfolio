# -*- coding: utf-8 -*-
"""得物商机推荐报告 · 数据清洗与统计分析核心

职责：CSV -> 三步清洗（类目白名单 -> 国际大牌剔除 -> 热度过滤分组）-> 统计 dict。
清洗中间产物（每一步保留/剔除明细）通过 clean_pipeline 的 funnel 返回，
由 build_report.py 写入批次目录「过程记录」。

铁律（业务方 2026-09-16 确认的清洗标准，不得擅改）：
1. 类目整理：只对「机会类目」字段做白名单比对（不是「类目组」）；
   一行含多个类目（空格分隔）时任一命中即保留该行，且只有白名单内类目进入统计。
2. 大牌剔除：热点标题含国际大牌（中英文别名）的整行剔除；
   剩余行的相似机会品列表里同样删掉大牌商品。
3. 热度清洗：先按「搜索热度（近30天）」转数值降序，只留大于平均值的记录；
   再按「成交热度（近30天）」转数值降序；
   剩余记录按成交热度均值切分为「高热度，高成交」与「高热度，低成交」。
"""
import json
import re
from datetime import datetime

import pandas as pd

from domain_dict import (
    CATEGORY_WHITELIST_GOLD, CATEGORY_WHITELIST_FASHION,
    LUXURY_BRANDS, KNOWN_BRANDS, STOP_WORDS, MATERIAL_GROUPS,
    PRICE_BANDS, GROUP_HIGH, GROUP_LOW, canon_category,
)

EXPECTED_COLS = [
    "抓取日期", "类目组", "页码", "页内序号", "热点标题", "热点图链接",
    "商品信息", "卖点分析", "适用人群", "适用场景",
    "成交热度（近30天）", "搜索热度（近30天）",
    "机会类目", "机会价格", "相似机会品", "副标题",
]

# 白名单（归一化后的完整三级路径集合）
WHITELIST = {canon_category(c) for c in CATEGORY_WHITELIST_GOLD + CATEGORY_WHITELIST_FASHION}

# 大牌别名 -> 标准名（全部小写，匹配时统一 lower）
_LUXURY_ALIAS = {}
for _std, _aliases in LUXURY_BRANDS.items():
    for _a in _aliases:
        _LUXURY_ALIAS[_a.lower()] = _std

# 相似品品牌别名 -> 标准名
_BRAND_ALIAS = {}
for _std, _aliases in KNOWN_BRANDS.items():
    for _a in _aliases:
        _BRAND_ALIAS[_a.lower()] = _std


# ------------------------------------------------------------
# 基础解析
# ------------------------------------------------------------
def load_csv(path):
    """读取 CSV。必须用 utf-8-sig（文件带 BOM），全部按字符串读入。"""
    df = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    validate_columns(df)
    return df


def validate_columns(df):
    """16 列齐全校验，缺列直接报错，不静默继续。"""
    lack = [c for c in EXPECTED_COLS if c not in df.columns]
    if lack:
        raise ValueError(f"CSV 缺少必要列: {lack}")


def parse_heat(text):
    """热度文本 -> 数值。"4,849 万"->48490000；"1.2 亿"->1.2e8；"-"或空->None。"""
    m = re.match(r"([\d,\.]+)\s*(万|亿|千)?", str(text).strip())
    if not m:
        return None
    factor = {"万": 1e4, "亿": 1e8, "千": 1e3, None: 1}[m.group(2)]
    return float(m.group(1).replace(",", "")) * factor


def fmt_wan(value):
    """数值 -> 中文万单位展示。48490000 -> '4,849 万'。"""
    if value is None:
        return "-"
    if value >= 1e8:
        return f"{value / 1e8:,.2f} 亿"
    if value >= 1e4:
        return f"{value / 1e4:,.0f} 万"
    return f"{value:,.0f}"


def parse_price_ranges(text):
    """机会价格 -> [(low, high), ...]。兼容 "¥116-3825"、"¥899以下"、"¥300以下 ¥500-1000" 多段。
    无法解析或为空返回 []。"""
    s = str(text).strip()
    if not s:
        return []
    ranges = []
    for seg in re.findall(r"¥\s*[\d,]+(?:\s*-\s*[\d,]+|以下)?", s):
        m_range = re.match(r"¥\s*([\d,]+)\s*-\s*([\d,]+)", seg)
        m_cap = re.match(r"¥\s*([\d,]+)以下", seg)
        if m_range:
            ranges.append((int(m_range.group(1).replace(",", "")),
                           int(m_range.group(2).replace(",", ""))))
        elif m_cap:
            ranges.append((0, int(m_cap.group(1).replace(",", ""))))
    return ranges


def split_categories(text):
    """机会类目 -> [类目, ...]。多类目以空白分隔，逐项归一。"""
    return [canon_category(t) for t in re.split(r"\s+", str(text).strip()) if t]


def parse_goods_info(text):
    """商品信息 JSON -> dict；解析失败返回 {}（不崩溃）。"""
    try:
        d = json.loads(text)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def parse_similar(text):
    """相似机会品 JSON -> list；解析失败返回 []（不崩溃）。"""
    try:
        arr = json.loads(text)
        return arr if isinstance(arr, list) else []
    except Exception:
        return []


def split_tokens(value):
    """多值字段（材质/风格/颜色等）按分隔符拆词。"""
    return [t.strip() for t in re.split(r"[/、,，;；\s]+", str(value)) if t.strip()]


def match_luxury(text):
    """文本命中国际大牌 -> 标准品牌名；未命中 -> None。大小写不敏感。"""
    tl = str(text).lower()
    for alias, std in _LUXURY_ALIAS.items():
        if alias in tl:
            return std
    return None


def match_brand(text):
    """相似品标题 -> 竞品标准品牌名；未命中 -> None。"""
    tl = str(text).lower()
    for alias, std in _BRAND_ALIAS.items():
        if alias in tl:
            return std
    return None


def parse_case_price(text):
    """平台最低价 "￥394" -> 394；无法解析 -> None。"""
    m = re.findall(r"[\d,]+", str(text))
    return int(m[0].replace(",", "")) if m else None


# ------------------------------------------------------------
# 三步清洗流水线
# ------------------------------------------------------------
def clean_pipeline(df):
    """三步清洗。返回 (clean_df, similar_items, funnel)。

    clean_df: 最终分析集（搜索热度>均值），含派生列：
        _搜索v/_成交v/_类目hits/_价格区间/_商品信息/_热度分组
    similar_items: 清洗后的相似机会品明细 [{标题,价格,品牌,主图,所属热点,热点分组}]
    funnel: 每步保留/剔除计数与明细（写过程记录用）
    """
    funnel = {"rawRows": int(len(df)), "uniqueTitles": int(df["热点标题"].nunique())}

    # ---- Step 1 类目整理（对「机会类目」做白名单比对；任一命中即保留）----
    kept_idx, dropped_cat, cat_hits = [], [], {}
    for idx, row in df.iterrows():
        cats = split_categories(row["机会类目"])
        hits = [c for c in cats if c in WHITELIST]
        if hits:
            kept_idx.append(idx)
            cat_hits[idx] = hits
        else:
            dropped_cat.append({"热点标题": row["热点标题"], "机会类目": row["机会类目"]})
    df1 = df.loc[kept_idx].copy()
    df1["_类目hits"] = [cat_hits[i] for i in kept_idx]
    funnel["step1Category"] = {
        "kept": int(len(df1)), "dropped": len(dropped_cat),
        "whitelistSize": len(WHITELIST), "droppedItems": dropped_cat,
    }

    # ---- Step 2 国际大牌剔除（热点标题命中整行剔除；相似品里同清）----
    brand_hits = []
    keep_mask = []
    for _, row in df1.iterrows():
        hit = match_luxury(row["热点标题"])
        keep_mask.append(hit is None)
        if hit:
            brand_hits.append({"热点标题": row["热点标题"], "命中品牌": hit})
    df2 = df1[keep_mask].copy()
    funnel["step2Luxury"] = {
        "kept": int(len(df2)), "droppedHotspots": len(brand_hits),
        "droppedItems": brand_hits, "droppedSimilarCount": 0,
    }

    # ---- Step 3 热度清洗 ----
    df2["_搜索v"] = df2["搜索热度（近30天）"].map(parse_heat)
    df2["_成交v"] = df2["成交热度（近30天）"].map(parse_heat)
    search_mean = df2["_搜索v"].mean()
    df3 = df2[df2["_搜索v"] > search_mean].copy()
    df3 = df3.sort_values("_成交v", ascending=False, na_position="last")
    deal_mean = df3["_成交v"].mean()
    df3["_热度分组"] = df3["_成交v"].map(
        lambda v: GROUP_HIGH if pd.notna(v) and v >= deal_mean else
        (GROUP_LOW if pd.notna(v) else "成交数据缺失"))
    funnel["step3Heat"] = {
        "searchMean": round(float(search_mean), 1),
        "kept": int(len(df3)),
        "searchMissing": int(df2["_搜索v"].isna().sum()),
        "dealMean": round(float(deal_mean), 1) if pd.notna(deal_mean) else None,
        "highCount": int((df3["_热度分组"] == GROUP_HIGH).sum()),
        "lowCount": int((df3["_热度分组"] == GROUP_LOW).sum()),
        "dealMissingCount": int((df3["_热度分组"] == "成交数据缺失").sum()),
    }

    # ---- 相似机会品清洗（从最终分析集展开；大牌剔除；按标题去重）----
    similar, seen_titles, dropped_similar = [], set(), 0
    group_map = dict(zip(df3["热点标题"], df3["_热度分组"]))
    for _, row in df3.iterrows():
        for item in parse_similar(row["相似机会品"]):
            title = str(item.get("商品标题", "")).strip()
            if not title:
                continue
            if match_luxury(title):
                dropped_similar += 1
                continue
            if title in seen_titles:
                continue
            seen_titles.add(title)
            similar.append({
                "商品标题": title,
                "平台最低价": parse_case_price(item.get("平台最低价", "")),
                "平台最低价原文": str(item.get("平台最低价", "")),
                "品牌": match_brand(title) or "",
                "主图链接": str(item.get("主图链接", "")),
                "所属热点": row["热点标题"],
                "热点分组": group_map.get(row["热点标题"], ""),
            })
    funnel["step2Luxury"]["droppedSimilarCount"] = dropped_similar
    funnel["similarKept"] = len(similar)
    funnel["finalCount"] = int(len(df3))
    return df3, similar, funnel


# ------------------------------------------------------------
# 统计聚合
# ------------------------------------------------------------
def _top(counter, n=15):
    return [{"name": k, "count": v} for k, v in counter.most_common(n)]


def compute_stats(df, similar, funnel, source_name, week_label, capture_date):
    """在最终分析集上聚合全部报告数据。只统计有数据的维度，不捏造。"""
    from collections import Counter

    stats = {
        "meta": {
            "reportTitle": "得物商机推荐 · 市场趋势分析报告",
            "weekLabel": week_label, "captureDate": capture_date,
            "sourceFile": source_name,
            "generatedAt": datetime.now().isoformat(timespec="seconds"),
        },
        "funnel": funnel,
    }

    n = len(df)
    high = df[df["_热度分组"] == GROUP_HIGH]
    low = df[df["_热度分组"] == GROUP_LOW]

    def row_view(r):
        prices = parse_price_ranges(r["机会价格"])
        return {
            "热点标题": r["热点标题"], "副标题": r["副标题"],
            "成交热度": r["成交热度（近30天）"], "搜索热度": r["搜索热度（近30天）"],
            "_成交v": r["_成交v"], "_搜索v": r["_搜索v"],
            "机会类目": r["_类目hits"], "机会价格": r["机会价格"],
            "价格区间": prices, "热点图链接": r["热点图链接"],
            "卖点分析": r["卖点分析"], "适用人群": r["适用人群"], "适用场景": r["适用场景"],
            "热度分组": r["_热度分组"],
        }

    stats["groups"] = {
        "high": [row_view(r) for _, r in high.iterrows()],
        "low": [row_view(r) for _, r in low.iterrows()],
    }
    stats["summary"] = {
        "finalCount": int(n),
        "highCount": int(len(high)), "lowCount": int(len(low)),
        "dealSum": float(df["_成交v"].sum()),
        "searchSum": float(df["_搜索v"].sum()),
        "dealMean": funnel["step3Heat"]["dealMean"],
        "searchMean": funnel["step3Heat"]["searchMean"],
        "similarCount": len(similar),
    }

    # ---- 热门关键词（jieba 分词；词频 + 流量权重双榜）----
    import jieba
    kw_freq, kw_weight = Counter(), Counter()
    for _, r in df.iterrows():
        text = f"{r['热点标题']} {r['副标题']}"
        words = {w for w in jieba.lcut(text)
                 if len(w) >= 2 and w not in STOP_WORDS
                 and not re.fullmatch(r"[\d\W]+", w)}
        for w in words:
            kw_freq[w] += 1
            if pd.notna(r["_成交v"]):
                kw_weight[w] += r["_成交v"]
    stats["keywords"] = {"freq": _top(kw_freq, 20),
                         "weighted": [{"name": k, "weight": v} for k, v in kw_weight.most_common(20)]}

    # ---- 元素/风格/材质（商品信息 JSON；计数 + 流量加权）----
    # 注意：weighted 必须保留全量映射，渲染层再做截断；
    # 若在此截断，"计数榜"里的词在"权重榜"查不到会被错误显示为 0。
    def field_stats(field):
        cnt, weight = Counter(), Counter()
        for _, r in df.iterrows():
            info = parse_goods_info(r["商品信息"])
            tokens = set(split_tokens(info.get(field, "")))
            for t in tokens:
                cnt[t] += 1
                if pd.notna(r["_成交v"]):
                    weight[t] += r["_成交v"]
        return {"count": _top(cnt, 12),
                "weighted": [{"name": k, "weight": v} for k, v in weight.most_common()]}

    stats["elements"] = {f: field_stats(f) for f in ["材质", "风格", "颜色", "工艺", "核心功能"]}

    # 材质大类归并
    mg_cnt, mg_weight = Counter(), Counter()
    for _, r in df.iterrows():
        info = parse_goods_info(r["商品信息"])
        tokens = {t.lower() for t in split_tokens(info.get("材质", ""))}
        hit_groups = set()
        for gname, members in MATERIAL_GROUPS.items():
            if any(m.lower() in tokens for m in members):
                hit_groups.add(gname)
        for g in hit_groups:
            mg_cnt[g] += 1
            if pd.notna(r["_成交v"]):
                mg_weight[g] += r["_成交v"]
    stats["materialGroups"] = {"count": _top(mg_cnt, 10),
                               "weighted": [{"name": k, "weight": v} for k, v in mg_weight.most_common()]}

    # ---- 机会信号：场景/人群/类目/价格带 ----
    sc, pp, cat_c, cat_w = Counter(), Counter(), Counter(), Counter()
    for _, r in df.iterrows():
        for t in set(split_tokens(r["适用场景"])):
            sc[t] += 1
        for t in set(split_tokens(r["适用人群"])):
            pp[t] += 1
        for c in set(r["_类目hits"]):
            cat_c[c] += 1
            if pd.notna(r["_成交v"]):
                cat_w[c] += r["_成交v"]
    stats["signals"] = {
        "scenes": _top(sc, 12), "personas": _top(pp, 12),
        "categories": _top(cat_c, 15),
        "categoriesWeighted": [{"name": k, "weight": v} for k, v in cat_w.most_common()],
    }

    band_cnt = {b[0]: 0 for b in PRICE_BANDS}
    band_rows = {b[0]: [] for b in PRICE_BANDS}
    unpriced = 0
    for _, r in df.iterrows():
        ranges = parse_price_ranges(r["机会价格"])
        if not ranges:
            unpriced += 1
            continue
        ceiling = max(hi for _, hi in ranges)
        for bname, lo_b, hi_b in PRICE_BANDS:
            if ceiling >= lo_b and (hi_b is None or ceiling < hi_b):
                band_cnt[bname] += 1
                band_rows[bname].append(r["热点标题"])
                break
    stats["priceBands"] = {"bands": [{"name": k, "count": v} for k, v in band_cnt.items()],
                           "rows": band_rows, "unpriced": unpriced}

    # ---- 竞品格局（相似机会品品牌）----
    brand_c, brand_prices = Counter(), {}
    no_brand = 0
    for item in similar:
        if item["品牌"]:
            brand_c[item["品牌"]] += 1
            if item["平台最低价"] is not None:
                brand_prices.setdefault(item["品牌"], []).append(item["平台最低价"])
        else:
            no_brand += 1
    total_branded = sum(brand_c.values())
    cr3 = sum(v for _, v in brand_c.most_common(3)) / total_branded if total_branded else 0
    stats["brands"] = {
        "top": [{"name": k, "count": v,
                 "medianPrice": sorted(brand_prices[k])[len(brand_prices[k]) // 2] if brand_prices.get(k) else None}
                for k, v in brand_c.most_common(12)],
        "cr3": round(cr3, 3), "noBrandCount": no_brand, "totalBranded": total_branded,
    }

    # ---- 商品案例 ----
    stats["cases"] = similar

    # ---- 决策思路（只填数据支撑的维度，缺口显式标注）----
    stats["decision"] = {
        "市场容量": {
            "status": "ok",
            "evidence": f"分析集 {n} 个热点，近30天成交热度合计 {fmt_wan(stats['summary']['dealSum'])}，"
                        f"搜索热度合计 {fmt_wan(stats['summary']['searchSum'])}",
        },
        "增长趋势": {"status": "missing", "evidence": "数据未提供（仅有近30天单点快照，无历史环比）"},
        "竞争可进入性": {
            "status": "ok",
            "evidence": f"相似机会品 {len(similar)} 条，品牌 CR3 = {stats['brands']['cr3'] * 100:.0f}%"
                        f"（{'头部集中，需差异化切入' if stats['brands']['cr3'] > 0.6 else '中等集中' if stats['brands']['cr3'] > 0.3 else '分散，有机会'}）",
        },
        "利润空间": {
            "status": "partial",
            "evidence": "机会价格区间可参考（见第五章价格带分布）；采购成本数据未提供，无法测算毛利",
        },
        "供应链难度": {"status": "missing", "evidence": "数据未提供（无货源/起定量/品控信息）"},
    }

    # ---- 风险提示（每条基于真实数据）----
    top5_share = (sum(r["_成交v"] for r in stats["groups"]["high"][:5] if r["_成交v"]) /
                  stats["summary"]["dealSum"]) if stats["summary"]["dealSum"] else 0
    stats["risks"] = [
        {"风险": "热度高度右偏", "证据": f"头部 5 个热点占分析集成交热度 {top5_share * 100:.0f}%",
         "缓解": "不要只押头部款，高热低成交组（第五章）是差异化机会池"},
        {"风险": "竞品品牌集中", "证据": f"相似品品牌 CR3 = {stats['brands']['cr3'] * 100:.0f}%",
         "缓解": "避开头部品牌正面价格带，从设计元素/场景细分切入"},
        {"风险": "场景集中送礼", "证据": f"适用场景 TOP1「{stats['signals']['scenes'][0]['name']}」"
                                       f"覆盖 {stats['signals']['scenes'][0]['count']}/{n} 个热点",
         "缓解": "送礼场景有强季节波动，搭配日常佩戴场景做平销款"},
        {"风险": "样本与平台局限", "证据": "单周快照、仅得物平台、国际大牌已按规则剔除",
         "缓解": "与天猫生意参谋、京东新品监控周报交叉验证后再定开款"},
    ]
    return stats
