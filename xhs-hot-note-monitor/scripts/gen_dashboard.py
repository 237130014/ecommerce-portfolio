"""
看板生成模块：读取指定目录下的 notes_*.json，合并为汇总 CSV + 瀑布流 HTML 看板。

用法：
    python scripts/gen_dashboard.py [数据目录]
"""
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "xhs-baseline"


def parse_count(s) -> int:
    """把「1.2万」「1234」「3.5千」解析成整数。"""
    if not s:
        return 0
    s = str(s).strip().replace("+", "").replace(",", "")
    try:
        if "万" in s:
            return int(float(s.replace("万", "")) * 10000)
        if "千" in s:
            return int(float(s.replace("千", "")) * 1000)
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def load_all(base: Path):
    """读取指定目录下所有 notes_*.json，合并 items，按点赞降序排序。返回 (items, keywords)。"""
    items = []
    keywords = []
    for jf in sorted(base.glob("notes_*.json")):
        data = json.loads(jf.read_text(encoding="utf-8"))
        keywords.append(data.get("keyword", ""))
        for it in data.get("items", []):
            it["keyword"] = data.get("keyword", "")
            items.append(it)
    # 按点赞数降序
    items.sort(key=lambda x: parse_count(x.get("liked_count", 0)), reverse=True)
    for i, it in enumerate(items, 1):
        it["rank"] = i
    return items, keywords


