# -*- coding: utf-8 -*-
"""生成花瓣网式瀑布流新品看板 HTML：全部新品图片、品牌导航、搜索、价格排序、点击放大、
变动角标（新增 / 涨价 / 降价）。

用法: python gen_dashboard.py [BASE]
默认 BASE = jd-baseline。

本次改进
--------
1. 修复硬编码「12 家店铺」→ 按实际数据动态计算
2. 标题不再写死「京东」，按数据里出现的平台自动生成
3. 变动角标：读 compare_new.py 产出的 `变动数据.json`，在卡片上标注 新 / 涨 x% / 降 x%
4. 新增「只看变动」筛选，一键过滤出本轮有变化的商品
5. CSV 下载链接自动跟随实际文件名（被占用降级为 _v2 时也能正确下载）
6. 品牌导航改为「全部预览 + 单品牌查看」：默认全部，点品牌只看该品牌，再点一次（或点返回）回到全部
"""
import glob
import json
import os
import re
import sys
from datetime import datetime

def norm_path(p):
    """兼容 Git Bash 风格路径：/c/Users/xxx → C:/Users/xxx（Windows Python 不认前者）。"""
    if p and re.match(r'^/[a-zA-Z]/', p):
        return p[1].upper() + ':' + p[2:]
    return p


BASE = norm_path(sys.argv[1]) if len(sys.argv) > 1 else 'jd-baseline'
TODAY = datetime.now().strftime('%Y-%m-%d')

PLATFORM_LABEL = {'jd': '京东', 'tmall': '天猫'}

files = sorted(glob.glob(os.path.join(BASE, 'jd_new_*.json')))
seen, items = set(), []
dup_note = {}
platforms = set()

for f in files:
    match = re.match(r'jd_new_(\d+)_', os.path.basename(f))
    no = match.group(1) if match else '00'
    with open(f, encoding='utf-8') as fh:
        data = json.load(fh)
    store = data['store']
    if data.get('platform'):
        platforms.add(data['platform'])
    for idx, it in enumerate(data['items'], 1):
        url = it.get('url', '')
        if url in seen:
            dup_note[store] = '同源店铺，已合并去重'
            continue
        seen.add(url)
        img = os.path.join(BASE, 'images', '%s_%03d.jpg' % (no, idx))
        items.append({
            'store': store,
            'title': it.get('title', ''),
            'price': it.get('price'),
            'activity': it.get('activity', ''),
            'comments': it.get('comments', ''),
            'img': os.path.relpath(img, BASE).replace(os.sep, '/'),
            'url': url,
        })

# 变动数据（可能不存在，首次抓取时没有）
delta_path = os.path.join(BASE, '变动数据.json')
delta = {}
if os.path.isfile(delta_path):
    try:
        with open(delta_path, encoding='utf-8') as fh:
            delta = json.load(fh)
    except Exception:
        delta = {}

# CSV 实际文件名（被 Excel 占用时 fix_images.py 会降级为 _v2）
csv_name = '新品全量明细.csv'
if not os.path.isfile(os.path.join(BASE, csv_name)) and os.path.isfile(os.path.join(BASE, '新品全量明细_v2.csv')):
    csv_name = '新品全量明细_v2.csv'

data_json = json.dumps(items, ensure_ascii=False).replace('</', '<\\/')
delta_json = json.dumps(delta, ensure_ascii=False).replace('</', '<\\/')

if platforms == {'jd'}:
    board_name = '京东竞品新品瀑布流看板'
elif platforms:
    board_name = '竞品新品瀑布流看板'
else:
    board_name = '竞品新品瀑布流看板'

TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__BOARD_NAME__ · __TODAY__</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: "Microsoft YaHei", "PingFang SC", sans-serif; background: #f6f5f2; color: #333; }
.toolbar { position: sticky; top: 0; z-index: 100; background: #fff; border-bottom: 1px solid #e6e3de;
  padding: 12px 20px; box-shadow: 0 2px 8px rgba(0,0,0,.05); }
