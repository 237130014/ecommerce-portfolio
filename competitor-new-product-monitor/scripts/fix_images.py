# -*- coding: utf-8 -*-
"""图片处理：1) 京东 360buyimg 链接 n7(缩略图)→n0(原图)，天猫 alicdn 去尺寸后缀转原图；
2) 下载图片到 {BASE}/images/；3) 更新 JSON 与「新品全量明细.csv」。

用法: python fix_images.py [BASE]
默认 BASE = jd-baseline（当前工作目录下）。

防风控与健壮性（本次加固）
--------------------------
- 带 Referer 请求：部分图床有防盗链，裸请求会 403，按域名补对应 Referer
- 指数退避重试：失败按 1s / 2s / 4s 退避，不硬撞
- 低并发 + 随机间隔：并发压到 3，每次请求前加随机小延迟，避免批量特征
"""
import json
import glob
import csv
import os
import re
import sys
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request


def norm_path(p):
    """兼容 Git Bash 风格路径：/c/Users/xxx → C:/Users/xxx（Windows Python 不认前者）。"""
    if p and re.match(r'^/[a-zA-Z]/', p):
        return p[1].upper() + ':' + p[2:]
    return p


BASE = norm_path(sys.argv[1]) if len(sys.argv) > 1 else 'jd-baseline'
IMG_DIR = os.path.join(BASE, 'images')
os.makedirs(IMG_DIR, exist_ok=True)

MAX_WORKERS = 3                 # 并发压低：防风控
RETRIES = 3                     # 重试次数（含首次）
DOWNLOAD_DELAY = (0.2, 0.8)     # 每次下载前的随机延迟（秒）
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')

files = sorted(glob.glob(os.path.join(BASE, 'jd_new_*.json')))
all_items = []


def fix_url(u):
    """图片转原图：京东 360buyimg n7→n0；天猫/淘宝 alicdn 去掉尺寸/质量后缀（如 _60x60.jpg、_q50.jpg）。"""
    if not u:
        return u
    u = u.replace('/n7/', '/n0/')
    while True:
        n = re.sub(r'\.(jpg|jpeg|png|webp)_[0-9A-Za-z]+\.(jpg|jpeg|png|webp)$', r'.\1', u)
        if n == u:
            break
        u = n
    return u


def referer_for(url):
    """按图床域名给出合适的 Referer，规避防盗链。"""
    if '360buyimg.com' in url:
        return 'https://item.jd.com/'
    if 'alicdn.com' in url:
        return 'https://detail.tmall.com/'
    return ''


for f in files:
    m = re.match(r'jd_new_(\d+)_', os.path.basename(f))
    no = m.group(1) if m else '00'
    with open(f, encoding='utf-8') as fh:
        data = json.load(fh)
    # 去重①：店内按商品链接去重（同一商品在列表重复出现时只留第一个）
    seen_url = set()
    dedup = []
    for it in data['items']:
        u = it.get('url', '')
        if u and u in seen_url:
            continue
        if u:
            seen_url.add(u)
        dedup.append(it)
    if len(dedup) != len(data['items']):
        print('  店内去重: %s %d -> %d' % (data['store'], len(data['items']), len(dedup)))
    data['items'] = dedup
    for idx, it in enumerate(data['items'], 1):
        it['image'] = fix_url(it.get('image', ''))
        it['store'] = data['store']
        all_items.append((no, idx, it))
    with open(f, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)

print('链接替换完成，共 %d 条，开始下载图片（并发 %d，带 Referer + 退避）...'
      % (len(all_items), MAX_WORKERS))


def download(item):
    no, idx, it = item
    url = it['image']
    local = os.path.join(IMG_DIR, '%s_%03d.jpg' % (no, idx))
    if not url:
        return (no, idx, None, 'fail')
    if os.path.exists(local) and os.path.getsize(local) > 1000:
        return (no, idx, local, 'cached')
    headers = {'User-Agent': UA}
    ref = referer_for(url)
    if ref:
        headers['Referer'] = ref
    for attempt in range(RETRIES):
        try:
            time.sleep(random.uniform(*DOWNLOAD_DELAY))
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=25) as r:
                raw = r.read()
            if len(raw) > 1000:
                with open(local, 'wb') as fh:
                    fh.write(raw)
                return (no, idx, local, 'ok')
        except Exception:
            if attempt < RETRIES - 1:
                time.sleep(2 ** attempt)   # 指数退避 1s / 2s
    return (no, idx, None, 'fail')


results = {'ok': 0, 'cached': 0, 'fail': 0}
local_map = {}
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
    futs = {ex.submit(download, it): it for it in all_items}
    for fut in as_completed(futs):
        no, idx, local, status = fut.result()
        results[status] = results.get(status, 0) + 1
        if local:
            local_map[(no, idx)] = local

print('下载结果: %s' % results)
if results['fail']:
    # 修复：all_items 元素是 (no, idx, it) 三元组，此处必须按三元组解包
    failed = ['%s_%03d' % (no, idx)
              for (no, idx, _it) in all_items if local_map.get((no, idx)) is None]
    print('警告：以下 %d 张图片下载失败（保留链接，报告中显示图缺失）—— %s'
          % (len(failed), failed[:10]))


# CSV（n0 链接 + 本地相对路径）
def csv_path():
    p = os.path.join(BASE, '新品全量明细.csv')
    if not os.path.exists(p):
        return p
    try:
        with open(p, 'a', encoding='utf-8'):
            pass
        return p
    except PermissionError:
        return os.path.join(BASE, '新品全量明细_v2.csv')


csv_out = csv_path()
seen_global = set()
csv_rows = 0
with open(csv_out, 'w', encoding='utf-8-sig', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=['store', 'title', 'price', 'activity', 'comments',
                                       'image_n0', 'local_image', 'url', 'id'])
    w.writeheader()
    for no, idx, it in all_items:
        # 去重②：CSV 全局按商品链接去重（同源店铺同一商品只保留第一个）
        u = it.get('url', '')
        if u in seen_global:
            continue
        seen_global.add(u)
        loc = local_map.get((no, idx), '')
        loc_rel = os.path.relpath(loc, BASE).replace(os.sep, '/') if loc else ''
        w.writerow({
            'store': it['store'], 'title': it['title'], 'price': it.get('price', ''),
            'activity': it.get('activity', ''), 'comments': it.get('comments', ''),
            'image_n0': it['image'], 'local_image': loc_rel, 'url': u, 'id': it.get('id', '')
        })
        csv_rows += 1
print('CSV: %s（全局去重后 %d 行，原始 %d 条）' % (csv_out, csv_rows, len(all_items)))