def write_csv(items, base: Path):
    """生成汇总 CSV。"""
    out = base / "热门笔记明细.csv"
    cols = ["rank", "keyword", "title", "desc", "liked_count", "collected_count",
            "comment_count", "author", "publish_time", "cover", "local_image", "url"]
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for it in items:
            row = {c: it.get(c, "") for c in cols}
            w.writerow(row)
    print(f"[dash] CSV 已生成：{out}")
    return out


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>小红书热门笔记看板</title>
<style>
  :root { --red: #ff2442; --red-dark: #d81e39; --bg: #f7f7f8; --card: #ffffff;
          --text: #1f1f1f; --muted: #8a8a8a; --border: #ececec; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         color: var(--text); padding: 24px 28px; }
  header { max-width: 1280px; margin: 0 auto 20px; }
  h1 { font-size: 22px; font-weight: 600; display: flex; align-items: center; gap: 10px; }
  h1 .logo { width: 28px; height: 28px; border-radius: 8px; background: var(--red); color: #fff;
             display: inline-flex; align-items: center; justify-content: center; font-size: 16px; }
  .stats { display: flex; gap: 18px; margin-top: 14px; flex-wrap: wrap; }
  .stat { background: var(--card); border: 1px solid var(--border); border-radius: 12px;
          padding: 12px 20px; min-width: 130px; }
  .stat .num { font-size: 22px; font-weight: 700; color: var(--red); }
  .stat .lbl { font-size: 12px; color: var(--muted); margin-top: 2px; }
  .toolbar { max-width: 1280px; margin: 0 auto 18px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
  .chips { display: flex; gap: 8px; flex-wrap: wrap; }
  .chip { padding: 6px 14px; border-radius: 18px; border: 1px solid var(--border); background: var(--card);
          cursor: pointer; font-size: 13px; transition: all .15s; }
  .chip:hover { border-color: var(--red); color: var(--red); }
  .chip.active { background: var(--red); color: #fff; border-color: var(--red); }
  .search { flex: 1; min-width: 200px; padding: 8px 14px; border: 1px solid var(--border);
            border-radius: 18px; font-size: 13px; outline: none; }
  .search:focus { border-color: var(--red); }
  .btn { padding: 8px 16px; border-radius: 18px; border: none; background: var(--red); color: #fff;
         font-size: 13px; cursor: pointer; text-decoration: none; }
  .btn:hover { background: var(--red-dark); }
  .grid { max-width: 1280px; margin: 0 auto; columns: 300px auto; column-gap: 16px; }
  .card { break-inside: avoid; background: var(--card); border: 1px solid var(--border); border-radius: 12px;
          margin-bottom: 16px; overflow: hidden; cursor: pointer; transition: transform .15s, box-shadow .15s; }
  .card:hover { transform: translateY(-3px); box-shadow: 0 8px 24px rgba(0,0,0,.08); }
  .card .img { width: 100%; display: block; background: #f0f0f0; }
  .card .body { padding: 12px 14px; }
  .card .title { font-size: 14px; font-weight: 600; line-height: 1.45; display: -webkit-box;
                 -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .card .meta { display: flex; align-items: center; gap: 12px; margin-top: 10px; font-size: 12px; color: var(--muted); }
  .card .author { display: flex; align-items: center; gap: 6px; min-width: 0; flex: 1; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .card .avatar { width: 20px; height: 20px; border-radius: 50%; background: #ffd9de; color: var(--red);
                  display: inline-flex; align-items: center; justify-content: center; font-size: 11px; flex-shrink: 0; }
  .card .likes { color: var(--red); font-weight: 600; flex-shrink: 0; }
  .rank-badge { position: absolute; top: 10px; left: 10px; background: rgba(0,0,0,.55); color: #fff;
                font-size: 12px; font-weight: 600; padding: 3px 9px; border-radius: 8px; }
  .img-wrap { position: relative; }
  .empty { max-width: 1280px; margin: 60px auto; text-align: center; color: var(--muted); }
  .lightbox { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.75); z-index: 99;
              align-items: center; justify-content: center; padding: 40px; }
  .lightbox.open { display: flex; }
  .lb-card { background: #fff; border-radius: 16px; max-width: 680px; width: 100%; max-height: 90vh;
             overflow: auto; }
  .lb-card img { width: 100%; display: block; }
  .lb-body { padding: 18px 22px; }
  .lb-title { font-size: 17px; font-weight: 600; margin-bottom: 10px; }
  .lb-desc { font-size: 14px; color: #444; line-height: 1.7; margin-bottom: 14px; white-space: pre-wrap; }
  .lb-meta { display: flex; gap: 16px; font-size: 13px; color: var(--muted); margin-bottom: 14px; flex-wrap: wrap; }
  .lb-link { display: inline-block; padding: 8px 18px; background: var(--red); color: #fff;
             border-radius: 18px; font-size: 13px; text-decoration: none; }
  .lb-close { position: absolute; top: 20px; right: 28px; color: #fff; font-size: 34px; cursor: pointer; }
</style>
</head>
<body>
<header>
  <h1><span class="logo">红</span>小红书热门笔记看板</h1>
  <div class="stats">
    <div class="stat"><div class="num" id="statTotal">0</div><div class="lbl">笔记总数</div></div>
    <div class="stat"><div class="num" id="statKw">0</div><div class="lbl">关键词数</div></div>
    <div class="stat"><div class="num" id="statTop">0</div><div class="lbl">最高点赞</div></div>
    <div class="stat"><div class="num" style="font-size:15px;color:var(--text)" id="statDate">-</div><div class="lbl">更新时间</div></div>
  </div>
</header>
<div class="toolbar">
  <div class="chips" id="chips"></div>
  <input class="search" id="searchBox" placeholder="搜索标题 / 作者...">
  <a class="btn" id="dlBtn" href="热门笔记明细.csv" download>下载 CSV</a>
</div>
<div class="grid" id="grid"></div>
<div class="empty" id="empty" style="display:none">没有匹配的笔记</div>

<div class="lightbox" id="lightbox">
  <div class="lb-close" id="lbClose">&times;</div>
  <div class="lb-card">
    <img id="lbImg" src="" alt="">
    <div class="lb-body">
      <div class="lb-title" id="lbTitle"></div>
      <div class="lb-meta" id="lbMeta"></div>
      <div class="lb-desc" id="lbDesc"></div>
      <a class="lb-link" id="lbLink" href="#" target="_blank">打开原文</a>
    </div>
  </div>
</div>

<script>
const DATA = __DATA__;
let curKw = "全部";
let curText = "";

function fmt(n){ return n>=10000 ? (n/10000).toFixed(1)+"万" : n; }

function renderChips(){
  const kws = ["全部", ...new Set(DATA.map(d=>d.keyword).filter(Boolean))];
  document.getElementById("chips").innerHTML = kws.map(k =>
    `<span class="chip ${k===curKw?'active':''}" data-kw="${k}">${k}</span>`).join("");
  document.querySelectorAll(".chip").forEach(c =>
    c.onclick = () => { curKw = c.dataset.kw; renderChips(); render(); });
}

function render(){
  const kwFilter = curKw === "全部" ? null : curKw;
  let list = DATA.filter(d =>
    (!kwFilter || d.keyword === kwFilter) &&
    (!curText || (d.title||"").includes(curText) || (d.author||"").includes(curText)));
  const g = document.getElementById("grid");
  if(!list.length){ g.innerHTML=""; document.getElementById("empty").style.display="block"; return; }
  document.getElementById("empty").style.display="none";
  g.innerHTML = list.map(d => `
    <div class="card" data-idx="${DATA.indexOf(d)}">
      <div class="img-wrap">
        ${d.rank<=3 ? `<span class="rank-badge">TOP ${d.rank}</span>` : ""}
        <img class="img" src="${d.local_image || d.cover}" loading="lazy" onerror="this.style.display='none'">
      </div>
      <div class="body">
        <div class="title">${(d.title||"无标题").replace(/</g,"&lt;")}</div>
        <div class="meta">
          <span class="author"><span class="avatar">${(d.author||"?").charAt(0)}</span>${d.author||"未知作者"}</span>
          <span class="likes">${fmt(d.likes||0)} 赞</span>
        </div>
      </div>
    </div>`).join("");
  document.querySelectorAll(".card").forEach(c => c.onclick = () => openLightbox(+c.dataset.idx));
  document.getElementById("statTotal").textContent = list.length;
  document.getElementById("statTop").textContent = list.length ? fmt(Math.max(...list.map(d=>d.likes||0))) : 0;
}

function openLightbox(idx){
  const d = DATA[idx];
  document.getElementById("lbImg").src = d.local_image || d.cover;
  document.getElementById("lbTitle").textContent = d.title || "无标题";
  document.getElementById("lbDesc").textContent = d.desc || "（无正文摘要）";
  document.getElementById("lbMeta").innerHTML =
    `<span>作者：${d.author||"-"}</span><span>点赞：${fmt(d.likes||0)}</span>`+
    `<span>收藏：${fmt(d.collected||0)}</span><span>评论：${fmt(d.comment||0)}</span>`+
    `<span>${d.publish_time||""}</span>`;
  document.getElementById("lbLink").href = d.url || "#";
  document.getElementById("lightbox").classList.add("open");
}
document.getElementById("lbClose").onclick = () => document.getElementById("lightbox").classList.remove("open");
document.getElementById("lightbox").onclick = e => { if(e.target.id==="lightbox") e.target.classList.remove("open"); };
document.getElementById("searchBox").oninput = e => { curText = e.target.value.trim(); render(); };

DATA.forEach(d => { d.likes = parseInt(d.liked_count)||0; d.collected = parseInt(d.collected_count)||0; d.comment = parseInt(d.comment_count)||0; });
document.getElementById("statKw").textContent = new Set(DATA.map(d=>d.keyword)).size;
document.getElementById("statDate").textContent = "__DATE__";
renderChips();
render();
</script>
</body>
</html>
"""


def gen_dashboard(base: Path):
    items, keywords = load_all(base)
    if not items:
        print("[dash] 没有数据，请先运行 search.py")
        return

    # CSV
    write_csv(items, base)

    # HTML 看板（文件名带时间，避免同一目录内重名）
    now = datetime.now()
    out = base / f"小红书热门笔记-{now.strftime('%Y-%m-%d_%H%M')}.html"
    # 只注入看板需要的字段
    slim = [{
        "keyword": it.get("keyword", ""),
        "rank": it.get("rank", 0),
        "title": it.get("title", ""),
        "desc": it.get("desc", ""),
        "cover": it.get("cover", ""),
        "local_image": it.get("local_image", ""),
        "url": it.get("url", ""),
        "liked_count": str(it.get("liked_count", "")),
        "collected_count": str(it.get("collected_count", "")),
        "comment_count": str(it.get("comment_count", "")),
        "author": it.get("author", ""),
        "publish_time": it.get("publish_time", ""),
    } for it in items]
    html = (HTML_TEMPLATE
            .replace("__DATA__", json.dumps(slim, ensure_ascii=False))
            .replace("__DATE__", now.strftime("%Y-%m-%d %H:%M")))
    out.write_text(html, encoding="utf-8")
    print(f"[dash] 看板已生成：{out}")
    return out


if __name__ == "__main__":
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_DIR
    gen_dashboard(base)
