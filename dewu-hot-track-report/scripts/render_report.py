# -*- coding: utf-8 -*-
"""得物商机推荐报告 · 双格式渲染层

render_md(stats)   -> Markdown 文本
render_html(stats) -> 自包含 HTML（CSS/JS 全内联，无 CDN；仅商品主图用外链 src）

铁律：
- 所有数字必须来自 stats dict，禁止在模板里写死任何批次数值。
- JSON 注入防 </script>：json.dumps(...).replace("</", "<\\/")。
- 数据未提供的维度必须显式标注「数据未提供」，不得填估算值。
"""
import json

from analysis import fmt_wan
from domain_dict import CASE_PRICE_BANDS, GROUP_HIGH, GROUP_LOW


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _band_of(price):
    if price is None:
        return ""
    for name, lo, hi in CASE_PRICE_BANDS:
        if price >= lo and (hi is None or price < hi):
            return name
    return ""


def _bar_rows(items, max_count, unit="款"):
    rows = []
    for it in items:
        pct = round(it["count"] / max_count * 100, 1) if max_count else 0
        rows.append(
            f'<div class="brow"><span class="blabel">{esc(it["name"])}</span>'
            f'<span class="btrack"><span class="bfill" style="width:{pct}%"></span></span>'
            f'<span class="bval">{it["count"]} {unit}</span></div>')
    return "".join(rows)


def _heat_bar_rows(items, max_w):
    rows = []
    for it in items:
        pct = round(it["weight"] / max_w * 100, 1) if max_w else 0
        rows.append(
            f'<div class="brow"><span class="blabel">{esc(it["name"])}</span>'
            f'<span class="btrack"><span class="bfill gold" style="width:{pct}%"></span></span>'
            f'<span class="bval">{fmt_wan(it["weight"])}</span></div>')
    return "".join(rows)


