# -*- coding: utf-8 -*-
"""得物「商机推荐 › 高搜词 › 查看更多类目热点」抓取器。

用 bsk（BrowserSkill，真实登录态浏览器）驱动页面，通过**接口响应拦截**拿到
每条热点的完整明细（商品画像 / 人群 / 场景 / 机会价格 / 相似机会品 / 环比），
不逐条点开卡片。

用法：
    python scrape.py --session nmyx --out ./runs/2026-10-20 --groups A,B
    python scrape.py --session nmyx --out ./runs/2026-10-20 --config my_groups.json
    python scrape.py --session nmyx --out ./runs/2026-10-20 --group A --max-pages 3

输出：<out>/data/cap_A.json、cap_B.json（每页完整请求+响应）
"""
import argparse
import json
import os
import subprocess
import sys
import time

# --------------------------------------------------------------------------------------
# 默认类目组：对应「流行饰品/眼镜/服配 下 7 个二级」与「黄金/珠宝/翡翠/玉石 一级」
# mode = top       → 勾选第 0 级节点本身（= 整个一级类目）
# mode = children  → 先展开第 0 级节点，再逐个勾选它的第 1 级子类目
# --------------------------------------------------------------------------------------
DEFAULT_GROUPS = [
    {
        "key": "A",
        "label": "流行饰品/眼镜/服配",
        "mode": "children",
        "parent": "流行饰品/眼镜/服配",
        "items": ["首饰", "玛瑙/玉髓", "水晶", "黑曜石", "朱砂", "其他玉石", "石英岩玉"],
    },
    {
        "key": "B",
        "label": "黄金/珠宝/翡翠/玉石",
        "mode": "top",
        "parent": "黄金/珠宝/翡翠/玉石",
        "items": [],
    },
]

# --------------------------------------------------------------------------------------
# 页面内 JS 片段
# --------------------------------------------------------------------------------------
JS_HOOK = r"""
(() => {
  if (window.__cap) return 'already hooked';
  window.__cap = [];
  const want = /chanceRecommend|hotTrack|HotTrack|opportunity/i;
  const of = window.fetch;
  window.fetch = async function(...args) {
    const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
    const opt = args[1] || (typeof args[0] === 'object' ? args[0] : {});
    let body = opt && opt.body;
    try { if (body instanceof FormData) body = JSON.stringify(Object.fromEntries(body)); } catch (e) {}
    const res = await of.apply(this, args);
    if (want.test(url)) {
      try {
        const txt = await res.clone().text();
        window.__cap.push({url, method: (opt.method || 'GET'), reqBody: String(body || '').slice(0, 5000), resp: txt.slice(0, 2000000)});
      } catch (e) { window.__cap.push({url, err: String(e)}); }
    }
    return res;
  };
  const oo = XMLHttpRequest.prototype.open, os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(m, u) { this.__u = u; this.__m = m; return oo.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function(b) {
    this.addEventListener('load', function() {
      if (want.test(this.__u || '')) {
        try { window.__cap.push({url: this.__u, method: this.__m, reqBody: String(b || '').slice(0, 5000), resp: String(this.responseText).slice(0, 2000000)}); } catch (e) {}
      }
    });
    return os.apply(this, arguments);
  };
  return 'hooked';
})()
"""

JS_RESET_CAP = "(() => { window.__cap = []; return 'cleared'; })()"
JS_CAP_LEN = "(() => (window.__cap || []).length)()"
JS_CAP_AT = "(() => { const c = window.__cap || []; return c[%d] || null; })()"

# 打开「查看更多类目热点」入口（按文案定位，不依赖哈希类名）
JS_TAG_SEEALL = r"""
(() => {
  document.querySelectorAll('#bskSeeAll').forEach(e => e.removeAttribute('id'));
  const cands = Array.from(document.querySelectorAll('div,span,a,button'))
    .filter(e => (e.textContent || '').trim() === '查看更多类目热点' && e.children.length <= 1);
  if (!cands.length) return { err: '未找到「查看更多类目热点」入口' };
  const el = cands[cands.length - 1];
  el.id = 'bskSeeAll';
  return { ok: 1, tag: el.tagName };
})()
"""

