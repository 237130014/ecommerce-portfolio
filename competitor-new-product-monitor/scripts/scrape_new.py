# -*- coding: utf-8 -*-
"""竞品新品抓取（bsk 驱动，真实登录态浏览器）

用 Tencent/BrowserSkill 的 `bsk` CLI 驱动你日常使用、已登录的浏览器，抓取京东/天猫
竞品店铺「新品」排序商品，输出统一的 jd_new_{序号}_{店名}.json。

为什么改用 bsk
--------------
传统无头浏览器在平台眼里从"身份"上就是假的（机器指纹、陌生账号、机房 IP），需要登录
的页面往往连门都进不去。bsk 复用你真实的 Chrome、真实登录态、本地真实 IP，把"设备/身份"
这一层风控直接抹平；遇到验证码/登录墙时通过 request-help 交给人处理，处理完自动继续。

依赖与环境
----------
1. bsk CLI：https://github.com/Tencent/BrowserSkill
2. 浏览器安装 BrowserSkill 扩展并连接（Chrome / Edge）
3. 在普通终端常驻运行：`bsk daemon start`（窗口保持不关）
4. 浏览器里已登录目标平台（京东 / 天猫）

用法
----
    python scrape_new.py [BASE] [选项]

常用选项
--------
    --stores 1,3,5        只抓指定序号店铺（默认全部）
    --platform jd|tmall   只抓指定平台（默认全部）
    --force               已抓过的店也重抓（默认跳过，实现断点续抓）
    --delay 4-9           每店之间随机延迟秒数区间（默认 4-9，防风控）
    --limit 120           单店最多保留条数
    --dump-html DIR       额外把每店页面 HTML 存盘，便于排查选择器

设计原则（防风控）
------------------
1. 串行抓取，绝不并发
2. 每店之间随机延迟，模拟人的浏览节奏
3. 命中登录墙 / 验证码时暂停并请求人工介入，处理完自动继续
4. 单店失败不影响其它店；失败如实报告，禁止编造数据
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime

BSK = ''


# --------------------------------------------------------------------------
# 通用工具
# --------------------------------------------------------------------------

def norm_path(p):
    """兼容 Git Bash 风格路径：/c/Users/xxx → C:/Users/xxx（Windows Python 不认前者）。"""
    if p and re.match(r'^/[a-zA-Z]/', p):
        return p[1].upper() + ':' + p[2:]
    return p


# --------------------------------------------------------------------------
# bsk 定位与调用
# --------------------------------------------------------------------------

def find_bsk() -> str:
    """定位 bsk 可执行文件：环境变量 > PATH > 默认安装目录。"""
    candidates = [
        os.environ.get('BSK_BIN'),
        shutil.which('bsk'),
        os.path.join(os.path.expanduser('~'), '.local', 'bin', 'bsk.exe'),
        os.path.join(os.path.expanduser('~'), '.local', 'bin', 'bsk'),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    sys.exit(
        '错误：未找到 bsk 可执行文件。请先安装 BrowserSkill：\n'
        '  Windows    : irm https://raw.githubusercontent.com/Tencent/BrowserSkill/main/install.ps1 | iex\n'
        '  macOS/Linux: curl -fsSL https://raw.githubusercontent.com/Tencent/BrowserSkill/main/install.sh | sh\n'
        '也可用环境变量 BSK_BIN 指定 bsk 的绝对路径。'
    )


def run_bsk(args, timeout=120):
    """执行 bsk 子命令，返回 (returncode, stdout, stderr)。

    固定 BSK_AUTO_START=0：daemon 应由用户在自己的终端常驻启动，脚本不代为拉起。
    否则在没有 daemon 的环境里，bsk 会卡在"自动启动"上而不是快速失败。
    """
    cmd = [BSK] + [str(a) for a in args]
    env = dict(os.environ)
    env['BSK_AUTO_START'] = '0'
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=timeout, env=env)
        return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()
    except subprocess.TimeoutExpired:
        return 124, '', '命令超时（%ss）' % timeout
    except OSError as exc:
        return 1, '', '无法执行 bsk：%s' % exc


def _loose_json(text):
    """宽容解析 bsk 输出：可能是裸 JSON，也可能包在 result/value/data 里。"""
    if not text:
        return None
    val = None
    try:
        val = json.loads(text)
    except Exception:
        match = re.search(r'[\[{].*[\]}]', text, re.S)
        if match:
            try:
                val = json.loads(match.group(0))
            except Exception:
                return text
        else:
            return text
    if isinstance(val, dict):
        for key in ('result', 'value', 'data', 'output'):
            if key in val:
                inner = val[key]
                if isinstance(inner, str):
                    try:
                        return json.loads(inner)
                    except Exception:
                        return inner
                return inner
    return val


def bsk_eval(session, js, timeout=60):
    """在页面内执行 JS 并返回解析后的值；失败返回 None。"""
    code, out, err = run_bsk(
        ['evaluate', '--session', session, '--timeout', '%ss' % timeout, '--json', js],
        timeout + 20,
    )
    if code != 0:
        return None
    return _loose_json(out)


# --------------------------------------------------------------------------
# 页面探测：登录墙 / 验证码 / 商品数量
# --------------------------------------------------------------------------

PROBE_JS = r"""
(() => {
  const q = (s) => document.querySelector(s);
  const n = (s) => document.querySelectorAll(s).length;
  const url = location.href;
  const title = document.title || '';
  const bodyLen = document.body ? ((document.body.innerText || '').length) : 0;
  const loginDom = !!(q('#loginname') || q('.login-box') || q('.login-form')
                      || q('#J_Quick2Static') || q('#J_QRCodeImg') || q('.password-login'));
  const loginUrl = /passport\.jd\.com|login\.taobao\.com|login\.tmall\.com|login\.jd\.com/.test(url);
  const captcha = !!(q('.nc_wrapper') || q('.nc-container') || q('#nc_1_wrapper')
                     || q('.slider-verify') || q('.captcha') || q('iframe[src*="captcha"]')
                     || /安全验证|人机验证|拖动滑块/.test(title));
  const items = n('dl.item[data-id]') + n('li[data-src]') + n('li.j-sku-item') + n('#J_goodsList li')
              + n('.J_TItems .item') + n('.product-item');
  return {url: url, title: title, bodyLen: bodyLen,
          loginWall: (loginDom || loginUrl), captcha: captcha, itemCount: items};
})()
"""


def probe(session):
    """探测当前页面状态。"""
    return bsk_eval(session, PROBE_JS, timeout=45) or {}


# --------------------------------------------------------------------------
# 懒加载处理：京东店铺页的「价格」和「图片」都是滚动后才加载的
# --------------------------------------------------------------------------

# 逐步滚动整页，给懒加载留出时间。放在单次 evaluate 里用 async/await 完成，
# 避免几十次 CLI 往返。（bsk evaluate 默认 await-promise=true）
SCROLL_JS = r"""
(async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const step = Math.max(300, Math.round(window.innerHeight * 0.75));
  let h = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
  let y = 0, steps = 0;
  while (y < h && steps < 40) {
    window.scrollTo(0, y);
    await sleep(650);
    y += step; steps++;
    h = Math.max(h, document.body.scrollHeight);
  }
  window.scrollTo(0, h);
  await sleep(1000);
  window.scrollTo(0, 0);
  await sleep(600);
  return JSON.stringify({ok: true, height: h, steps: steps});
})()
"""

# 统计加载完成度：卡片数 / 已出价格的数 / 已出真图的数
READY_JS = r"""
(() => {
  // 天猫：卡片是 dl.item[data-id]（店内搜索页），价格为密文（服务端直出，恒为就绪）
  const tmCards = document.querySelectorAll('dl.item[data-id]');
  if (tmCards.length) {
    const imgs = Array.from(document.querySelectorAll('dl.item[data-id] dt.photo img, dl.item[data-id] img'));
    const imgReady = imgs.filter(e => {
      const s = e.getAttribute('src') || '';
      return s && !/\.gif($|\?)/i.test(s) && /alicdn|taobao|tmall/.test(s);
    }).length;
    return {cards: tmCards.length, priced: tmCards.length, imgReady: imgReady, platform: 'tmall'};
  }
  const cards = document.querySelectorAll('li.jSubObject').length
              || document.querySelectorAll('.jItem').length
              || document.querySelectorAll('li.gl-item, #J_goodsList li').length;
  const priced = Array.from(document.querySelectorAll('.jdNum')).filter(e => {
    const t = (e.textContent || '').replace(/\u00a0/g, ' ').trim();
    return t && /\d/.test(t);
  }).length;
  const imgs = Array.from(document.querySelectorAll('.jPic img'));
  const imgReady = imgs.filter(e => {
    const s = e.getAttribute('src') || '';
    return s && !/cms\/g10\/|\.gif($|\?)/i.test(s);
  }).length;
  return {cards: cards, priced: priced, imgReady: imgReady, platform: 'jd'};
})()
"""


def wait_ready(session, timeout=25, interval=2.5, threshold=0.9):
    """轮询等待懒加载完成（价格与图片覆盖率达标），超时就返回当前状态。"""
    deadline = time.time() + timeout
    last = {}
    while True:
        state = bsk_eval(session, READY_JS, timeout=30)
        if isinstance(state, dict):
            last = state
            cards = state.get('cards') or 0
            if cards and (state.get('priced', 0) >= cards * threshold
                          and state.get('imgReady', 0) >= cards * threshold):
                return last
        if time.time() >= deadline:
            return last
        time.sleep(interval)


def settle_page(session):
    """滚动触发懒加载 + 等待就绪（最多两轮）。返回完成度状态。"""
    state = wait_ready(session, timeout=10)
    bsk_eval(session, SCROLL_JS, timeout=110)
    state = wait_ready(session, timeout=25)
    cards = (state or {}).get('cards') or 0
    if cards and (state.get('priced', 0) < cards * 0.9 or state.get('imgReady', 0) < cards * 0.9):
        bsk_eval(session, SCROLL_JS, timeout=110)
        state = wait_ready(session, timeout=20)
    return state or {}


def request_help(session, prompt, targets=None):
    """请用户人工接管（登录 / 验证码 / 确认），最长等待 5 分钟。"""
    args = ['request-help', '--session', session, '--prompt', prompt, '--timeout', '5m']
    for target in (targets or []):
        args += ['--target', target]
    code, _out, _err = run_bsk(args, timeout=330)
    return code == 0


def navigate(session, url, wait='load', timeout='60s'):
    """导航到目标页。

    默认用 load 而非 networkidle：京东/天猫页面常驻埋点与轮询请求，
    networkidle 可能永远不触发，导致误报超时。真正的"内容就绪"由 settle_page 负责。
    """
    return run_bsk(['navigate', url, '--session', session,
                    '--wait-until', wait, '--timeout', timeout], timeout=100)


# --------------------------------------------------------------------------
# 页面内数据提取脚本
# --------------------------------------------------------------------------

_EXTRACT_COMMON = r"""
  const abs = (u) => { try { return new URL(u, location.href).href; } catch (e) { return u || ''; } };
  const firstText = (el, sels) => {
    for (const s of sels) {
      const n = el.querySelector(s);
      if (n) { const t = (n.textContent || '').replace(/\s+/g, ' ').trim(); if (t) return t; }
    }
    return '';
  };
  const firstAttr = (el, sels, attrs) => {
    for (const s of sels) {
      const n = el.querySelector(s) || (el.matches && el.matches(s) ? el : null);
      if (!n) continue;
      for (const a of attrs) { const v = n.getAttribute(a); if (v) return v; }
    }
    return '';
  };
  const toNum = (s) => {
    const m = String(s || '').replace(/,/g, '').match(/\d+(\.\d+)?/);
    return m ? parseFloat(m[0]) : null;
  };
