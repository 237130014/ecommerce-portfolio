# -*- coding: utf-8 -*-
"""变动对比：把上一轮数据与当前 jd_new_*.json 对比，标出新增 / 下架 / 涨价 / 降价。

用法
----
    python compare_new.py [BASE] [--min-pct 1.0] [--against YYYY-MM-DD]

默认 BASE = jd-baseline。无上一轮数据时提示跳过（首次抓取仅建档）。

本次改进
--------
1. URL 归一化匹配：按平台稳定商品 ID 匹配，剥离活动/追踪参数。京东换活动链接、天猫带不同
   query 是常见现象，旧版按完整 URL 精确匹配会误判成「下架 + 新增」
2. 涨跌阈值：幅度小于 --min-pct 的变动忽略（默认 1%），过滤掉一分钱级别的噪音
3. 变动数据落盘：额外输出 `变动数据.json`，供看板给卡片打变动角标
4. 历史归档：结果归档到 BASE/history/{日期}/，保留多轮轨迹，便于回溯
"""
import argparse
import glob
import json
import os
import re
import shutil
import sys
from datetime import datetime

TODAY = datetime.now().strftime('%Y-%m-%d')


def norm_path(p):
    """兼容 Git Bash 风格路径：/c/Users/xxx → C:/Users/xxx（Windows Python 不认前者）。"""
    if p and re.match(r'^/[a-zA-Z]/', p):
        return p[1].upper() + ':' + p[2:]
    return p


def norm_url(u):
    """归一化商品 URL 为平台内的稳定 key。

    与 gen_dashboard.py 中的同名函数保持一致，两边必须同步修改。
    优先级：query 里的 id（天猫/淘宝） > 路径里的数字 ID（京东） > 去 query 的裸路径。
    """
    if not u:
        return u
    u = u.split('#')[0]
    match = re.search(r'[?&]id=(\d+)', u)
    if match:
        return 'id:%s' % match.group(1)
    match = re.search(r'item\.jd\.com/(\d+)', u) or re.search(r'/(\d{6,})\.html', u)
    if match:
        return 'jd:%s' % match.group(1)
    return u.split('?')[0].rstrip('/').lower()


def load(files):
    """把多份 JSON 读成 {归一化key: item}，同 key 只保留第一条。"""
    out = {}
    for f in files:
        with open(f, encoding='utf-8') as fh:
            data = json.load(fh)
        for it in data.get('items', []):
            url = it.get('url', '')
            if not url:
                continue
            key = norm_url(url)
            if key in out:
                continue
            out[key] = {**it, 'store': data.get('store', it.get('store', '')), '_key': key}
    return out


def money_cell(price):
    if isinstance(price, (int, float)) and price:
        return '¥%g' % price
    return '- '