# 定位「列表抽屉」：优先含类目级联的那一层（详情抽屉没有 cascader，避免叠层误命中）
JS_ROOM = r"""
const __room = (function () {
  const all = Array.from(document.querySelectorAll('.ant-drawer-content'));
  return all.find(d => d.querySelector('.ant-cascader')) || all[all.length - 1] || null;
})();
"""

JS_DRAWER_STATE = r"""
(() => {
  const rooms = Array.from(document.querySelectorAll('.ant-drawer-content'))
    .filter(d => d.querySelector('[class*=cardGrid]') || d.querySelector('[class*=cardTitle]'));
  const d = rooms.find(x => x.querySelector('.ant-cascader')) || rooms[rooms.length - 1];
  if (!d) return { open: false, drawers: document.querySelectorAll('.ant-drawer-content').length };
  const p = d.querySelector('.ant-pagination');
  return {
    open: true,
    drawers: document.querySelectorAll('.ant-drawer-content').length,
    cards: (d.querySelector('[class*=cardGrid]') || { children: [] }).children.length,
    hasPager: !!p,
    hasCascader: !!d.querySelector('.ant-cascader'),
    active: p ? (p.querySelector('.ant-pagination-item-active') || {}).textContent : '',
    total: p ? (p.querySelector('.ant-pagination-total-text') || {}).textContent : '',
    nextDis: p ? !!p.querySelector('.ant-pagination-next.ant-pagination-disabled') : true
  };
})()
"""

JS_TAG_CASCADER = r"""
(() => {
  document.querySelectorAll('#bskCasc').forEach(e => e.removeAttribute('id'));
  const all = Array.from(document.querySelectorAll('.ant-drawer-content'));
  const d = all.find(x => x.querySelector('.ant-cascader'));
  if (!d) return { err: '抽屉内无类目级联筛选器' };
  const c = d.querySelector('.ant-cascader');
  const s = c.querySelector('.ant-select-selector');
  if (!s) return { err: 'no selector' };
  s.id = 'bskCasc';
  return { ok: 1, hasClear: !!c.querySelector('.ant-select-clear') };
})()
"""

JS_TAG_CLEAR = r"""
(() => {
  document.querySelectorAll('#bskClear').forEach(e => e.removeAttribute('id'));
  const all = Array.from(document.querySelectorAll('.ant-drawer-content'));
  const d = all.find(x => x.querySelector('.ant-cascader'));
  const c = d && d.querySelector('.ant-cascader');
  const cl = c && c.querySelector('.ant-select-clear');
  if (!cl) return { ok: 0, reason: 'no clear icon' };
  cl.id = 'bskClear';
  return { ok: 1 };
})()
"""

# 读取当前可见下拉的各级菜单项（title 才是完整文本）
JS_LEVELS = r"""
(() => {
  const drops = Array.from(document.querySelectorAll('.ant-cascader-dropdown'))
    .filter(d => !d.className.includes('hidden'));
  if (!drops.length) return { err: 'dropdown closed', levels: [] };
  const d = drops[drops.length - 1];
  return {
    ok: 1,
    levels: Array.from(d.querySelectorAll('.ant-cascader-menu')).map(m =>
      Array.from(m.querySelectorAll('.ant-cascader-menu-item')).map(e => ({
        t: (e.getAttribute('title') || e.textContent || '').trim(),
        checked: e.getAttribute('aria-checked') === 'true'
      })))
  };
})()
"""

# 给指定层级的菜单项打标记：--tag=hover 用于展开，--tag=cb 用于勾选
JS_TAG_ITEM = r"""
(() => {
  const lv = %d, txt = %s, tag = %s;
  document.querySelectorAll('#bskItem').forEach(e => e.removeAttribute('id'));
  const drops = Array.from(document.querySelectorAll('.ant-cascader-dropdown'))
    .filter(d => !d.className.includes('hidden'));
  if (!drops.length) return { err: 'dropdown closed' };
  const d = drops[drops.length - 1];
  const menus = Array.from(d.querySelectorAll('.ant-cascader-menu'));
  const m = menus[lv];
  if (!m) return { err: 'no level ' + lv, levels: menus.length };
  const items = Array.from(m.querySelectorAll('.ant-cascader-menu-item'));
  const it = items.find(e => (e.getAttribute('title') || e.textContent || '').trim() === txt);
  if (!it) return { err: 'missing: ' + txt, level: lv, avail: items.map(e => e.getAttribute('title')) };
  if (tag === 'hover') {
    it.id = 'bskItem';
    return { ok: 1, level: lv, txt, action: 'hover' };
  }
  const cb = it.querySelector('.ant-cascader-checkbox');
  if (!cb) return { err: 'item 无 checkbox（该级不可多选）', txt };
  cb.id = 'bskItem';
  return { ok: 1, level: lv, txt, action: 'check', checked: it.getAttribute('aria-checked') };
})()
"""

