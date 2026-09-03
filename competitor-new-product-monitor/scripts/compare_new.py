# -*- coding: utf-8 -*-
"""变动对比：把 BASE/prev/（上一轮）与 BASE/ 当前 jd_new_*.json 对比，标出新增/下架/涨价/降价。

用法: python compare_new.py [BASE]
默认 BASE = jd-baseline。无 prev/ 时提示跳过对比。
"""
import json, glob, os, sys
from datetime import datetime

BASE = sys.argv[1] if len(sys.argv) > 1 else 'jd-baseline'
TODAY = datetime.now().strftime('%Y-%m-%d')
prev_dir = os.path.join(BASE, 'prev')

prev_files = sorted(glob.glob(os.path.join(prev_dir, 'jd_new_*.json')))
new_files = sorted(glob.glob(os.path.join(BASE, 'jd_new_*.json')))

if not prev_files:
    print('未找到 BASE/prev/ 上一轮数据，跳过对比（首次抓取仅建档）。')
    sys.exit(0)

def load(files):
    out = {}
    for f in files:
        with open(f, encoding='utf-8') as fh:
            data = json.load(fh)
        for it in data.get('items', []):
            url = it.get('url', '')
            if url:
                out[url] = {**it, 'store': data['store']}
    return out

prev, new = load(prev_files), load(new_files)
added = [v for k, v in new.items() if k not in prev]
removed = [v for k, v in prev.items() if k not in new]
price_changes = []
for k, v in new.items():
    o = prev.get(k)
    if not o:
        continue
    np_, op_ = v.get('price'), o.get('price')
    if isinstance(np_, (int, float)) and np_ and isinstance(op_, (int, float)) and op_ and np_ != op_:
        pct = (np_ - op_) / op_ * 100
        price_changes.append({'title': v.get('title', ''), 'store': v['store'], 'url': k,
                              'old': op_, 'new': np_, 'pct': pct, 'up': np_ > op_})

price_changes.sort(key=lambda x: -abs(x['pct']))
up = [c for c in price_changes if c['up']]
down = [c for c in price_changes if not c['up']]

lines = [f"# 竞品新品变动对比（{TODAY}）", ""]
lines.append(f"- 新增上架：**{len(added)}** 件")
lines.append(f"- 下架/消失：**{len(removed)}** 件")
lines.append(f"- 涨价：**{len(up)}** 件 | 降价：**{len(down)}** 件")
lines.append("")

def table(rows, kind):
    if not rows:
        return []
    t = [f"## {kind}（{len(rows)}）", "", "| 商品 | 店铺 | 原价→现价 | 幅度 | 链接 |", "|---|---|---|---|---|"]
    for r in rows[:50]:
        old, new = r.get('old'), r.get('new')
        if old and new:
            price_cell = f"¥{old}→¥{new} | {'+' if r.get('up') else ''}{r.get('pct', 0):.1f}%"
        elif new:
            price_cell = f"现价 ¥{new} | -"
        elif old:
            price_cell = f"原价 ¥{old} | -"
        else:
            price_cell = "- | -"
        t.append(f"| {r['title'][:38]}{'…' if len(r['title'])>38 else ''} | {r['store']} | "
                 f"{price_cell} | [查看]({r['url']}) |")
    return t

lines += table([{'title': a['title'], 'store': a['store'], 'url': a['url'], 'new': a.get('price')} for a in added], "新增上架")
lines += table([{'title': r['title'], 'store': r['store'], 'url': r['url'], 'old': r.get('price')} for r in removed], "下架/消失")
lines += table(up, "涨价")
lines += table(down, "降价")
lines.append("")

out = os.path.join(BASE, f'变动对比-{TODAY}.md')
with open(out, 'w', encoding='utf-8') as fh:
    fh.write("\n".join(lines))
print(f"对比完成：新增 {len(added)} / 下架 {len(removed)} / 涨价 {len(up)} / 降价 {len(down)}")
print('输出:', os.path.abspath(out))