# ============================================================
# Markdown
# ============================================================
def render_md(s):
    m = s["meta"]
    f = s["funnel"]
    sm = s["summary"]
    out = []
    out.append(f"# {m['reportTitle']}")
    out.append("")
    out.append(f"- 周期：{m['weekLabel']}（抓取日期：{m['captureDate']}）")
    out.append(f"- 数据来源：{m['sourceFile']}")
    out.append(f"- 报告生成时间：{m['generatedAt']}")
    out.append("")
    out.append("> 本报告仅基于得物商家后台商机推荐数据生成；数据未提供的维度一律标注「数据未提供」，不做估算。")
    out.append("")

    # 一、执行摘要
    out.append("## 一、执行摘要")
    out.append("")
    hi = s["groups"]["high"]
    lo = s["groups"]["low"]
    top3 = "、".join(f"「{r['热点标题']}」" for r in (hi + lo)[:3])
    out.append(f"原始数据 {f['rawRows']} 条，经类目白名单（保留 {f['step1Category']['kept']} 条）、"
               f"国际大牌剔除（热点行 {f['step2Luxury']['droppedHotspots']} 条、相似品 "
               f"{f['step2Luxury']['droppedSimilarCount']} 条）、搜索热度均值过滤"
               f"（>{fmt_wan(f['step3Heat']['searchMean'])}）三步清洗后，"
               f"最终分析集 **{sm['finalCount']} 个热点**："
               f"**{GROUP_HIGH} {sm['highCount']} 个**、**{GROUP_LOW} {sm['lowCount']} 个**。")
    out.append("")
    out.append(f"热度 TOP3：{top3}。分析集近30天成交热度合计 {fmt_wan(sm['dealSum'])}、"
               f"搜索热度合计 {fmt_wan(sm['searchSum'])}；相似机会品 {sm['similarCount']} 条可供选品参考。")
    out.append("")
    out.append("**一句话结论**：见第六章决策思路——头部款验证需求，「高热度低成交」组是未被满足机会的挖掘池。")
    out.append("")

    # 二、热点横向对比
    out.append("## 二、热点横向对比")
    out.append("")
    out.append(f"### 2.1 {GROUP_HIGH}（成交热度 ≥ 均值 {fmt_wan(f['step3Heat']['dealMean'])}）")
    out.append("")
    out.append("| 排名 | 热点标题 | 成交热度 | 搜索热度 | 机会类目 | 机会价格 | 分组 | 热点图 |")
    out.append("|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(hi, 1):
        cats = "；".join(c.split(">")[-1] for c in r["机会类目"])
        img = r.get("热点图链接") or ""
        img_md = f"![热点图]({img})" if img else "-"
        out.append(f"| {i} | {r['热点标题']} | {r['成交热度']} | {r['搜索热度']} | {cats} | {r['机会价格'] or '-'} | {r['热度分组']} | {img_md} |")
    out.append("")
    out.append(f"### 2.2 {GROUP_LOW}（成交热度 < 均值，潜在未满足机会）")
    out.append("")
    out.append("| 排名 | 热点标题 | 成交热度 | 搜索热度 | 机会类目 | 机会价格 | 分组 | 热点图 |")
    out.append("|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(lo, 1):
        cats = "；".join(c.split(">")[-1] for c in r["机会类目"])
        img = r.get("热点图链接") or ""
        img_md = f"![热点图]({img})" if img else "-"
        out.append(f"| {i} | {r['热点标题']} | {r['成交热度']} | {r['搜索热度']} | {cats} | {r['机会价格'] or '-'} | {r['热度分组']} | {img_md} |")
    out.append("")

    # 三、热门关键词
    out.append("## 三、热门关键词")
    out.append("")
    out.append("统计口径：对热点标题 + 副标题做 jieba 分词，去除通用品类词/材质词；"
               "「流量权重」= 含该词热点的成交热度之和。")
    out.append("")
    out.append("| 排名 | 关键词（按词频） | 出现热点数 | 关键词（按流量权重） | 流量权重 |")
    out.append("|---|---|---|---|---|")
    kf, kw = s["keywords"]["freq"], s["keywords"]["weighted"]
    for i in range(max(len(kf), len(kw))):
        a = kf[i] if i < len(kf) else {"name": "", "count": ""}
        b = kw[i] if i < len(kw) else {"name": "", "weight": None}
        out.append(f"| {i + 1} | {a['name']} | {a['count']} | {b['name']} | {fmt_wan(b['weight']) if b['weight'] else ''} |")
    out.append("")
    out.append("提示：「轻奢 / 小众 / 高级感」类词若出现，属于行业标配而非差异化卖点；"
               "差异化应从上表具象元素词（造型/寓意/材质特征）中找。")
    out.append("")

    # 四、元素 / 风格 / 材质
    out.append("## 四、元素 / 风格 / 材质三大趋势拆解")
    out.append("")
    out.append("统计口径：解析「商品信息」JSON，多值字段拆分计数；流量权重 = 含该词热点的成交热度之和。")
    out.append("")
    mg = s["materialGroups"]
    out.append("### 4.1 材质大类（归并视图）")
    out.append("")
    out.append("| 材质大类 | 覆盖热点数 | 流量权重 |")
    out.append("|---|---|---|")
    wm = {x["name"]: x["weight"] for x in mg["weighted"]}
    for it in mg["count"]:
        out.append(f"| {it['name']} | {it['count']} | {fmt_wan(wm.get(it['name'], 0))} |")
    out.append("")
    for label, key in [("4.2 材质（原始词 TOP12）", "材质"), ("4.3 风格 TOP12", "风格"),
                       ("4.4 颜色 TOP12", "颜色"), ("4.5 工艺 TOP12", "工艺"),
                       ("4.6 核心功能 TOP12", "核心功能")]:
        out.append(f"### {label}")
        out.append("")
        out.append("| 关键词 | 出现热点数 | 流量权重 |")
        out.append("|---|---|---|")
        el = s["elements"][key]
        wm2 = {x["name"]: x["weight"] for x in el["weighted"]}
        for it in el["count"]:
            out.append(f"| {it['name']} | {it['count']} | {fmt_wan(wm2.get(it['name'], 0))} |")
        out.append("")

    # 五、机会信号
    out.append("## 五、机会信号：场景 / 人群 / 类目 / 价格带")
    out.append("")
    sig = s["signals"]
    out.append("### 5.1 适用场景 TOP12")
    out.append("")
    out.append("| 场景 | 覆盖热点数 |")
    out.append("|---|---|")
    for it in sig["scenes"]:
        out.append(f"| {it['name']} | {it['count']} |")
    out.append("")
    out.append("### 5.2 适用人群 TOP12")
    out.append("")
    out.append("| 人群 | 覆盖热点数 |")
    out.append("|---|---|")
    for it in sig["personas"]:
        out.append(f"| {it['name']} | {it['count']} |")
    out.append("")
    out.append("### 5.3 机会类目分布（白名单内）")
    out.append("")
    out.append("| 机会类目 | 热点数 | 流量权重 |")
    out.append("|---|---|---|")
    cw = {x["name"]: x["weight"] for x in sig["categoriesWeighted"]}
    for it in sig["categories"]:
        out.append(f"| {it['name']} | {it['count']} | {fmt_wan(cw.get(it['name'], 0))} |")
    out.append("")
    out.append("### 5.4 机会价格带分布（按区间上界归类）")
    out.append("")
    out.append("| 价格带 | 热点数 | 覆盖热点 |")
    out.append("|---|---|---|")
    for b in s["priceBands"]["bands"]:
        rows = "、".join(s["priceBands"]["rows"][b["name"]][:8]) or "-"
        out.append(f"| {b['name']} | {b['count']} | {rows} |")
    if s["priceBands"]["unpriced"]:
        out.append(f"| 价格数据缺失 | {s['priceBands']['unpriced']} | - |")
    out.append("")

    # 六、决策思路
    out.append("## 六、新品开发决策思路")
    out.append("")
    out.append("采用五维评估框架；数据未提供的维度显式标注，不做估算：")
    out.append("")
    out.append("| 评估维度 | 数据支撑 | 结论 |")
    out.append("|---|---|---|")
    status_map = {"ok": "✅ 有数据", "partial": "⚠️ 部分", "missing": "⛔ 数据未提供"}
    for dim, d in s["decision"].items():
        out.append(f"| {dim} | {status_map[d['status']]} | {d['evidence']} |")
    out.append("")
    out.append("### 下一步行动清单")
    out.append("")
    hi3 = "、".join(f"「{r['热点标题']}」" for r in hi[:3])
    lo3 = "、".join(f"「{r['热点标题']}」" for r in lo[:3])
    mat1 = mg["count"][0]["name"] if mg["count"] else "-"
    sc1 = sig["scenes"][0]["name"] if sig["scenes"] else "-"
    out.append(f"1. **验证头部需求**：拆解 {hi3} 的相似机会品（第七章），确认可进入的价格带与差异化点；")
    out.append(f"2. **挖掘未满足机会**：{lo3} 搜索热度高但成交低，排查是供给不足还是转化问题，优先打样；")
    out.append(f"3. **材质/场景卡位**：主力材质方向「{mat1}」，主力场景「{sc1}」，新品开发围绕其做组合；")
    out.append(f"4. **规避正面竞争**：相似品品牌 CR3 = {s['brands']['cr3'] * 100:.0f}%，避开头部品牌主销价格段；")
    out.append("5. **交叉验证**：本报告为得物单平台单周快照，与天猫生意参谋、京东新品监控周报对齐后再定开款。")
    out.append("")

    # 七、商品案例
    out.append("## 七、商品案例：相似机会品库")
    out.append("")
    out.append(f"共 {len(s['cases'])} 条（已剔除国际大牌、按标题去重）。完整交互筛选见 HTML 版报告。")
    out.append("")
    out.append("| 商品标题 | 平台最低价 | 品牌 | 所属热点 | 热点分组 |")
    out.append("|---|---|---|---|---|")
    priced = [c for c in s["cases"] if c["平台最低价"] is not None]
    for c in priced[:40]:
        out.append(f"| {c['商品标题'][:38]} | {c['平台最低价原文']} | {c['品牌'] or '-'} | {c['所属热点']} | {c['热点分组']} |")
    if len(priced) > 40:
        out.append(f"| …… 其余 {len(priced) - 40} 条见 HTML 版 | | | | |")
    out.append("")

    # 八、风险提示与数据口径
    out.append("## 八、风险提示与数据口径")
    out.append("")
    out.append("| 风险 | 数据证据 | 缓解建议 |")
    out.append("|---|---|---|")
    for r in s["risks"]:
        out.append(f"| {r['风险']} | {r['证据']} | {r['缓解']} |")
    out.append("")
    out.append("### 清洗漏斗（本次报告的数据边界）")
    out.append("")
    out.append("| 步骤 | 规则 | 保留 | 剔除 |")
    out.append("|---|---|---|---|")
    out.append(f"| 原始数据 | - | {f['rawRows']} 条 | - |")
    out.append(f"| 1. 类目整理 | 机会类目命中白名单（{f['step1Category']['whitelistSize']} 条）即保留 | "
               f"{f['step1Category']['kept']} | {f['step1Category']['dropped']} |")
    out.append(f"| 2. 大牌剔除 | 热点标题含 30 个国际大牌中英文别名 | {f['step2Luxury']['kept']} | "
               f"{f['step2Luxury']['droppedHotspots']}（另清相似品 {f['step2Luxury']['droppedSimilarCount']} 条）|")
    out.append(f"| 3. 热度过滤 | 搜索热度 > 均值 {fmt_wan(f['step3Heat']['searchMean'])} | {f['step3Heat']['kept']} | "
               f"{f['step2Luxury']['kept'] - f['step3Heat']['kept']} |")
    out.append(f"| 分组 | 成交热度 ≥ 均值 {fmt_wan(f['step3Heat']['dealMean'])} → {GROUP_HIGH} | "
               f"{f['step3Heat']['highCount']} + {f['step3Heat']['lowCount']} | - |")
    out.append("")
    out.append("### 数据来源与免责")
    out.append("")
    out.append(f"- 数据文件：{m['sourceFile']}（抓取日期 {m['captureDate']}，得物商家后台「查看更多类目热点」）")
    out.append("- 热度为得物平台给出的近30天指标，非销量/销售额绝对值；报告仅供新品开发选品参考，不构成经营承诺。")
    out.append("- 国际大牌已按业务规则剔除；剔除明细见批次目录「过程记录/clean_funnel.json」。")
    out.append("")
    return "\n".join(out)


# ============================================================
# HTML
# ============================================================
CSS = """
:root{
  --ink:#17202b; --ink2:#54607a; --ink3:#8a94a6; --line:#e6e9f0; --bg:#f4f6fa; --card:#fff;
  --brand:#0e7fd6; --brand2:#12b5d8; --gold:#b8860b; --gold-soft:#fdf6e3;
  --green:#0f8a4d; --green-soft:#e7f6ee; --amber:#b45309; --amber-soft:#fdf2e3;
  --red:#c0392b; --red-soft:#fdecea;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.7 "Microsoft YaHei","PingFang SC",Arial,sans-serif}
.hero{background:linear-gradient(135deg,#0b3c5d 0%,#0e7fd6 60%,#12b5d8 100%);color:#fff;padding:42px 24px 34px}
.hero-inner,.page{max-width:1080px;margin:auto}
.eyebrow{font-size:12px;letter-spacing:2px;color:#aee3ff;font-weight:700}
.hero h1{margin:6px 0 10px;font-size:30px;line-height:1.25}
.hero p{margin:0 0 16px;color:#d7ecff;max-width:820px}
.chips{display:flex;flex-wrap:wrap;gap:10px}
.chip{background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.28);border-radius:999px;padding:6px 14px;font-size:13px}
.chip b{font-size:16px;margin-right:4px}
nav{position:sticky;top:0;z-index:9;background:#fff;border-bottom:1px solid var(--line)}
.nav-inner{max-width:1080px;margin:auto;display:flex;flex-wrap:wrap;gap:2px 6px;padding:8px 16px}
nav a{color:var(--ink2);text-decoration:none;font-size:12.5px;padding:5px 9px;border-radius:6px}
nav a:hover{background:var(--bg);color:var(--brand)}
.page{padding:20px 16px 40px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px 24px;margin:18px 0}
h2{margin:0 0 14px;font-size:20px;border-left:5px solid var(--brand);padding-left:12px}
h3{margin:20px 0 8px;font-size:15.5px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#f0f3f8;text-align:left;padding:8px 10px;border-bottom:2px solid var(--line);white-space:nowrap}
td{padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tr.hl td{background:var(--gold-soft)}
.summary{background:var(--gold-soft);border-left:5px solid var(--gold);padding:14px 16px;border-radius:0 10px 10px 0;margin:10px 0}
.note{color:var(--ink2);font-size:12.5px;background:#f0f3f8;border-radius:8px;padding:10px 14px;margin:10px 0}
.tag{display:inline-block;border-radius:999px;padding:2px 10px;font-size:12px;margin:1px 2px;background:#eaf2fb;color:#1259a0}
.tag-hi{background:var(--green-soft);color:var(--green)}
.tag-lo{background:var(--amber-soft);color:var(--amber)}
.tag-gold{background:var(--gold-soft);color:var(--gold)}
.brow{display:flex;align-items:center;gap:10px;margin:5px 0}
.blabel{flex:0 0 200px;font-size:12.5px;color:var(--ink2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.btrack{flex:1;height:14px;background:#eef1f6;border-radius:7px;overflow:hidden}
.bfill{display:block;height:100%;background:var(--brand);border-radius:7px}
.bfill.gold{background:var(--gold)}
.bval{flex:0 0 86px;text-align:right;font-size:12.5px;color:var(--ink2);font-variant-numeric:tabular-nums}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.funnel{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:12px 0}
.fstep{background:#f0f3f8;border-radius:10px;padding:12px;text-align:center}
.fstep b{display:block;font-size:22px;color:var(--brand)}
.fstep span{font-size:12px;color:var(--ink2)}
.fstep.loss b{color:var(--red)}
.case-filters{display:flex;flex-wrap:wrap;gap:10px;margin:0 0 14px}
.case-filters select,.case-filters input{padding:7px 10px;border:1px solid var(--line);border-radius:8px;font-size:13px;background:#fff;color:var(--ink)}
.case-filters input{flex:1;min-width:180px}
.case-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.case-card{border:1px solid var(--line);border-radius:12px;overflow:hidden;background:#fff;display:flex;flex-direction:column}
.case-card img{width:100%;aspect-ratio:1/1;object-fit:cover;background:#f0f3f8}
.case-body{padding:10px 12px;display:flex;flex-direction:column;gap:5px;flex:1}
.case-title{font-size:12.5px;line-height:1.45;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.case-meta{margin-top:auto;display:flex;justify-content:space-between;align-items:center;font-size:12px;color:var(--ink2)}
.case-price{color:var(--red);font-weight:700;font-size:14px}
.case-count{color:var(--ink2);font-size:12.5px;margin:0 0 10px}
.hotspot-list{display:flex;flex-direction:column;gap:14px;margin-top:8px}
.hotspot-card{border:1px solid var(--line);border-radius:12px;overflow:hidden;background:#fff}
.hotspot-card.tag-hi{border-top:4px solid var(--green)}
.hotspot-card.tag-lo{border-top:4px solid var(--amber)}
.hotspot-head{padding:12px 16px 10px}
.hotspot-title{font-size:15px;font-weight:700;line-height:1.4;display:flex;gap:8px;align-items:baseline}
.hotspot-rank{flex:0 0 auto;font-size:12px;color:var(--ink3);font-variant-numeric:tabular-nums}
.hotspot-fields{display:flex;flex-wrap:wrap;gap:6px 18px;margin-top:8px;font-size:13px;color:var(--ink2)}
.hotspot-fields .hf b{color:var(--ink);font-weight:600;margin-right:4px}
.hotspot-fields .hf .v{color:var(--ink)}
.hotspot-fields .hf .v.deal{color:var(--red);font-weight:700}
.hotspot-img{width:100%;display:block;background:#f0f3f8;border-top:1px solid var(--line)}
.hotspot-img-fail{display:none;padding:18px 16px;color:var(--ink2);font-size:13px;background:#f0f3f8;border-top:1px solid var(--line)}
.hotspot-img-fail a{color:var(--brand)}
.hotspot-card.img-failed .hotspot-img{display:none}
.hotspot-card.img-failed .hotspot-img-fail{display:block}
footer{color:var(--ink3);font-size:12px;text-align:center;padding:22px 0 30px}
@media(max-width:900px){.case-grid{grid-template-columns:repeat(3,1fr)}.funnel{grid-template-columns:repeat(3,1fr)}}
@media(max-width:640px){.grid2{grid-template-columns:1fr}.case-grid{grid-template-columns:repeat(2,1fr)}.blabel{flex-basis:120px}}
"""

JS = """
const q = s => document.querySelector(s);
const cards = () => Array.from(document.querySelectorAll('.case-card'));
function applyFilters(){
  const brand = q('#f-brand').value, band = q('#f-band').value,
        grp = q('#f-group').value, kw = q('#f-kw').value.trim().toLowerCase();
  let n = 0;
  cards().forEach(c => {
    const ok = (!brand || c.dataset.brand === brand)
      && (!band || c.dataset.band === band)
      && (!grp || c.dataset.group === grp)
      && (!kw || c.dataset.search.includes(kw));
    c.style.display = ok ? '' : 'none';
    if (ok) n++;
  });
  q('#case-count').textContent = '当前显示 ' + n + ' / ' + cards().length + ' 条';
}
['f-brand','f-band','f-group'].forEach(id => q('#'+id).addEventListener('change', applyFilters));
q('#f-kw').addEventListener('input', applyFilters);
"""


def render_html(s):
    m = s["meta"]
    f = s["funnel"]
    sm = s["summary"]
    hi = s["groups"]["high"]
    lo = s["groups"]["low"]
    sig = s["signals"]
    mg = s["materialGroups"]

    def heat_cards(rows, tag):
        # 一行一个热点卡；字段全量默认展开，下方展示热点长图
        cards = []
        for i, r in enumerate(rows, 1):
            cats = "；".join(c.split(">")[-1] for c in r["机会类目"])
            price = r["机会价格"] or "-"
            img = esc(r.get("热点图链接", "") or "")
            if img:
                img_html = (
                    f"<img class='hotspot-img' loading='lazy' referrerpolicy='no-referrer' "
                    f"src='{img}' alt='热点图' "
                    f"onerror=\"this.parentElement.classList.add('img-failed')\">"
                    f"<div class='hotspot-img-fail'>热点图加载失败（CDN / 登录态 / 防盗链原因），"
                    f"<a href='{img}' target='_blank' rel='noopener'>点此在新窗口查看大图</a></div>")
            else:
                img_html = (
                    f"<div class='hotspot-img-fail'>本次未采集到热点图链接。</div>")
            cards.append(
                f"<div class='hotspot-card {tag}'>"
                f"<div class='hotspot-head'>"
                f"<div class='hotspot-title'><span class='hotspot-rank'>#{i}</span>{esc(r['热点标题'])}"
                f"<span class='tag {tag}' style='margin-left:auto'>{esc(r['热度分组'])}</span></div>"
                f"<div class='hotspot-fields'>"
                f"<span class='hf'><b>成交热度</b><span class='v deal'>{esc(r['成交热度'])}</span></span>"
                f"<span class='hf'><b>搜索热度</b><span class='v'>{esc(r['搜索热度'])}</span></span>"
                f"<span class='hf'><b>机会类目</b><span class='v'>{esc(cats)}</span></span>"
                f"<span class='hf'><b>机会价格</b><span class='v'>{esc(price)}</span></span>"
                f"</div></div>"
                f"{img_html}"
                f"</div>")
        return "".join(cards)

    def opt_rows(counter_items):
        return "".join(f"<option value='{esc(x)}'>{esc(x)}</option>" for x in counter_items)

    # 案例卡片
    brand_set = sorted({c["品牌"] for c in s["cases"] if c["品牌"]})
    band_set = [b[0] for b in CASE_PRICE_BANDS]
    cards_html = []
    for c in s["cases"]:
        band = _band_of(c["平台最低价"])
        price_txt = c["平台最低价原文"] or "-"
        img = esc(c["主图链接"])
        cards_html.append(
            f"<div class='case-card' data-brand='{esc(c['品牌'])}' data-band='{band}' "
            f"data-group='{esc(c['热点分组'])}' data-search='{esc(c['商品标题'].lower())}'>"
            f"<img loading='lazy' src='{img}' alt=''>"
            f"<div class='case-body'><div class='case-title'>{esc(c['商品标题'])}</div>"
            f"<div><span class='tag'>{esc(c['品牌']) or '无品牌'}</span>"
            f"<span class='tag {'tag-hi' if c['热点分组'] == GROUP_HIGH else 'tag-lo'}'>{esc(c['热点分组'])}</span></div>"
            f"<div class='case-meta'><span class='case-price'>{esc(price_txt)}</span>"
            f"<span>{esc(c['所属热点'])}</span></div></div></div>")
    case_json = json.dumps(len(s["cases"]), ensure_ascii=False)

    # 关键词榜
    kf, kw = s["keywords"]["freq"], s["keywords"]["weighted"]
    kf_max = kf[0]["count"] if kf else 1
    kw_max = kw[0]["weight"] if kw else 1

    # 元素四宫格
    def element_block(title, key):
        el = s["elements"][key]
        mx = el["count"][0]["count"] if el["count"] else 1
        return f"<div><h3>{title}</h3>{_bar_rows(el['count'][:10], mx)}</div>"

    mg_mx = mg["count"][0]["count"] if mg["count"] else 1
    sc_mx = sig["scenes"][0]["count"] if sig["scenes"] else 1
    pp_mx = sig["personas"][0]["count"] if sig["personas"] else 1
    cat_mx = sig["categories"][0]["count"] if sig["categories"] else 1
    band_mx = max((b["count"] for b in s["priceBands"]["bands"]), default=1)

    status_icon = {"ok": "✅", "partial": "⚠️", "missing": "⛔"}
    decision_rows = "".join(
        f"<tr><td><b>{esc(dim)}</b></td><td>{status_icon[d['status']]}</td><td>{esc(d['evidence'])}</td></tr>"
        for dim, d in s["decision"].items())
    risk_rows = "".join(
        f"<tr><td><b>{esc(r['风险'])}</b></td><td>{esc(r['证据'])}</td><td>{esc(r['缓解'])}</td></tr>"
        for r in s["risks"])

    hi3 = "、".join(f"「{r['热点标题']}」" for r in hi[:3])
    lo3 = "、".join(f"「{r['热点标题']}」" for r in lo[:3])
    mat1 = mg["count"][0]["name"] if mg["count"] else "-"
    sc1 = sig["scenes"][0]["name"] if sig["scenes"] else "-"
    top3 = "、".join(f"「{r['热点标题']}」" for r in (hi + lo)[:3])

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(m['reportTitle'])} | {esc(m['weekLabel'])}</title>
<style>{CSS}</style>
</head>
<body>
<div class="hero"><div class="hero-inner">
<div class="eyebrow">DEWU OPPORTUNITY WEEKLY</div>
<h1>{esc(m['reportTitle'])}</h1>
<p>{esc(m['weekLabel'])}（抓取日期 {esc(m['captureDate'])}）· 数据源：{esc(m['sourceFile'])} · 生成于 {esc(m['generatedAt'])}</p>
<div class="chips">
<span class="chip"><b>{sm['finalCount']}</b>分析集热点</span>
<span class="chip"><b>{sm['highCount']}</b>{esc(GROUP_HIGH)}</span>
<span class="chip"><b>{sm['lowCount']}</b>{esc(GROUP_LOW)}</span>
<span class="chip"><b>{sm['similarCount']}</b>相似机会品</span>
<span class="chip"><b>{fmt_wan(sm['dealSum'])}</b>成交热度合计</span>
</div>
</div></div>
<nav><div class="nav-inner">
<a href="#s1">执行摘要</a><a href="#s2">热点对比</a><a href="#s3">热门关键词</a>
<a href="#s4">元素风格材质</a><a href="#s5">机会信号</a><a href="#s6">决策思路</a>
<a href="#s7">商品案例</a><a href="#s8">风险与口径</a>
</div></nav>
<div class="page">

<section class="card" id="s1">
<h2>一、执行摘要</h2>
<div class="summary">
原始数据 {f['rawRows']} 条，经类目白名单、国际大牌剔除、搜索热度均值过滤三步清洗后，
最终分析集 <b>{sm['finalCount']} 个热点</b>：<b>{esc(GROUP_HIGH)} {sm['highCount']} 个</b>、
<b>{esc(GROUP_LOW)} {sm['lowCount']} 个</b>。热度 TOP3：{esc(top3)}。
</div>
<div class="funnel">
<div class="fstep"><b>{f['rawRows']}</b><span>原始数据</span></div>
<div class="fstep {'loss' if f['step1Category']['dropped'] else ''}"><b>{f['step1Category']['kept']}</b><span>类目白名单后（剔 {f['step1Category']['dropped']}）</span></div>
<div class="fstep {'loss' if f['step2Luxury']['droppedHotspots'] else ''}"><b>{f['step2Luxury']['kept']}</b><span>大牌剔除后（剔 {f['step2Luxury']['droppedHotspots']}）</span></div>
<div class="fstep"><b>{f['step3Heat']['kept']}</b><span>搜索热度过滤后</span></div>
<div class="fstep"><b>{sm['highCount']}+{sm['lowCount']}</b><span>高成交 / 低成交</span></div>
</div>
<p class="note">头部款验证既有需求；「{esc(GROUP_LOW)}」组（{sm['lowCount']} 个）搜索热度高但成交转化不足，
是市场中尚未被满足机会的挖掘池，详见第二、六章。</p>
</section>

<section class="card" id="s2">
<h2>二、热点横向对比</h2>
<h3>2.1 {esc(GROUP_HIGH)}（成交热度 ≥ 均值 {fmt_wan(f['step3Heat']['dealMean'])}）</h3>
<div class="hotspot-list">{heat_cards(hi, 'tag-hi')}</div>
<h3>2.2 {esc(GROUP_LOW)}（成交热度 &lt; 均值 · 潜在未满足机会）</h3>
<div class="hotspot-list">{heat_cards(lo, 'tag-lo')}</div>
</section>

<section class="card" id="s3">
<h2>三、热门关键词</h2>
<p class="note">统计口径：热点标题 + 副标题 jieba 分词，去通用词；流量权重 = 含该词热点的成交热度之和。
「轻奢/小众/高级感」属行业标配而非差异化卖点，差异化从具象元素词中找。</p>
<div class="grid2">
<div><h3>按出现热点数</h3>{_bar_rows(kf[:15], kf_max)}</div>
<div><h3>按流量权重</h3>{_heat_bar_rows(kw[:15], kw_max)}</div>
</div>
</section>

<section class="card" id="s4">
<h2>四、元素 / 风格 / 材质三大趋势拆解</h2>
<h3>4.1 材质大类（归并视图）</h3>
{_bar_rows(mg['count'], mg_mx)}
<div class="grid2" style="margin-top:14px">
{element_block('4.2 材质（原始词）', '材质')}
{element_block('4.3 风格', '风格')}
{element_block('4.4 颜色', '颜色')}
{element_block('4.5 工艺', '工艺')}
</div>
</section>

<section class="card" id="s5">
<h2>五、机会信号：场景 / 人群 / 类目 / 价格带</h2>
<div class="grid2">
<div><h3>5.1 适用场景</h3>{_bar_rows(sig['scenes'][:10], sc_mx)}</div>
<div><h3>5.2 适用人群</h3>{_bar_rows(sig['personas'][:10], pp_mx)}</div>
<div><h3>5.3 机会类目（白名单内）</h3>{_bar_rows(sig['categories'][:10], cat_mx)}</div>
<div><h3>5.4 机会价格带（按区间上界）</h3>{_bar_rows(s['priceBands']['bands'], band_mx)}
<p class="note">价格数据缺失 {s['priceBands']['unpriced']} 条未计入。</p></div>
</div>
</section>

<section class="card" id="s6">
<h2>六、新品开发决策思路</h2>
<table><thead><tr><th>评估维度</th><th>数据支撑</th><th>结论</th></tr></thead>
<tbody>{decision_rows}</tbody></table>
<h3>下一步行动清单</h3>
<table><tbody>
<tr><td class="num">1</td><td><b>验证头部需求</b>：拆解 {esc(hi3)} 的相似机会品（第七章），确认可进入价格带与差异化点</td></tr>
<tr><td class="num">2</td><td><b>挖掘未满足机会</b>：{esc(lo3)} 搜索热但成交低，排查供给不足还是转化问题，优先打样</td></tr>
<tr><td class="num">3</td><td><b>材质/场景卡位</b>：主力材质方向「{esc(mat1)}」，主力场景「{esc(sc1)}」，围绕其做组合开发</td></tr>
<tr><td class="num">4</td><td><b>规避正面竞争</b>：相似品品牌 CR3 = {s['brands']['cr3'] * 100:.0f}%，避开头部品牌主销价格段</td></tr>
<tr><td class="num">5</td><td><b>交叉验证</b>：本报告为得物单平台单周快照，与天猫生意参谋、京东新品监控周报对齐后再定开款</td></tr>
</tbody></table>
</section>

<section class="card" id="s7">
<h2>七、商品案例：相似机会品库</h2>
<p class="case-count" id="case-count">共 {len(s['cases'])} 条（已剔除国际大牌、按标题去重）</p>
<div class="case-filters">
<input id="f-kw" type="text" placeholder="搜索商品标题关键词…">
<select id="f-brand"><option value="">全部品牌</option>{opt_rows(brand_set)}</select>
<select id="f-band"><option value="">全部价格段</option>{opt_rows(band_set)}</select>
<select id="f-group"><option value="">全部热点分组</option>
<option value="{esc(GROUP_HIGH)}">{esc(GROUP_HIGH)}</option>
<option value="{esc(GROUP_LOW)}">{esc(GROUP_LOW)}</option></select>
</div>
<div class="case-grid">{''.join(cards_html)}</div>
</section>

<section class="card" id="s8">
<h2>八、风险提示与数据口径</h2>
<table><thead><tr><th>风险</th><th>数据证据</th><th>缓解建议</th></tr></thead>
<tbody>{risk_rows}</tbody></table>
<h3>清洗漏斗（数据边界）</h3>
<table><thead><tr><th>步骤</th><th>规则</th><th>保留</th><th>剔除</th></tr></thead><tbody>
<tr><td>原始数据</td><td>-</td><td class="num">{f['rawRows']}</td><td class="num">-</td></tr>
<tr><td>1. 类目整理</td><td>机会类目命中白名单（{f['step1Category']['whitelistSize']} 条）即保留</td>
<td class="num">{f['step1Category']['kept']}</td><td class="num">{f['step1Category']['dropped']}</td></tr>
<tr><td>2. 大牌剔除</td><td>热点标题含 30 个国际大牌中英文别名；相似品同清</td>
<td class="num">{f['step2Luxury']['kept']}</td><td class="num">{f['step2Luxury']['droppedHotspots']} + 相似品 {f['step2Luxury']['droppedSimilarCount']}</td></tr>
<tr><td>3. 热度过滤</td><td>搜索热度 &gt; 均值 {fmt_wan(f['step3Heat']['searchMean'])}</td>
<td class="num">{f['step3Heat']['kept']}</td><td class="num">{f['step2Luxury']['kept'] - f['step3Heat']['kept']}</td></tr>
<tr class="hl"><td>分组</td><td>成交热度 ≥ 均值 {fmt_wan(f['step3Heat']['dealMean'])} → {esc(GROUP_HIGH)}</td>
<td class="num">{f['step3Heat']['highCount']} / {f['step3Heat']['lowCount']}</td><td class="num">-</td></tr>
</tbody></table>
<h3>数据来源与免责</h3>
<p class="note">数据文件：{esc(m['sourceFile'])}（抓取日期 {esc(m['captureDate'])}，得物商家后台「查看更多类目热点」）。<br>
热度为得物平台给出的近30天指标，非销量/销售额绝对值；本报告仅供新品开发选品参考，不构成经营承诺。<br>
国际大牌已按业务规则剔除；剔除明细见批次目录「过程记录/clean_funnel.json」。</p>
</section>

</div>
<footer>{esc(m['reportTitle'])} · {esc(m['weekLabel'])} · 由 生成分析报告 技能自动生成 · 案例数据 {case_json} 条</footer>
<script>{JS}</script>
</body>
</html>"""
    return html