JS_CHIPS = r"""
(() => {
  const all = Array.from(document.querySelectorAll('.ant-drawer-content'));
  const d = all.find(x => x.querySelector('.ant-cascader'));
  const c = d && d.querySelector('.ant-cascader');
  if (!c) return { chips: [], total: '' };
  const p = d.querySelector('.ant-pagination');
  return {
    chips: Array.from(c.querySelectorAll('.ant-select-selection-item'))
      .map(e => e.getAttribute('title') || e.textContent.trim()),
    total: p ? (p.querySelector('.ant-pagination-total-text') || {}).textContent : '',
    active: p ? (p.querySelector('.ant-pagination-item-active') || {}).textContent : ''
  };
})()
"""

JS_PAGER = r"""
(() => {
  const all = Array.from(document.querySelectorAll('.ant-drawer-content'));
  const d = all.find(x => x.querySelector('.ant-pagination'));
  const p = d && d.querySelector('.ant-pagination');
  if (!p) return { ok: 0 };
  return {
    ok: 1,
    active: (p.querySelector('.ant-pagination-item-active') || {}).textContent || '',
    total: (p.querySelector('.ant-pagination-total-text') || {}).textContent || '',
    nextDis: !!p.querySelector('.ant-pagination-next.ant-pagination-disabled'),
    prevDis: !!p.querySelector('.ant-pagination-prev.ant-pagination-disabled')
  };
})()
"""


# --------------------------------------------------------------------------------------
# bsk 驱动
# --------------------------------------------------------------------------------------
class Bsk:
    def __init__(self, session, verbose=True):
        self.session = session
        self.verbose = verbose

    def run(self, *args, timeout=120):
        cmd = ["bsk", *args, "--session", self.session]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout)
        return r.stdout.strip()

    def ev(self, js, retry=3):
        for _ in range(retry):
            try:
                raw = self.run("evaluate", js, "--json")
                return json.loads(raw).get("value")
            except Exception:
                time.sleep(1.2)
        return None

    def click(self, selector):
        return self.run("click", "--selector", selector)

    def hover(self, selector):
        return self.run("hover", "--selector", selector)

    def escape(self):
        return self.run("press", "Escape")

    def wait(self, sec):
        time.sleep(sec)

    def log(self, msg):
        if self.verbose:
            print(msg, flush=True)


def wait_until(fn, timeout=25, interval=0.5, desc=""):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = fn()
        if v:
            return v
        time.sleep(interval)
    return None


# --------------------------------------------------------------------------------------
# 页面操作
# --------------------------------------------------------------------------------------
def ensure_drawer(bsk):
    st = bsk.ev(JS_DRAWER_STATE)
    if st and st.get("open") and st.get("hasCascader"):
        bsk.log("  抽屉已打开")
        return True
    bsk.log("  点击「查看更多类目热点」…")
    tag = bsk.ev(JS_TAG_SEEALL)
    if not tag or not tag.get("ok"):
        bsk.log("  ! %s" % (tag or {}).get("err", "入口定位失败"))
        return False
    bsk.click("#bskSeeAll")
    ok = wait_until(lambda: (lambda s: s if s and s.get("open") and s.get("cards") else None)(
        bsk.ev(JS_DRAWER_STATE)), timeout=30, desc="drawer")
    if not ok:
        bsk.log("  ! 抽屉未出现")
        return False
    bsk.wait(1.5)
    return True


def clear_filter(bsk):
    """清空已勾选的类目，回到全量。"""
    bsk.ev(JS_TAG_CASCADER)
    bsk.hover("#bskCasc")          # 清除图标只在 hover 时出现
    bsk.wait(0.6)
    t = bsk.ev(JS_TAG_CLEAR)
    if not t or not t.get("ok"):
        bsk.log("  类目筛选本来就是空的")
        return True
    bsk.click("#bskClear")
    bsk.wait(2.6)
    st = bsk.ev(JS_CHIPS)
    bsk.log("  已清空 | %s" % (st or {}).get("total", ""))
    return True


