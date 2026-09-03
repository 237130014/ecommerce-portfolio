"""
小红书搜索模块：关键词搜索 + 排序/时间筛选 + 接口响应拦截提取

数据来源：拦截 https://so.xiaohongshu.com/api/sns/web/v2/search/notes 的响应，
拿到结构化 JSON（标题/封面/点赞/收藏/评论/作者/时间），比 DOM 抓取更可靠。

用法：
    from login import ensure_login
    from search import search_keyword, load_keywords
    pw, context, page = ensure_login()
    items = search_keyword(page, "黄金项链", sort="最多点赞", publish_time="一周内", limit=30)
"""
import json
import random
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "xhs-baseline"

SEARCH_URL = "https://www.xiaohongshu.com/search_result?keyword={kw}&source=web_search_result_notes"
NOTES_API = "search/notes"

# 排序/时间选项在筛选面板里的展示文本
SORT_LABELS = ["综合", "最新", "最多点赞", "最多评论", "最多收藏"]
TIME_LABELS = ["不限", "一天内", "一周内", "半年内"]


def load_keywords(path: Path = None):
    """从 references/keywords.json 读取关键词清单，返回 list[str]。"""
    p = path or ROOT / "references" / "keywords.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("keywords", [])


def _sleep(lo=1.0, hi=2.5):
    time.sleep(random.uniform(lo, hi))


def parse_item(raw: dict) -> dict:
    """把 search/notes 响应里的单个 item 转成标准字段。"""
    nc = raw.get("note_card", {})
    interact = nc.get("interact_info", {})
    cover = nc.get("cover", {})
    user = nc.get("user", {})
    nid = raw.get("id", "")
    xsec = raw.get("xsec_token", "")

    publish_time = ""
    for tag in nc.get("corner_tag_info", []):
        if tag.get("type") == "publish_time":
            publish_time = tag.get("text", "")
            break

    url = ""
    if nid:
        url = f"https://www.xiaohongshu.com/explore/{nid}"
        if xsec:
            url += f"?xsec_token={xsec}&xsec_source=pc_search"

    return {
        "note_id": nid,
        "title": nc.get("display_title", ""),
        "desc": nc.get("display_title", ""),  # 列表页只有文案标题，完整正文需详情页补全
        "cover": cover.get("url_default") or cover.get("url_pre") or "",
        "url": url,
        "liked_count": interact.get("liked_count", ""),
        "collected_count": interact.get("collected_count", ""),
        "comment_count": interact.get("comment_count", ""),
        "shared_count": interact.get("shared_count", ""),
        "author": user.get("nickname", "") or user.get("nick_name", ""),
        "author_id": user.get("user_id", ""),
        "publish_time": publish_time,
        "type": nc.get("type", ""),
        "xsec_token": xsec,
    }


def _js_click_tag(page, option_text: str) -> bool:
    """用 JS 点击筛选面板中「可见」的选项 tag（排除 aria-hidden 隐藏热力层）。"""
    js = f"""
    (() => {{
        const spans = Array.from(document.querySelectorAll('div.filter-panel span'));
        for (const s of spans) {{
            if (s.innerText && s.innerText.trim() === {json.dumps(option_text)}) {{
                let el = s;
                while (el && !(el.classList && el.classList.contains('tags'))) {{
                    el = el.parentElement;
                }}
                if (el && el.getAttribute('aria-hidden') !== 'true') {{
                    el.click();
                    return true;
                }}
            }}
        }}
        return false;
    }})()
    """
    try:
        return bool(page.evaluate(js))
    except Exception:
        return False


def _click_filter_tag(page, option_text: str, retries: int = 4) -> bool:
    """hover「筛选」弹出面板后，点击指定选项 tag。"""
    for _ in range(retries):
        try:
            page.locator("text=筛选").first.hover()
            page.wait_for_timeout(2500)
            if _js_click_tag(page, option_text):
                page.wait_for_timeout(3000)
                return True
        except Exception:
            pass
        page.wait_for_timeout(1000)
    print(f"[search] 未能点击筛选选项「{option_text}」")
    return False


def search_keyword(page, keyword: str, sort: str = "最多点赞",
                   publish_time: str = "一周内", limit: int = 30,
                   max_scrolls: int = 40):
    """搜索单个关键词，返回 items 列表（按点赞数降序）。"""
    collected = {}
    state = {"collecting": False}

    def on_response(resp):
        if NOTES_API not in resp.url or not state["collecting"]:
            return
        try:
            data = resp.json()
            items = data.get("data", {}).get("items", [])
            for it in items:
                nid = it.get("id")
                if not nid or nid in collected:
                    continue
                # 过滤推广位/广告卡片等非标准笔记（id 含 #，或无标题/封面）
                if "#" in str(nid):
                    continue
                parsed = parse_item(it)
                if not parsed["title"] or not parsed["cover"]:
                    continue
                collected[nid] = parsed
        except Exception:
            pass

    page.on("response", on_response)

    try:
        url = SEARCH_URL.format(kw=quote(keyword))
        page.goto(url, wait_until="commit", timeout=40000)
        page.wait_for_timeout(5000)

        # 先点排序，再点时间（时间点击触发最终筛选请求，从这一步开始收集）
        _click_filter_tag(page, sort)
        state["collecting"] = True
        if publish_time not in ("不限", ""):
            _click_filter_tag(page, publish_time)
        page.wait_for_timeout(3000)

        # 滚动加载更多（触发 page 2/3/...）
        for _ in range(max_scrolls):
            if len(collected) >= limit:
                break
            page.mouse.wheel(0, 2200)
            _sleep(0.8, 1.5)

    finally:
        try:
            page.remove_listener("response", on_response)
        except Exception:
            pass

    items = list(collected.values())
    items.sort(key=lambda x: _to_int(x.get("liked_count")), reverse=True)
    result = items[:limit]
    print(f"[search] 关键词「{keyword}」抓取 {len(result)} 条")
    return result


def _to_int(s):
    try:
        return int(str(s).replace(",", "").replace("万", "0000").replace("+", ""))
    except Exception:
        return 0


def save_items(items, keyword: str, base: Path = DATA_DIR):
    """保存本轮抓取数据为 JSON。"""
    base.mkdir(parents=True, exist_ok=True)
    safe_kw = keyword.replace("/", "_").replace("\\", "_")
    data = {
        "keyword": keyword,
        "sort": "最多点赞",
        "publish_time": "一周内",
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(items),
        "items": items,
    }
    out = base / f"notes_{safe_kw}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[search] 已保存 {out}")
    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from login import ensure_login

    keywords = sys.argv[1:] or load_keywords() or ["黄金项链"]
    pw, context, page = ensure_login()
    for kw in keywords:
        try:
            items = search_keyword(page, kw)
            save_items(items, kw, DATA_DIR)
        except Exception as e:
            print(f"[search] 关键词「{kw}」失败：{e}")
    context.close()
    pw.stop()