.toolbar h1 { font-size: 18px; display: inline-block; margin-right: 18px; vertical-align: middle; }
.stats { display: inline-block; color: #999; font-size: 13px; vertical-align: middle; }
.controls { margin-top: 10px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.search-box { flex: 1; min-width: 220px; max-width: 420px; position: relative; }
.search-box input { width: 100%; padding: 8px 12px 8px 34px; border: 1px solid #ddd; border-radius: 20px;
  font-size: 14px; outline: none; background: #faf9f7; }
.search-box .icon { position: absolute; left: 12px; top: 8px; color: #bbb; font-size: 14px; }
select { padding: 8px 12px; border: 1px solid #ddd; border-radius: 8px; font-size: 13px; background: #fff; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { padding: 5px 12px; border: 1px solid #ddd; border-radius: 16px; font-size: 12px; cursor: pointer;
  background: #fff; user-select: none; transition: all .15s; }
.chip.on { background: #c7000b; color: #fff; border-color: #c7000b; }
.chip .n { opacity: .7; font-size: 11px; margin-left: 3px; }
.chip.only-change.on { background: #ba7517; border-color: #ba7517; }
.link-btn { padding: 8px 14px; background: #f5f5f5; border: 1px solid #ddd; border-radius: 8px; font-size: 13px;
  text-decoration: none; color: #555; }
.link-btn:hover { background: #eee; }
#count-bar { padding: 10px 20px; font-size: 13px; color: #888; background: #f6f5f2; }
.masonry { column-gap: 14px; padding: 0 20px 40px; }
@media (min-width: 1700px) { .masonry { column-count: 6; } }
@media (max-width: 1699px) and (min-width: 1300px) { .masonry { column-count: 5; } }
@media (max-width: 1299px) and (min-width: 1000px) { .masonry { column-count: 4; } }
@media (max-width: 999px) and (min-width: 700px) { .masonry { column-count: 3; } }
@media (max-width: 699px) { .masonry { column-count: 2; } }
.card { break-inside: avoid; margin-bottom: 14px; background: #fff; border-radius: 10px; overflow: hidden;
  box-shadow: 0 1px 4px rgba(0,0,0,.08); transition: transform .2s, box-shadow .2s; }
.card:hover { transform: translateY(-3px); box-shadow: 0 6px 18px rgba(0,0,0,.12); }
.card .pic { position: relative; cursor: zoom-in; }
.card .pic img { width: 100%; height: auto; display: block; background: #f0eeea; }
.card .pic .tag { position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,.55); color: #fff;
  font-size: 11px; padding: 2px 8px; border-radius: 4px; }
.card .pic .delta { position: absolute; top: 8px; right: 8px; color: #fff; font-size: 11px;
  padding: 2px 8px; border-radius: 4px; font-weight: 500; }
.delta.new { background: rgba(186,117,23,.94); }
.delta.up { background: rgba(199,0,11,.94); }
.delta.down { background: rgba(15,158,117,.94); }
.card .info { padding: 8px 10px 10px; }
.card .t { font-size: 12.5px; line-height: 1.45; height: 2.9em; overflow: hidden; display: -webkit-box;
  -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.card .row { display: flex; justify-content: space-between; align-items: center; margin-top: 6px; }
.card .act { display: inline-block; margin-top: 4px; font-size: 11px; color: #c7000b; background: #fff0f0;
  padding: 1px 8px; border-radius: 4px; border: 1px solid #ffd5d5; }
.card .p { color: #c7000b; font-size: 15px; font-weight: 600; }
.card .p.no { color: #aaa; font-weight: 400; font-size: 12px; }
.card .c { color: #999; font-size: 11px; }
.empty { text-align: center; padding: 60px 0; color: #999; }
#lightbox { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.92); z-index: 999;
  align-items: center; justify-content: center; flex-direction: column; }
#lightbox.show { display: flex; }
#lightbox img { max-width: 88vw; max-height: 78vh; border-radius: 6px; box-shadow: 0 10px 40px rgba(0,0,0,.6); }
#lightbox .lb-info { color: #fff; max-width: 720px; text-align: center; margin-top: 14px; font-size: 14px; line-height: 1.5; }
#lightbox .lb-act { margin-top: 12px; }
#lightbox a { display: inline-block; padding: 9px 22px; background: #c7000b; color: #fff; text-decoration: none;
  border-radius: 20px; font-size: 14px; }
#lightbox .lb-close { position: fixed; top: 18px; right: 26px; color: #fff; font-size: 34px; cursor: pointer; }
#toTop { display: none; position: fixed; right: 24px; bottom: 30px; width: 42px; height: 42px; border-radius: 50%;
  background: #c7000b; color: #fff; border: none; font-size: 18px; cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,.25); }
</style>
</head>
<body>
<div class="toolbar">
  <h1>__BOARD_NAME__</h1>
  <span class="stats" id="stats"></span>
  <div class="controls">
    <div class="search-box"><span class="icon">🔍</span>
      <input id="kw" type="text" placeholder="搜索商品名称，如：四叶草 / 手链 / 和田玉">
    </div>
    <select id="sort">
      <option value="">价格：默认排序</option>
      <option value="asc">价格：从低到高</option>
      <option value="desc">价格：从高到低</option>
    </select>
    <a class="link-btn" href="__CSV_NAME__" download>⬇ 下载明细 CSV</a>
  </div>
  <div class="chips" id="chips"></div>
</div>
<div id="count-bar"></div>
<div class="masonry" id="masonry"></div>
<div class="empty" id="empty" style="display:none">没有符合条件的商品，换个关键词或筛选条件试试</div>
<div id="lightbox">
  <span class="lb-close" onclick="closeLB()">×</span>
  <img id="lb-img" src="" alt="">
  <div class="lb-info" id="lb-info"></div>
  <div class="lb-act"><a id="lb-link" href="#" target="_blank">查看该商品 →</a></div>
</div>
<button id="toTop" onclick="window.scrollTo({top:0,behavior:'smooth'})">↑</button>
<script id="data" type="application/json">__DATA__</script>
<script id="delta" type="application/json">__DELTA__</script>
<script>
const ALL = JSON.parse(document.getElementById('data').textContent);
const DELTA = JSON.parse(document.getElementById('delta').textContent);
const UP = DELTA.up || {}, DOWN = DELTA.down || {};
const ADDED = new Set(DELTA.added || []);
const REMOVED = new Set(DELTA.removed || []);
let activeStore = null, kw = '', sortMode = '', onlyChanged = false, currentList = [];
// activeStore === null 表示「全部预览」；否则只展示该品牌

function normUrl(u) {
  if (!u) return u;
  u = u.split('#')[0];
  let m = u.match(/[?&]id=(\d+)/);
  if (m) return 'id:' + m[1];
  m = u.match(/item\.jd\.com\/(\d+)/) || u.match(/\/(\d{6,})\.html/);
  if (m) return 'jd:' + m[1];
  return u.split('?')[0].replace(/\/+$/, '').toLowerCase();
}

function deltaOf(it) {
  const k = normUrl(it.url);
  if (ADDED.has(k)) return { cls: 'new', text: '新上架' };
  if (UP[k] != null) return { cls: 'up', text: '涨 ' + UP[k] + '%' };
  if (DOWN[k] != null) return { cls: 'down', text: '降 ' + Math.abs(DOWN[k]) + '%' };
  return null;
}

const shortName = (s) => s.replace('京东自营旗舰店', '').replace('珠宝官方旗舰店', '')
  .replace('饰品京东自营', '').replace('京东自营', '');

const stores = [...new Set(ALL.map(i => i.store))];
const chipBox = document.getElementById('chips');
const countMap = ALL.reduce((m, i) => { m[i.store] = (m[i.store] || 0) + 1; return m; }, {});

// 「全部预览」入口：默认选中，一键回到所有品牌
const allChip = document.createElement('span');
allChip.className = 'chip all-chip on';
allChip.textContent = '全部预览 ' + ALL.length;
allChip.title = '展示所有品牌的全部新品';
allChip.onclick = () => { activeStore = null; syncChips(); render(); };
chipBox.appendChild(allChip);

// 每个品牌一个入口：点击后单独呈现该品牌下的商品
const storeChips = {};
stores.forEach(s => {
  const c = document.createElement('span');
  c.className = 'chip';
  c.textContent = shortName(s) + ' ' + countMap[s];
  c.title = '只看 ' + shortName(s) + ' 的商品';
  c.onclick = () => { activeStore = (activeStore === s) ? null : s; syncChips(); render(); };
  storeChips[s] = c;
  chipBox.appendChild(c);
});

// 选中某品牌时出现的「返回全部」快捷入口
const backChip = document.createElement('span');
backChip.className = 'chip back-hint';
backChip.onclick = () => { activeStore = null; syncChips(); render(); };
chipBox.appendChild(backChip);

function syncChips() {
  allChip.classList.toggle('on', activeStore === null);
  stores.forEach(s => storeChips[s].classList.toggle('on', activeStore === s));
  backChip.classList.toggle('show', activeStore !== null);
  backChip.textContent = '× 返回全部预览';
}

const changedCount = ALL.filter(i => deltaOf(i)).length;
if (changedCount > 0) {
  const cc = document.createElement('span');
  cc.className = 'chip only-change';
  cc.textContent = '只看变动 ' + changedCount;
  cc.onclick = () => { onlyChanged = !onlyChanged; cc.classList.toggle('on', onlyChanged); render(); };
  chipBox.appendChild(cc);
}

const allPlatforms = [...new Set(ALL.map(i => i.store))].length;
function pricedCount() { return ALL.filter(i => typeof i.price === 'number' && i.price).length; }
document.getElementById('stats').textContent =
  `共 ${ALL.length} 件新品 · 有价格 ${pricedCount()} 件 · ${allPlatforms} 家店铺 · __TODAY__ 抓取`;

document.getElementById('kw').addEventListener('input', e => { kw = e.target.value.trim(); render(); });
document.getElementById('sort').addEventListener('change', e => { sortMode = e.target.value; render(); });

function render() {
  let list = activeStore ? ALL.filter(i => i.store === activeStore) : ALL.slice();
  if (kw) list = list.filter(i => i.title.includes(kw));
  if (onlyChanged) list = list.filter(i => deltaOf(i));
  if (sortMode === 'asc') list = list.filter(i => typeof i.price === 'number').sort((a, b) => a.price - b.price);
  if (sortMode === 'desc') list = list.filter(i => typeof i.price === 'number').sort((a, b) => b.price - a.price);
  currentList = list;
  document.getElementById('masonry').innerHTML = list.map((it, k) => card(it, k)).join('');
  document.getElementById('empty').style.display = list.length ? 'none' : 'block';
  const scope = activeStore ? `品牌：${shortName(activeStore)} · ` : '全部预览 · ';
  document.getElementById('count-bar').textContent =
    scope + `当前显示 ${list.length} 件 / 共 ${ALL.length} 件` + (kw ? `（关键词：${kw}）` : '')
    + (onlyChanged ? '（只看变动）' : '');
}

function card(it, k) {
  const p = (typeof it.price === 'number' && it.price) ? `¥${it.price}` : '<span class="p no">价格待补</span>';
  const act = it.activity ? `<span class="act">${it.activity}</span>` : '';
  const d = deltaOf(it);
  const badge = d ? `<span class="delta ${d.cls}">${d.text}</span>` : '';
  return `<div class="card">
    <div class="pic" onclick="openLB(${k})">
      <img loading="lazy" src="${it.img}" alt="${it.title.replace(/"/g, '&quot;')}">
      <span class="tag">${shortName(it.store)}</span>
      ${badge}
    </div>
    <div class="info">
      <div class="t">${it.title}</div>
      <div class="row"><span class="p">${p}</span><span class="c">${it.comments || ''}</span></div>
      ${act}
    </div>
  </div>`;
}

function openLB(k) {
  const it = currentList[k];
  if (!it) return;
  document.getElementById('lb-img').src = it.img;
  document.getElementById('lb-info').textContent = it.title;
  document.getElementById('lb-link').href = it.url;
  document.getElementById('lightbox').classList.add('show');
}
function closeLB() { document.getElementById('lightbox').classList.remove('show'); }
document.getElementById('lightbox').addEventListener('click', e => { if (e.target.id === 'lightbox') closeLB(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeLB(); });

window.addEventListener('scroll', () => {
  document.getElementById('toTop').style.display = window.scrollY > 600 ? 'block' : 'none';
});

render();
</script>
</body>
</html>"""

html = (TEMPLATE
        .replace('__BOARD_NAME__', board_name)
        .replace('__TODAY__', TODAY)
        .replace('__CSV_NAME__', csv_name)
        .replace('__DATA__', data_json)
        .replace('__DELTA__', delta_json))

out = os.path.join(BASE, '%s-%s.html' % (board_name, TODAY))
with open(out, 'w', encoding='utf-8') as fh:
    fh.write(html)

priced = sum(1 for it in items if isinstance(it.get('price'), (int, float)) and it['price'])
store_names = sorted({it['store'] for it in items})
delta_count = (len(delta.get('added', [])) + len(delta.get('up', {})) + len(delta.get('down', {})))
print('唯一新品数: %d | 有价格: %d | 店铺数: %d | 有变动标记: %d'
      % (len(items), priced, len(store_names), delta_count))
if dup_note:
    print('同源去重: %s' % dup_note)
print('输出:', os.path.abspath(out), '(%d KB)' % (os.path.getsize(out) / 1024))