def open_cascader(bsk):
    bsk.ev(JS_TAG_CASCADER)
    bsk.click("#bskCasc")
    ok = wait_until(lambda: (lambda r: r if r and r.get("ok") else None)(bsk.ev(JS_LEVELS)),
                    timeout=10)
    return bool(ok)


def _tag_item(bsk, level, text, action):
    js = JS_TAG_ITEM % (level, json.dumps(text, ensure_ascii=False), json.dumps(action))
    return bsk.ev(js)


def apply_group(bsk, grp):
    """按类目组勾选筛选条件。返回是否成功。"""
    mode = grp.get("mode", "top")
    parent = grp.get("parent") or grp.get("label")
    items = grp.get("items") or []
    bsk.log("  应用类目：%s（%s）" % (grp.get("label"), mode))

    if not open_cascader(bsk):
        bsk.log("  ! 类目下拉打不开")
        return False

    if mode == "top":
        r = _tag_item(bsk, 0, parent, "check")
        if not r or not r.get("ok"):
            bsk.log("  ! 一级节点标记失败: %s" % json.dumps(r, ensure_ascii=False)[:200])
            return False
        bsk.click("#bskItem")
        bsk.wait(1.4)
    else:
        # 先 hover 展开第 0 级，再勾第 1 级 —— 直接点第 0 级会把整个一级类目勾上
        r = _tag_item(bsk, 0, parent, "hover")
        if not r or not r.get("ok"):
            bsk.log("  ! 一级节点展开失败: %s" % json.dumps(r, ensure_ascii=False)[:200])
            return False
        bsk.hover("#bskItem")
        # 等二级菜单挂载出来（hover 是异步渲染，固定 sleep 会在慢机器上翻车）
        def _lv1_ready():
            r = bsk.ev(JS_LEVELS) or {}
            lv = r.get("levels") or []
            return lv[1] if len(lv) > 1 and lv[1] else None

        if not wait_until(_lv1_ready, timeout=8, interval=0.4):
            bsk.log("  ! 二级菜单未展开")
            return False
        got, miss = [], []
        for name in items:
            r = _tag_item(bsk, 1, name, "check")
            if not r or not r.get("ok"):
                miss.append("%s(%s)" % (name, (r or {}).get("err", "?")))
                continue
            if r.get("checked") == "true":
                got.append(name + "*")
                continue
            bsk.click("#bskItem")
            bsk.wait(1.1)
            got.append(name)
        bsk.log("    勾选 %d/%d：%s" % (len(got), len(items), " ".join(got)))
        if miss:
            bsk.log("    ! 未选中：%s" % ", ".join(miss))
        if not got:
            return False

    bsk.escape()
    bsk.wait(3.2)
    st = bsk.ev(JS_CHIPS) or {}
    bsk.log("  筛选结果：%s | 已选 %s" % (st.get("total", ""), st.get("chips")))
    return True


# --------------------------------------------------------------------------------------
# 接口响应捕获
# --------------------------------------------------------------------------------------
def _cap_pages(bsk, base, pages):
    """把新增的响应按 pageNum 归档。返回新的 base。"""
    n = bsk.ev(JS_CAP_LEN) or 0
    if n <= base:
        return base, None
    last = None
    for i in range(base, n):
        e = bsk.ev(JS_CAP_AT % i)
        if not e or not e.get("resp"):
            continue
        try:
            body = json.loads(e.get("reqBody") or "{}")
        except Exception:
            body = {}
        pn = body.get("pageNum")
        if not pn:
            continue
        if str(pn) not in pages:
            pages[str(pn)] = {"reqBody": e.get("reqBody"), "resp": e.get("resp"),
                              "url": e.get("url"), "capturedAt": time.strftime("%Y-%m-%d %H:%M:%S")}
            last = pn
    return n, last