"""

EXTRACT_JD_JS = r"""
(() => {
%s
  // 京东店铺列表页（mall.jd.com / *.jd.com/view_search）真实卡片是 li.jSubObject > .jItem
  // 注意：li[data-src] 是缩略图轮播项，不是商品卡片，不能作为主选择器
  let cards = Array.from(document.querySelectorAll('li.jSubObject'));
  if (!cards.length) cards = Array.from(document.querySelectorAll('.jItem'));
  if (!cards.length) cards = Array.from(document.querySelectorAll('#J_goodsList li, li.gl-item, .gl-warp li, .goods-list li, li.j-sku-item'));
  if (!cards.length) cards = Array.from(document.querySelectorAll('li[data-src]'));
  const out = [], seen = new Set();
  cards.forEach((li) => {
    if (!li.querySelector) return;
    const a = li.querySelector('.jDesc a[href*="item.jd.com"], .jPic a[href*="item.jd.com"], a[href*="item.jd.com"], a[href*="item.htm"]');
    const href = a ? a.getAttribute('href') : (li.getAttribute('data-href') || '');
    let url = href ? abs(href) : '';
    url = url.split('#')[0].split('?')[0];
    if (!url || !/item\.jd\.com/.test(url) || seen.has(url)) return;
    seen.add(url);
    // 图片：京东用 J_imgLazyload 占位，真实地址在 original 属性；未滚动到时 src 是 gif 占位图。
    // 统一转绝对地址（京东返回 //img13.360buyimg.com/... 形式）。
    const isBadImg = (u) => !u || /cms\/g10\/|\.gif($|\?)/i.test(u);
    const imgEl = li.querySelector('.jPic img') || li.querySelector('img');
    let imgRaw = '';
    if (imgEl) {
      for (const a of ['original', 'data-src', 'data-lazy-img', 'data-ks-lazyload', 'src']) {
        const v = imgEl.getAttribute(a);
        if (!isBadImg(v)) { imgRaw = v; break; }
      }
    }
    if (isBadImg(imgRaw)) {
      // 兜底：卡片内缩略图轮播项的 data-src（服务端渲染，始终可读）
      const thumb = li.querySelector('[data-src]');
      const tv = thumb ? thumb.getAttribute('data-src') : '';
      if (!isBadImg(tv)) imgRaw = tv;
    }
    const img = imgRaw ? abs(imgRaw) : '';
    let title = firstText(li, ['.jDesc a', '.jDesc', '.p-name a', '.p-name', '.sku-name', '.p-title', '.name']);
    if (!title && a) title = (a.getAttribute('title') || a.textContent || '').replace(/\s+/g, ' ').trim();
    if (!title) title = firstAttr(li, ['img'], ['alt']);
    // 价格：优先取 .jdNum 文本；兜底 preprice 属性。
    // 绝不能用 jdprice 属性——那是 SKU 编号（曾导致价格字段被写成商品 ID）。
    let price = toNum(firstText(li, ['.jdNum', '.jPrice .jdPrice', '.p-price', '.price', 'strong.J_price', '.J_price']));
    if (price === null) price = toNum(firstAttr(li, ['.jdNum[preprice]', '[preprice]'], ['preprice']));
    const skuId = firstAttr(li, ['.jdNum'], ['jdprice']) || firstAttr(li, ['[data-id]'], ['data-id']);
    const idm = url.match(/item\.jd\.com\/(\d+)/) || url.match(/(\d{6,})/);
    const id = skuId || (idm ? idm[1] : '');
    // 兜底二次校验：价格不可能等于自己的 SKU 号
    if (price !== null && id && String(Math.trunc(price)) === String(id)) price = null;
    const comments = firstText(li, ['.jCommentNum', '.p-commit', '.p-commit a', '.comment', '.J_comment']);
    out.push({ rank: out.length + 1, title: title, price: price, comments: comments,
               image: img, url: url, id: id });
  });
  return out;
})()
""" % _EXTRACT_COMMON

EXTRACT_TMALL_JS = r"""
(new Promise(async (resolve) => {
%s
  // ---------- 天猫价格字体解密 ----------
  // 天猫店铺列表页的价格用自定义字体加密：DOM 里是密文（如「曍燰忈叱捨澥」），
  // 浏览器靠 @font-face（AlibabaSans102CustomFont 等）渲染成正常数字，且映射逐页随机。
  // 解法：把密文字符和 0-9/. 用同一字体画到 canvas，逐像素比对字形，反查映射。
  const decodeSetup = async () => {
    const els = Array.from(document.querySelectorAll('.c-price, .g_price'));
    const cipher = new Set();
    els.forEach(e => {
      const t = (e.textContent || '').trim();
      for (const ch of t) if (ch.trim() && !/[0-9.,]/.test(ch)) cipher.add(ch);
    });
    if (!cipher.size) return null;
    let font = null;
    for (const f of ['AlibabaSans102CustomFont', 'VerdanaItemRecommendFont']) {
      try { await document.fonts.load('40px "' + f + '"'); } catch (e) {}
      if (document.fonts.check('40px "' + f + '"')) { font = f; break; }
    }
    if (!font) return null;
    const glyph = (ch) => {
      const c = document.createElement('canvas');
      c.width = 48; c.height = 48;
      const ctx = c.getContext('2d');
      ctx.font = '40px "' + font + '"';
      ctx.textBaseline = 'top';
      ctx.fillText(ch, 4, 2);
      const d = ctx.getImageData(0, 0, 48, 48).data;
      let h = '';
      for (let y = 0; y < 48; y += 2) {
        let row = 0;
        for (let x = 0; x < 48; x += 2) row = (row << 1) | (d[(y * 48 + x) * 4 + 3] > 128 ? 1 : 0);
        h += row.toString(16);
      }
      return h;
    };
    const digits = '0123456789.';
    const digHash = {};
    for (const d of digits) digHash[d] = glyph(d);
    const map = {};
    for (const ch of cipher) {
      const h = glyph(ch);
      for (const d of digits) { if (digHash[d] === h) { map[ch] = d; break; } }
    }
    return (s) => Array.from(s).map(ch => (ch in map) ? map[ch] : ch).join('');
  };
  let decode = null;
  try { decode = await decodeSetup(); } catch (e) {}

  // 真实卡片是 dl.item[data-id]（店内搜索页）；.J_TItems .item / .product-item 为旧版兜底。
  let cards = Array.from(document.querySelectorAll('dl.item[data-id]'));
  if (!cards.length) cards = Array.from(document.querySelectorAll('.J_TItems .item, #J_ItemList .item, .product-item'));
  if (!cards.length) cards = Array.from(document.querySelectorAll('.item'));
  const out = [], seen = new Set();
  cards.forEach((li) => {
    if (!li.querySelector) return;
    const a = li.querySelector('a[href*="detail.tmall.com"], a[href*="item.taobao.com"], a[href*="detail.tmall.hk"]');
    if (!a) return;
    const raw = abs(a.getAttribute('href'));
    // 关键：天猫商品 ID 在 query（?id=xxx）里，绝不能整段 split('?')——
    // 否则所有商品 URL 都变成同一个 detail.tmall.com/item.htm，被去重成 1 条。
    const idm = raw.match(/[?&]id=(\d{6,})/);
    if (!idm) return;
    const id = idm[1];
    if (seen.has(id)) return;
    seen.add(id);
    const url = 'https://detail.tmall.com/item.htm?id=' + id;
    const imgRaw = firstAttr(li, ['dt.photo img', '.productImg img', 'img'], ['src', 'data-src', 'data-ks-lazyload']);
    const img = imgRaw ? abs(imgRaw) : '';
    let title = firstText(li, ['.item-name', '.productTitle', '.title', '.product-title', '.name']);
    if (!title) { const alt = firstAttr(li, ['dt.photo img', 'img'], ['alt']); if (alt) title = alt.trim(); }
    if (!title && a) title = (a.getAttribute('title') || a.textContent || '').replace(/\s+/g, ' ').trim();
    let price = null;
    const pEl = li.querySelector('.c-price') || li.querySelector('.g_price')
             || li.querySelector('.productPrice, .price, .item-price, strong');
    if (pEl) {
      let t = (pEl.textContent || '').trim();
      if (decode && /[^\x00-\x7F]/.test(t)) t = decode(t);
      price = toNum(t);
    }
    const comments = firstText(li, ['.sale-num', '.productSellNum', '.sell-num', '.comment']);
    out.push({ rank: out.length + 1, title: title, price: price, comments: comments,
               image: img, url: url, id: id });
  });
  resolve(out);
}))
""" % _EXTRACT_COMMON


# --------------------------------------------------------------------------
# 店铺清单与新品排序
# --------------------------------------------------------------------------

def apply_new_sort(url, platform):
    """把店铺列表页 URL 转成「新品」倒序 URL。

    京东：view_search 路径第 5 段置 1 表示新品排序（实测规则），形如 -0-1-0-0-
    天猫：追加/替换 orderType=newOn_desc
    """
    if platform == 'jd':
        match = re.match(r'^(.*?view_search-)([\d-]+)(\.html.*)$', url)
        if match:
            parts = match.group(2).split('-')
            if len(parts) >= 5:
                parts[4] = '1'
                return match.group(1) + '-'.join(parts) + match.group(3)
        return url
    if platform == 'tmall':
        # 实测：category.htm / search.htm 往往只渲染店铺外壳（0 商品），
        # 「店内搜索页」view_shop.htm?search=y 才会渲染商品卡片（dl.item）。
        m = re.match(r'^(https?://[^/]+/)(?:category|search|view_shop)\.htm(\?.*)?$', url)
        if m:
            query = m.group(2) or ''
            if 'search=' not in query:
                query += ('&' if '?' in query else '?') + 'search=y'
            if 'orderType=' in query:
                query = re.sub(r'orderType=[^&]*', 'orderType=newOn_desc', query)
            else:
                query += ('&' if '?' in query else '?') + 'orderType=newOn_desc'
            return m.group(1) + 'view_shop.htm' + query
        if 'orderType=' in url:
            return re.sub(r'orderType=[^&]*', 'orderType=newOn_desc', url)
        return url + ('&' if '?' in url else '?') + 'orderType=newOn_desc'
    return url


# stores.example.json 里占位符的特征。本技能不附带任何真实店铺，
# 使用者必须自己填店铺 URL；命中这些特征时直接报错，避免拿别人的店去抓。
PLACEHOLDER_MARKS = ('<', '>', '{', '}', '你的', '示例店', 'example.', 'xxx')


def url_hint(url, platform):
    """检查店铺 URL 是否可用于抓取，返回 (是否可用, 提示)。

    实测结论：京东/天猫的「店铺首页」只有导航和装修区块，不含商品卡片；
    必须使用「商品列表页」URL，否则会抓到 0 条。
    """
    if not url or not url.strip():
        return False, ('店铺 URL 为空。请复制 references/stores.example.json 为 stores.json，\n'
                       '    填入你自己的店铺「商品列表页」URL。')
    if any(m in url or m in url.lower() for m in PLACEHOLDER_MARKS):
        return False, ('这看起来还是 stores.example.json 里的占位符，不是真实店铺 URL。\n'
                       '    本技能不附带任何店铺，请替换成你自己的店铺「商品列表页」URL 后再跑。')
    if platform == 'jd':
        if 'view_search' not in url:
            return False, ('京东需要「商品列表页」URL（须含 view_search）。店铺首页没有商品卡片。\n'
                           '    获取方式：打开店铺 → 点左侧「所有商品」或任一分类 → 复制地址栏 URL。')
    elif platform == 'tmall':
        if not any(k in url for k in ('shop', 'category', 'search', 'list')):
            return False, ('天猫需要「商品列表页」URL。\n'
                           '    获取方式：打开店铺 → 点「全部商品」或某分类 → 复制地址栏 URL。')
    return True, ''


def load_stores(path, only_nos=None, only_platform=None):
    with open(path, encoding='utf-8') as fh:
        cfg = json.load(fh)
    stores = cfg.get('stores', []) if isinstance(cfg, dict) else (cfg or [])
    out = []
    for store in stores:
        if only_nos and str(store.get('no', '')).strip() not in only_nos:
            continue
        if only_platform and store.get('platform') != only_platform:
            continue
        out.append(store)
    return out


def parse_delay(spec):
    """解析 4-9 / 5 这类延迟区间。"""
    try:
        if '-' in spec:
            lo, hi = spec.split('-', 1)
            return max(0.0, float(lo)), max(0.0, float(hi))
        value = float(spec)
        return value, value
    except Exception:
        return 4.0, 9.0


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------

def main():
    global BSK

    parser = argparse.ArgumentParser(description='竞品新品抓取（bsk 驱动，真实登录态浏览器）')
    parser.add_argument('base', nargs='?', default='jd-baseline', help='数据目录（默认 jd-baseline）')
    parser.add_argument('--stores', default='', help='只抓指定序号，如 1,3,5')
    parser.add_argument('--platform', choices=['jd', 'tmall'], help='只抓指定平台')
    parser.add_argument('--force', action='store_true', help='已抓过的店也重抓')
    parser.add_argument('--delay', default='4-9', help='每店随机延迟秒数区间，如 4-9')
    parser.add_argument('--limit', type=int, default=120, help='单店最多保留条数')
    parser.add_argument('--dump-html', default='', help='把每店页面 HTML 额外存到该目录')
    parser.add_argument('--stores-file', default='', help='店铺清单路径（默认 skill/references/stores.json）')
    args = parser.parse_args()

    BSK = find_bsk()
    base = norm_path(args.base)
    os.makedirs(base, exist_ok=True)

    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    stores_file = norm_path(args.stores_file) if args.stores_file else os.path.join(skill_dir, 'references', 'stores.json')
    if not os.path.isfile(stores_file):
        sys.exit('错误：未找到店铺清单 %s\n请参考 references/stores.example.json 建立 stores.json。' % stores_file)

    only_nos = {x.strip() for x in args.stores.split(',') if x.strip()}
    stores = load_stores(stores_file, only_nos, args.platform)
    if not stores:
        sys.exit('没有匹配的店铺，请检查 --stores / --platform。')

    lo, hi = parse_delay(args.delay)

    # 1) 检查 daemon
    code, out, _err = run_bsk(['status', '--json'], timeout=30)
    if code != 0:
        sys.exit('错误：bsk daemon 未运行。请先在普通终端执行 `bsk daemon start`（窗口保持不关），再重试。\n%s' % out)

    # 2) 启动会话
    code, out, err = run_bsk(['session', 'start', '--json', '--no-focus', '--name', 'competitor-monitor'], timeout=90)
    if code != 0:
        sys.exit('错误：无法创建会话（浏览器扩展是否已安装并连接？）\n%s' % (err or out))
    parsed = _loose_json(out)
    session_id = ''
    if isinstance(parsed, dict):
        session_id = parsed.get('session_id') or parsed.get('id') or parsed.get('session') or ''
    if not session_id:
        match = re.search(r'([0-9a-zA-Z][0-9a-zA-Z_-]{7,})', out)
        session_id = match.group(1) if match else ''
    if not session_id:
        sys.exit('错误：未能解析 session id，bsk 输出：%s' % out)
    print('会话已创建：%s' % session_id)

    results = []
    try:
        for index, store in enumerate(stores):
            raw_no = str(store.get('no', index + 1)).strip()
            no = raw_no.zfill(2) if raw_no.isdigit() else raw_no
            name = str(store.get('name', 'store%s' % no)).strip()
            platform = store.get('platform', 'jd')
            out_file = os.path.join(base, 'jd_new_%s_%s.json' % (no, name))

            if os.path.isfile(out_file) and not args.force:
                print('[%s] %s 已有数据，跳过（--force 可重抓）' % (no, name))
                results.append((no, name, 'skipped', 0))
                continue

            ok, hint = url_hint(store.get('url', ''), platform)
            if not ok:
                print('[%s] %s ！URL 不可用，跳过。\n    %s' % (no, name, hint))
                results.append((no, name, 'bad_url', 0))
                continue

            url = apply_new_sort(store.get('url', ''), platform)
            print('[%s] %s（%s）→ %s' % (no, name, platform, url))

            code, o, e = navigate(session_id, url)
            if code != 0:
                print('    ! 首次导航失败，重试一次：%s' % str(e or o)[:120])
                time.sleep(3)
                code, o, e = navigate(session_id, url)
            if code != 0:
                print('    ! 导航失败：%s' % str(e or o)[:200])
                results.append((no, name, 'navigate_failed', 0))
                continue
            time.sleep(2)

            # 登录墙 / 验证码处理
            state = probe(session_id)
            if state.get('loginWall'):
                print('    检测到登录墙，请求人工登录 ...')
                request_help(session_id, '请在打开的窗口里登录 %s 账号（%s），完成后会自动继续。' % (platform.upper(), name))
                navigate(session_id, url)
                time.sleep(2)
                state = probe(session_id)
            if state.get('captcha'):
                print('    检测到验证码/滑块，请求人工处理 ...')
                request_help(session_id, '页面出现验证码/滑块，请手动完成验证，完成后会自动继续。')
                run_bsk(['reload', '--session', session_id], timeout=60)
                time.sleep(3)
                state = probe(session_id)

            # 滚动触发懒加载：京东店铺页的「价格」和「图片」都要滚动后才填充
            state = settle_page(session_id)
            print('    加载完成度：卡片 %s / 出价 %s / 出图 %s'
                  % (state.get('cards'), state.get('priced'), state.get('imgReady')))

            js = EXTRACT_TMALL_JS if platform == 'tmall' else EXTRACT_JD_JS
            items = bsk_eval(session_id, js, timeout=60)
            if not isinstance(items, list):
                print('    ! 提取失败，原始返回：%s' % str(items)[:200])
                results.append((no, name, 'extract_failed', 0))
                continue

            items = [it for it in items if isinstance(it, dict) and it.get('title') and it.get('url')]
            items = items[:args.limit]
            payload = {
                'store': name,
                'platform': platform,
                'url': url,
                'sort': 'new',
                'fetched_at': datetime.now().isoformat(timespec='seconds'),
                'count': len(items),
                'items': items,
            }
            with open(out_file, 'w', encoding='utf-8') as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            print('    OK 抓到 %d 条 → %s' % (len(items), out_file))
            results.append((no, name, 'ok', len(items)))

            if args.dump_html:
                os.makedirs(args.dump_html, exist_ok=True)
                run_bsk(['get-html', '--session', session_id,
                         '--out', os.path.join(args.dump_html, '%s_%s.html' % (no, name))], timeout=90)

            if index < len(stores) - 1:
                wait = random.uniform(lo, hi)
                print('    等待 %.1fs ...' % wait)
                time.sleep(wait)
    finally:
        run_bsk(['session', 'stop', session_id], timeout=45)

    # 汇总
    print('\n===== 抓取汇总 =====')
    ok = [r for r in results if r[2] == 'ok']
    bad = [r for r in results if r[2] not in ('ok', 'skipped')]
    skipped = [r for r in results if r[2] == 'skipped']
    print('成功 %d 店 / 跳过 %d 店 / 失败 %d 店' % (len(ok), len(skipped), len(bad)))
    for no, name, status, _cnt in bad:
        print('  ! [%s] %s：%s' % (no, name, status))
    if bad:
        print('失败店铺可重跑本脚本（已成功的店会跳过，不会覆盖）。')


if __name__ == '__main__':
    main()