def main():
    ap = argparse.ArgumentParser(description='竞品新品变动对比')
    ap.add_argument('base', nargs='?', default='jd-baseline', help='数据目录（默认 jd-baseline）')
    ap.add_argument('--min-pct', type=float, default=1.0, help='涨跌幅度阈值（%%），低于该值忽略，默认 1.0')
    ap.add_argument('--against', default='', help='对比指定历史目录（BASE/history/{日期}），默认用 BASE/prev/')
    args = ap.parse_args()

    base = norm_path(args.base)
    if args.against:
        prev_dir = os.path.join(base, 'history', args.against)
    else:
        prev_dir = os.path.join(base, 'prev')

    prev_files = sorted(glob.glob(os.path.join(prev_dir, 'jd_new_*.json')))
    new_files = sorted(glob.glob(os.path.join(base, 'jd_new_*.json')))

    if not prev_files:
        if not new_files:
            print('未找到本轮数据（%s/jd_new_*.json），无法对比。' % base)
            return 1
        # 首轮：自动把当前数据建档为下一轮的对比基线
        os.makedirs(prev_dir, exist_ok=True)
        copied = 0
        for f in new_files:
            shutil.copy2(f, os.path.join(prev_dir, os.path.basename(f)))
            copied += 1
        print('首轮抓取：已把 %d 个数据文件建档到 %s，作为下一轮对比基线。' % (copied, prev_dir))
        return 0
    if not new_files:
        print('未找到本轮数据（%s/jd_new_*.json），无法对比。' % base)
        return 1

    prev, new = load(prev_files), load(new_files)

    added = [v for k, v in new.items() if k not in prev]
    removed = [v for k, v in prev.items() if k not in new]

    price_changes = []
    for key, cur in new.items():
        old = prev.get(key)
        if not old:
            continue
        np_, op_ = cur.get('price'), old.get('price')
        if not (isinstance(np_, (int, float)) and np_):
            continue
        if not (isinstance(op_, (int, float)) and op_):
            continue
        if np_ == op_:
            continue
        pct = (np_ - op_) / op_ * 100
        if abs(pct) < args.min_pct:
            continue
        price_changes.append({'title': cur.get('title', ''), 'store': cur['store'],
                              'url': cur.get('url', ''), 'old': op_, 'new': np_,
                              'pct': pct, 'up': np_ > op_, '_key': key})

    price_changes.sort(key=lambda x: -abs(x['pct']))
    up = [c for c in price_changes if c['up']]
    down = [c for c in price_changes if not c['up']]

    lines = ['# 竞品新品变动对比（%s）' % TODAY, '']
    lines.append('- 对比基准：`%s`' % os.path.relpath(prev_dir, base).replace(os.sep, '/'))
    lines.append('- 本轮商品：**%d** 件 | 上轮商品：**%d** 件' % (len(new), len(prev)))
    lines.append('- 新增上架：**%d** 件' % len(added))
    lines.append('- 下架/消失：**%d** 件' % len(removed))
    lines.append('- 涨价：**%d** 件 | 降价：**%d** 件（阈值 %g%%，低于该幅度不列）' % (len(up), len(down), args.min_pct))
    lines.append('')

    def table(rows, kind):
        if not rows:
            return []
        items = ['## %s（%d）' % (kind, len(rows)), '',
                 '| 商品 | 店铺 | 原价→现价 | 幅度 | 链接 |', '|---|---|---|---|---|']
        for r in rows[:50]:
            title = r.get('title', '')
            shown = title[:38] + ('…' if len(title) > 38 else '')
            old, new_ = r.get('old'), r.get('new')
            if old and new_:
                price = '%s→%s' % (money_cell(old), money_cell(new_))
                pct = '%s%.1f%%' % ('+' if r.get('up') else '', r.get('pct', 0))
            elif new_:
                price, pct = '现价 %s' % money_cell(new_), '-'
            elif old:
                price, pct = '原价 %s' % money_cell(old), '-'
            else:
                price, pct = '-', '-'
            items.append('| %s | %s | %s | %s | [查看](%s) |'
                         % (shown, r.get('store', ''), price, pct, r.get('url', '')))
        items.append('')
        return items

    lines += table([{'title': a.get('title', ''), 'store': a['store'], 'url': a.get('url', ''),
                     'new': a.get('price')} for a in added], '新增上架')
    lines += table([{'title': r.get('title', ''), 'store': r['store'], 'url': r.get('url', ''),
                     'old': r.get('price')} for r in removed], '下架/消失')
    lines += table(up, '涨价')
    lines += table(down, '降价')

    out_md = os.path.join(base, '变动对比-%s.md' % TODAY)
    with open(out_md, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines))

    # 变动数据落盘，供看板打角标
    delta = {
        'date': TODAY,
        'base': os.path.relpath(prev_dir, base).replace(os.sep, '/'),
        'added': [v['_key'] for v in added],
        'removed': [v['_key'] for v in removed],
        'up': {c['_key']: round(c['pct'], 2) for c in up},
        'down': {c['_key']: round(c['pct'], 2) for c in down},
    }
    out_json = os.path.join(base, '变动数据.json')
    with open(out_json, 'w', encoding='utf-8') as fh:
        json.dump(delta, fh, ensure_ascii=False, indent=2)

    # 历史归档（保留多轮轨迹）
    try:
        hist_dir = os.path.join(base, 'history', TODAY)
        os.makedirs(hist_dir, exist_ok=True)
        for f in new_files:
            shutil.copy2(f, hist_dir)
        shutil.copy2(out_md, hist_dir)
    except Exception as exc:
        print('提示：历史归档失败（不影响主流程）：%s' % exc)

    print('对比完成：新增 %d / 下架 %d / 涨价 %d / 降价 %d'
          % (len(added), len(removed), len(up), len(down)))
    print('输出:', os.path.abspath(out_md))
    print('变动数据:', os.path.abspath(out_json))
    return 0


if __name__ == '__main__':
    sys.exit(main())