def capture_pages(bsk, max_pages):
    """先向前翻到底，再退回第 1 页，把每一页的响应都收齐。"""
    bsk.ev(JS_RESET_CAP)
    pages = {}
    base = 0

    # 向前
    for _ in range(max_pages + 2):
        st = bsk.ev(JS_PAGER) or {}
        if not st.get("ok"):
            bsk.log("  ! 分页控件缺失")
            break
        if st.get("nextDis"):
            bsk.log("  已到最后一页（当前 %s）" % st.get("active"))
            break
        bsk.click(".ant-drawer-content .ant-pagination-next")
        got = None
        for _ in range(50):
            time.sleep(0.4)
            base, got = _cap_pages(bsk, base, pages)
            if got:
                break
        bsk.log("  捕获第 %s 页（翻至 P%s）" % (got, (bsk.ev(JS_PAGER) or {}).get("active")))
        if not got:
            bsk.log("  ! 翻页未产生新响应，停止前进")
            break
        time.sleep(1.0)

    # 向后补齐（第 1 页及其余回退页）
    for _ in range(max_pages + 2):
        st = bsk.ev(JS_PAGER) or {}
        if not st.get("ok") or st.get("prevDis"):
            break
        bsk.click(".ant-drawer-content .ant-pagination-prev")
        time.sleep(0.9)
        base, _ = _cap_pages(bsk, base, pages)
        time.sleep(0.5)

    return pages


# --------------------------------------------------------------------------------------
def parse_groups(args):
    if args.config:
        with open(args.config, encoding="utf-8") as f:
            cfgs = json.load(f)
        if isinstance(cfgs, dict):
            cfgs = cfgs.get("groups", [])
    else:
        cfgs = DEFAULT_GROUPS
    if args.groups:
        want = {x.strip().upper() for x in args.groups.split(",") if x.strip()}
        cfgs = [g for g in cfgs if str(g.get("key", "")).upper() in want]
    if not cfgs:
        raise SystemExit("没有匹配到任何类目组，检查 --groups / --config")
    return cfgs


def main():
    ap = argparse.ArgumentParser(description="得物商机推荐·高搜词全量抓取（接口拦截版）")
    ap.add_argument("--session", required=True, help="bsk 会话名")
    ap.add_argument("--out", required=True, help="输出目录（会在其下建 data/）")
    ap.add_argument("--groups", default="", help="要跑的组，如 A,B（默认全跑）")
    ap.add_argument("--group", default="", help="只跑一组（兼容写法）")
    ap.add_argument("--config", default="", help="自定义类目组 JSON")
    ap.add_argument("--max-pages", type=int, default=10, help="每组最多翻多少页（默认 10）")
    ap.add_argument("--no-clear", action="store_true", help="不清空已有筛选（续抓时用）")
    args = ap.parse_args()

    if args.group and not args.groups:
        args.groups = args.group

    groups = parse_groups(args)
    out_data = os.path.join(args.out, "data")
    os.makedirs(out_data, exist_ok=True)
    bsk = Bsk(args.session)

    bsk.log("== 检查页面 ==")
    if not ensure_drawer(bsk):
        raise SystemExit("抽屉打不开：确认浏览器停在 stark.dewu.com/main/businessApp/opportunity?tabId=suggestion")

    bsk.log("== 注入接口拦截器 ==")
    bsk.log("  %s" % bsk.ev(JS_HOOK))

    for grp in groups:
        key = str(grp.get("key") or grp.get("label"))
        bsk.log("\n== 组 %s：%s ==" % (key, grp.get("label")))
        if not args.no_clear:
            clear_filter(bsk)
        if not apply_group(bsk, grp):
            bsk.log("  ! 组 %s 筛选失败，跳过" % key)
            continue
        pages = capture_pages(bsk, args.max_pages)
        payload = {
            "group": key,
            "label": grp.get("label"),
            "mode": grp.get("mode"),
            "items": grp.get("items"),
            "capturedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
            "pageCount": len(pages),
            "pages": pages,
        }
        path = os.path.join(out_data, "cap_%s.json" % key)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        total = 0
        for pg in pages.values():
            try:
                total += len(json.loads(pg["resp"])["data"]["contents"])
            except Exception:
                pass
        bsk.log("  -> %s 页 / %d 条  %s" % (len(pages), total, path))

    bsk.log("\n完成。下一步：python to_csv.py --data-dir %s --out <周目录>" % out_data)


if __name__ == "__main__":
    main()
