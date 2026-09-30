# -*- coding: utf-8 -*-
"""京东 SKU 主图批量抓取（bsk 驱动，复用真实浏览器登录态）

为什么用 bsk
------------
实测（2026-09-29）：Playwright 新开浏览器无论怎么反检测，扫码登录后访问
item.jd.com 仍被频控（pc-frequent-pro.pf.jd.com reason=403）。原因是"身份"不对：
陌生设备指纹 + 新账号 + 机房特征。
bsk 驱动用户日常在用的真实 Chrome（真实指纹 + 已登录账号 + 本地 IP），
把「设备/身份」这层风控直接抹平。

探针实测到的可靠选择器（2026-09-29）
------------------------------------
    第一主图  .image-carousel-track .item:first-child img.image
    标题      document.title  去掉尾部「【行情 报价 价格 评测】-京东」
    价格      .product-price
    店铺      .top-name-tag
    原图      把 URL 里的 /s<W>x<H>_ 前缀去掉即得原图

前置条件
--------
1. bsk daemon 常驻：start-bsk-daemon.bat（端口 53899，避开 VPN 占用的 52800）
2. 浏览器已登录京东（手动登录一次即可，登录态长期有效）
   `bsk.exe doctor` 显示 daemon running + extension connected 均为 ok

用法
----
    python fetch_main_images.py <BASE> [选项]

常用选项
--------
    --from-xlsx PATH   直接从京东榜单导出表读取 SKU（E 列 SKU ID）
    --skus 1,2,3       只抓指定序号
    --limit 50         本批最多抓多少个（默认 50）
    --force            已抓过的也重抓（默认跳过，便于断点续传）
    --delay 3-8        每个 SKU 之间随机延迟秒数（默认 3-8，防风控）
    --max-fail 3       连续失败多少次就熔断停止（默认 3）

产物
----
    images/{sku}.{ext}   主图原图
    report.csv           抓取报告（sku/状态/标题/价格/店铺/图片/URL/时间）
    state.json           断点续传状态（已完成的 sku 集合）
    logs/fetch_*.log     运行日志
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------

BSK_PORT = os.environ.get("BSK_PORT", "53899")
BSK_BIN = os.environ.get("BSK_BIN", "")

# 风控 / 异常页特征
RISK_MARKERS = [
    "pc-frequent-pro.pf.jd.com",
    "risk_handler",
    "passport.jd.com",
    "cfe.m.jd.com/privatedomain",
]
RISK_TEXT_MARKERS = ["访问过于频繁", "安全验证", "页面异常", "请稍后再试"]


def norm_path(p: str) -> str:
    """兼容 Git Bash 风格 /c/... → C:/...（Windows Python 不认前者）。"""
    if p and re.match(r"^/[a-zA-Z]/", p):
        return p[1].upper() + ":" + p[2:]
    return p


def default_base() -> Path:
    """默认数据目录（BASE）。

    两种目录布局都支持：
      · 源码布局：脚本平铺在工具目录下      → BASE = 脚本所在目录
      · 技能包布局：脚本在 <包>/scripts/ 下  → BASE = 包根目录

    技能包（~/.workbuddy/skills/jd-sku-image-fetch/）就是第二种，
    若还按脚本目录当 BASE，数据会落进 scripts/ 里，与 run.bat 不一致。
    """
    here = Path(__file__).resolve().parent
    return here.parent if here.name == "scripts" else here


def log(msg: str, logfile=None):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if logfile:
        with open(logfile, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def find_bsk() -> str:
    """定位 bsk 可执行文件。"""
    cands = [
        BSK_BIN,
        os.environ.get("BSK_BIN", ""),
        shutil.which("bsk") or "",
        os.path.join(os.path.expanduser("~"), ".local", "bin", "bsk.exe"),
        os.path.join(os.path.expanduser("~"), ".local", "bin", "bsk"),
    ]
    for c in cands:
        if c and os.path.isfile(norm_path(c)):
            return norm_path(c)
    return "bsk"


BSK = find_bsk()
# 关键：脚本环境里禁用 bsk 自动拉起 daemon，否则 status 会卡住
BSK_ENV = dict(os.environ, BSK_AUTO_START="0")


def bsk_run(args: list[str], timeout: int = 120) -> str:
    """调用 bsk CLI，返回 stdout。"""
    cmd = [BSK] + args
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, env=BSK_ENV,
        )
        return (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return f"__TIMEOUT__ {' '.join(args)}"
    except Exception as e:
        return f"__ERROR__ {e!r}"


def bsk_json(args: list[str], timeout: int = 120):
    """调用 bsk CLI 并解析 JSON（--json 输出）。"""
    out = bsk_run(args, timeout=timeout)
    # bsk 偶尔会先打印升级提示行，需要剥离后再找 JSON
    idx = out.find("{")
    if idx < 0:
        return None, out
    try:
        return json.loads(out[idx:]), out
    except Exception:
        # 尝试匹配最后一个完整 JSON 对象
        try:
            m = re.search(r"\{[\s\S]*\}\s*$", out)
            if m:
                return json.loads(m.group(0)), out
        except Exception:
            pass
        return None, out


# --------------------------------------------------------------------------
# bsk 会话管理
# --------------------------------------------------------------------------

def check_daemon(logfile=None) -> bool:
    out = bsk_run(["status"], timeout=30)
    ok = "daemon version" in out or "browsers connected" in out
    if not ok:
        log("[错误] bsk daemon 未运行。请先双击 start-bsk-daemon.bat，保持窗口不关。", logfile)
        log(f"       bsk status 输出：{out.strip()[:300]}", logfile)
    else:
        m = re.search(r"WS port\s+(\d+)", out)
        if m:
            log(f"[信息] bsk daemon 正常，端口 {m.group(1)}", logfile)
        m2 = re.search(r"browsers connected\s+(\d+)", out)
        if m2 and int(m2.group(1)) == 0:
            log("[错误] 没有浏览器连接。请确认 Chrome 已装 BrowserSkill 扩展并已连接。", logfile)
            return False
    return ok


def session_start(logfile=None) -> str | None:
    data, raw = bsk_json(["session", "start", "--json"], timeout=90)
    if data and data.get("session_id"):
        sid = data["session_id"]
        log(f"[信息] 会话已开启：{sid}（浏览器 {data.get('browser_instance_id')}）", logfile)
        return sid
    log(f"[错误] 开会话失败：{raw.strip()[:300]}", logfile)
    return None


def session_stop(sid: str):
    if sid:
        bsk_run(["session", "stop", sid], timeout=30)


# --------------------------------------------------------------------------
# 页面操作
# --------------------------------------------------------------------------

def navigate(sid: str, url: str, timeout: int = 90) -> str:
    out = bsk_run(
        ["navigate", url, "--session", sid, "--wait-until", "load", "--timeout", "60s"],
        timeout=timeout,
    )
    return out


def is_risk_page(url: str, text: str = "") -> str | None:
    """判断是否命中风控页，返回命中的标记。"""
    for m in RISK_MARKERS:
        if m in url:
            return m
    for m in RISK_TEXT_MARKERS:
        if m in text:
            return m
    return None


# 提取脚本：滚动唤醒懒加载 → 轮询主图就绪 → 一次性取全部字段
EXTRACT_JS = r"""
(async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));

  // 1. 轻滚动唤醒懒加载（不要滚太远，主图在首屏）
  window.scrollTo(0, 600);
  await sleep(900);
  window.scrollTo(0, 0);
  await sleep(700);

  // 2. 等待主图容器就绪（最多 ~12s）
  let firstImg = null;
  for (let i = 0; i < 24; i++) {
    const img = document.querySelector('.image-carousel-track .item:first-child img.image')
             || document.querySelector('.image-carousel-track img.image');
    const src = img && img.getAttribute('src');
    if (src && !/^data:/.test(src)) { firstImg = src; break; }
    await sleep(500);
  }

  // 3. 收集字段
  //    注意：店铺名常形如「知芝好物严选小店\n3.0」（店名+评分），
  //    换行会污染 CSV/Excel（字段内裸换行导致 Excel 行错位），必须压成单行。
  const flat = (s) => (s || '').replace(/[\r\n\t\u00a0\u2007\u202f]+/g, ' ').replace(/\s{2,}/g, ' ').trim();
  const title = flat((document.title || '').replace(/【行情[\s\S]*?】-京东$/, '')
                                      .replace(/-京东$/, ''));
  const price = flat(document.querySelector('.product-price')?.innerText);
  const shop  = flat(document.querySelector('.top-name-tag')?.innerText);

  // ---- v2.0 新增字段 ----
  // 累计评价数：优先取价格面板的「累计评价 2万+」
  //   —— 首屏即可见、结构稳定（2026-09-30 实测 4 款商品全部命中）；
  //   兜底取详情页评价区的「买家评价(2万+)」（在页面下方，懒加载时可能取不到）。
  //   输出只留数值部分，如 "2万+"。
  const ccEl = document.querySelector('.product-price-panel--options-comment')
            || document.querySelector('#comment-title');
  const comment = flat(ccEl ? ccEl.innerText : '')
      .replace(/^累计评价\s*/, '')
      .replace(/^买家评价\s*[（(]/, '')
      .replace(/[)）]\s*$/, '')
      .trim();

  // 营销活动：右侧「已享受 / 可再享」区域。
  //   实测形如「已享受：单品立减60元 可再享：最高返26京豆」，
  //   即商品价格下方那块活动说明（含单品立减 / 国补 / 返京豆等）。
  const promo = flat(document.querySelector('.page-right-discount')?.innerText);

  // 4. 主图原图：去掉 /s<W>x<H>_ 尺寸前缀
  const big = firstImg ? firstImg.replace(/\/s\d+x\d+_/, '/') : '';

  return {
    url: location.href,
    title: title,
    price: price,
    comment: comment,
    promo: promo,
    shop: shop,
    firstImg: firstImg || '',
    firstBig: big,
    imgCount: document.querySelectorAll('.image-carousel-track .item').length,
    bodyLen: (document.body?.innerText || '').length,
    bodySnip: (document.body?.innerText || '').slice(0, 200)
  };
})()
"""


def extract(sid: str, sku: str, logfile=None):
    """在已完成 navigate 的页面上提取字段。返回 dict 或 None。"""
    data, raw = bsk_json(
        ["evaluate", "--session", sid, EXTRACT_JS, "--json", "--timeout", "60s"],
        timeout=120,
    )
    if not data or not data.get("ok"):
        return None, raw
    return data.get("value") or {}, raw


def download(url: str, out_path: Path) -> bool:
    """下载图片（走 CDN，无需登录态）。优先 curl，失败用 urllib。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("curl"):
        r = subprocess.run(
            ["curl", "-sL", "-o", str(out_path), "-w", "%{http_code}", url],
            capture_output=True, text=True, timeout=90,
        )
        if r.stdout.strip() == "200" and out_path.exists() and out_path.stat().st_size > 1024:
            return True
    try:
        import urllib.request

        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Referer": "https://item.jd.com/",
        })
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        if len(data) > 1024:
            out_path.write_bytes(data)
            return True
    except Exception:
        pass
    return False


def ext_from_url(url: str) -> str:
    """从 URL 推断扩展名（京东主图可能是 .jpg/.png + .avif 后缀）。"""
    base = url.split("?")[0]
    m = re.search(r"\.(jpg|jpeg|png|webp|avif|gif)", base, re.I)
    if not m:
        return ".jpg"
    e = m.group(1).lower()
    if e == "jpeg":
        e = "jpg"
    # .png.avif / .jpg.avif → 保留主格式，便于查看
    if base.lower().endswith(".avif"):
        return "." + e if e != "avif" else ".avif"
    return "." + e


# --------------------------------------------------------------------------
# SKU 读取（兼容京东导出 xlsx 的 dimension 写坏问题）
# --------------------------------------------------------------------------

def read_skus_from_xlsx(path: str) -> list[str]:
    """从京东榜单导出 xlsx 读取 SKU 列。

    注意：京东导出的 xlsx 常把 <dimension ref="A1"/> 写坏（只声明 A1），
    openpyxl 会因此只读到 A 列。故直接解析 sheet1.xml 原始 XML，
    不依赖 dimension 声明（导出用的是 t="inlineStr"，也不需要 sharedStrings）。
    """
    import zipfile
    from xml.etree import ElementTree as ET

    NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)]
        names.sort()
        root = ET.fromstring(z.read(names[0]))

    def col_idx(letters: str) -> int:
        n = 0
        for ch in letters:
            n = n * 26 + (ord(ch) - ord("A") + 1)
        return n - 1

    def cell_text(c) -> str:
        if c.get("t") == "inlineStr":
            is_el = c.find(f"{NS}is")
            if is_el is None:
                return ""
            return "".join(it.text or "" for it in is_el.iter(f"{NS}t"))
        v = c.find(f"{NS}v")
        return (v.text or "") if v is not None else ""

    rows = []
    for row in root.iter(f"{NS}row"):
        cells = {}
        for c in row.findall(f"{NS}c"):
            m = re.match(r"^([A-Z]+)\d+$", c.get("r") or "")
            if m:
                cells[col_idx(m.group(1))] = cell_text(c)
        rows.append([cells.get(i, "") for i in range((max(cells) + 1) if cells else 0)])
    if not rows:
        return []

    # 定位 SKU 列：优先表头含 SKU，否则找"几乎全是长数字"的列
    header = rows[0]
    sku_idx = None
    for j, h in enumerate(header):
        if isinstance(h, str) and "SKU" in h.upper():
            sku_idx = j
            break
    if sku_idx is None:
        ncols = max((len(r) for r in rows[1:]), default=0)
        best, best_hit = None, 0
        for j in range(ncols):
            hit = sum(
                1 for r in rows[1:]
                if j < len(r) and re.fullmatch(r"\d{6,}", str(r[j]).strip().split(".")[0])
            )
            if hit > best_hit:
                best, best_hit = j, hit
        sku_idx = best

    out, seen = [], set()
    if sku_idx is None:
        return []
    for r in rows[1:]:
        if sku_idx >= len(r):
            continue
        s = str(r[sku_idx]).strip().split(".")[0].replace(",", "")
        if re.fullmatch(r"\d{6,}", s) and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def read_skus_from_csv(path: str) -> list[str]:
    """从 skus.csv 读取（支持 sku 列 + enabled 开关）。"""
    out, seen = [], set()
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            en = str(row.get("enabled", "1")).strip().lower()
            if en in ("0", "false", "no", "n", ""):
                continue
            s = str(row.get("sku", "")).strip().split(".")[0]
            if s.isdigit() and len(s) >= 6 and s not in seen:
                seen.add(s)
                out.append(s)
    return out


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------

def load_state(state_file: Path) -> dict:
    if state_file.exists():
        try:
            return json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"done": {}, "failed": {}}


def save_state(state_file: Path, state: dict):
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def build_state(done: dict, failed: dict | None = None,
                skus_all: list | None = None, source: str | None = None) -> dict:
    """组装 state.json。

    除 done/failed 外，额外记录**本批次的 SKU 全集**与来源。
    原因：一个批次可能是拖 xlsx 跑的，它的清单跟 BASE/skus.csv 完全是两份，
    fetch_stats.py 若拿 skus.csv 去对账就会算出"已完成 0"这种假象。
    老批次没有 skus_all 字段，统计端会自动退回旧逻辑。
    """
    st = {"done": done, "failed": failed or {}}
    if skus_all:
        st["skus_all"] = list(skus_all)
    if source:
        st["source"] = source
    return st


def _flat(v) -> str:
    """把字段里的换行/制表/不间断空格压成单空格。

    Excel 打开 CSV 时，字段内的裸换行会让行错位（视觉上 H 列对不上号）。
    Python 的 csv 模块能正确解析带引号的多行字段，但 Excel 处理不一致，
    所以从源头就把所有字段拍平。
    """
    if v is None:
        return ""
    s = str(v).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    s = s.replace("\u00a0", " ").replace("\u2007", " ").replace("\u202f", " ")
    while "  " in s:
        s = s.replace("  ", " ")
    return s.strip()


# 京东风控/登录页地址，绝不能出现在 image_url / page_url 字段里
_RISK_URL_MARKERS = ("pf.jd.com", "reason=403", "risk_handler", "passport.jd.com")


def _is_risk_url(u: str) -> bool:
    return any(m in (u or "") for m in _RISK_URL_MARKERS)


def _write_csv(path: Path, rows: list[dict]):
    # v2.0：在 price 之后插入 comment_count（累计评价数）与 promo（营销活动）
    fields = ["sku", "status", "title", "price", "comment_count", "promo",
              "shop", "img_count", "image_file", "image_url", "page_url",
              "note", "ts"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            out = {k: _flat(v) for k, v in r.items()}
            # 兜底清洗：历史上曾把风控页地址当图片 URL 写进报告
            for k in ("image_url", "page_url"):
                if _is_risk_url(out.get(k, "")):
                    out[k] = ""
            w.writerow(out)


def load_prev_report(report_file: Path) -> list[dict]:
    """读取现有 report.csv 的历史行（用于合并，避免批次覆盖）。"""
    if not report_file.exists():
        return []
    try:
        raw = report_file.read_text(encoding="utf-8-sig")
        return list(csv.DictReader(io.StringIO(raw)))
    except Exception:
        return []


def merge_with_history(report_file: Path, batch_rows: list[dict]) -> list[dict]:
    """把本批抓取结果合并进历史报告。

    规则（重要）：
    - 本批「成功」的行覆盖同 SKU 的历史行（--force 重抓时更新数据）
    - 本批「失败/风控」的行 *不覆盖* 历史成功记录 ——
      否则一次风控就会把之前抓好的标题/图片/URL 抹掉（历史踩坑）
    - 历史里没有的新 SKU 直接追加

    这样 report.csv 始终是「累计全量」，且只增不减。
    """
    batch = {r["sku"]: r for r in batch_rows if r.get("sku")}
    OK_STATES = {"ok"}
    out: list[dict] = []
    seen: set[str] = set()

    for old in load_prev_report(report_file):
        sku = (old.get("sku") or "").strip()
        if not sku:
            continue
        seen.add(sku)
        new = batch.get(sku)
        if new is None:
            out.append(old)
            continue
        # 历史是成功记录，本批却失败了 → 保留历史，不降级
        if (old.get("status") in OK_STATES) and (new.get("status") not in OK_STATES):
            out.append(old)
        else:
            # 逐字段合并：新值非空才覆盖，避免把好数据填成空
            merged = dict(old)
            for k, v in new.items():
                if k == "_score":
                    continue
                if str(v or "").strip():
                    merged[k] = v
            out.append(merged)

    for sku, r in batch.items():
        if sku not in seen:
            out.append(r)
    return out


def write_report(report_file: Path, rows: list[dict], logfile: Path = None):
    """写报告。被 Excel 占用时自动换文件名，绝不让抓取因此崩掉。

    注意：传入的 rows 只包含「本次批次」的记录，调用方需先用
    merge_with_history() 合并历史，否则会覆盖掉之前批次的结果。
    """
    if not rows:
        return None
    try:
        _write_csv(report_file, rows)
        return report_file
    except PermissionError:
        pass
    except OSError:
        pass

    # 目标文件被占用（最常见：Excel 开着 report.csv）→ 退避到同名副本
    for i in range(2, 21):
        alt = report_file.with_name(f"{report_file.stem}_{i}{report_file.suffix}")
        try:
            _write_csv(alt, rows)
            log(f"[警告] {report_file.name} 被占用（大概率是 Excel 开着），"
                f"本次报告已改写到 {alt.name}", logfile)
            return alt
        except (PermissionError, OSError):
            continue

    log(f"[警告] {report_file.name} 及 20 个备用文件名均写入失败，"
        f"报告未落盘（数据仍在 state.json 里，可重抓或手动导出）", logfile)
    return None


# --------------------------------------------------------------------------
# 批次目录命名：runs/<榜单名>_<YYYYMMDD>/
# --------------------------------------------------------------------------

# 京东榜单导出文件名里的噪音词，提取榜单名时剔除。
# 注意：只剔"纯格式噪音"，保留能区分不同榜单的词（热销排名/新品/商品明细…），
# 否则同一天下载两个不同榜单会撞进同一个目录。
_LIST_NOISE = {
    "离线", "汇总下载", "汇总", "下载", "导出", "数据", "报表",
    "不包括对比时间", "跨天不去重", "唯一",
}


def derive_list_name(xlsx_path: str | None, csv_path: Path | None = None) -> str:
    """从榜单文件名推断「榜单名」（含榜单类型，用于区分不同榜单）。

    京东导出的文件名形如：
        某店_商品榜单_热销排名_离线_汇总下载_2026-09-27_2026-09-27.xlsx
        → 某店_商品榜单_热销排名

    规则：去掉扩展名 → 去掉所有日期片段 → 去掉纯格式噪音词 →
    去重保序 → 用 _ 连接。全空则返回 "榜单"。
    """
    src = None
    if xlsx_path:
        src = Path(norm_path(xlsx_path)).stem
    elif csv_path:
        src = csv_path.stem

    if not src:
        return "榜单"

    # 去掉尾部京东加的随机后缀（如 _HFeLTzbA、_1022）
    s = re.sub(r"_[A-Za-z0-9]{6,12}$", " ", src)
    # 去掉所有日期/月份区间片段：
    #   2026-09-27 / 20260927 / 2026_09_27 / 202607-202609 / 202607
    s = re.sub(r"\d{4}[-_]?\d{2}([-_]?\d{2})?", " ", s)           # 完整日期
    s = re.sub(r"(?<!\d)\d{4}(?![-\d])", " ", s)                  # 独立四位年份
    s = re.sub(r"[_\-~]?\b\d{4}\b", " ", s)                       # 残留四位数字段
    # 去掉 Excel 临时文件前缀
    s = s.lstrip("~$")
    s = re.sub(r"[_\-~\s]+$", "", s)                              # 收尾多余分隔符

    parts = [p for p in re.split(r"[_\-\s]+", s) if p]
    keep = [p for p in parts if p not in _LIST_NOISE]

    if not keep:
        return "榜单"
    # 去重保序
    seen, uniq = set(), []
    for p in keep:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return "_".join(uniq)[:48]


def sanitize_run_name(name: str) -> str:
    """把批次名清洗成安全的目录名（去掉 Windows 非法字符）。"""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (name or "").strip())
    s = re.sub(r"_+", "_", s).strip("_ .")
    return s[:60] or "批次"


def make_run_dir(base: Path, list_name: str, date_str: str,
                 run_name: str | None = None) -> Path:
    """生成/复用批次目录 runs/<榜单名>_<日期>/。

    同名目录已存在时直接复用（同一批次分批续抓）；
    run_name 显式指定时优先用它。
    """
    stem = sanitize_run_name(run_name) if run_name else sanitize_run_name(f"{list_name}_{date_str}")
    return base / "runs" / stem


def resolve_run_dir(base: Path, run: str | None = None,
                    need_data: bool = False) -> Path | None:
    """定位批次目录，供导出/统计/修复等脚本共用。

    - run 为空       → 取 runs/ 下**最新**的一个批次目录（没有 runs/ 则退回 BASE）
    - run 是目录名   → runs/<run>
    - run 是绝对路径 → 直接用
    - 找不到时：need_data=True 返回 None，否则返回 BASE

    need_data=True 时要求目录里至少有 report.csv 或 state.json。
    """
    if run:
        p = Path(norm_path(run))
        if not p.is_absolute():
            p = base / "runs" / p
        return p if p.exists() or not need_data else (p if p.exists() else None)

    runs_root = base / "runs"
    if runs_root.is_dir():
        cands = [d for d in runs_root.iterdir() if d.is_dir()]
        if need_data:
            cands = [d for d in cands
                     if (d / "report.csv").exists() or (d / "state.json").exists()]
        if cands:
            # 按修改时间取最新
            return max(cands, key=lambda d: d.stat().st_mtime)

    if need_data:
        return base if ((base / "report.csv").exists() or (base / "state.json").exists()) else None
    return base


def main():
    ap = argparse.ArgumentParser(description="京东 SKU 主图批量抓取（bsk 驱动）")
    ap.add_argument("base", nargs="?", default=".", help="BASE 数据目录")
    ap.add_argument("--from-xlsx", help="从京东榜单导出 xlsx 读取 SKU")
    ap.add_argument("--skus-file", help="skus.csv 路径（默认 BASE/skus.csv）")
    ap.add_argument("--skus", help="只抓指定序号，如 1,2,3")
    ap.add_argument("--top", type=int, default=50,
                    help="只从榜单前 N 名里取 SKU（默认 50，即只考虑排名靠前的 50 个，"
                         "后面的不考虑）。0 表示不限")
    ap.add_argument("--limit", type=int, default=0,
                    help="本次最多抓多少个（默认 0 = 有多少抓多少）。"
                         "常用：--top 50 --limit 25 表示从前50名里抓25个")
    ap.add_argument("--force", action="store_true", help="已抓过的也重抓")
    ap.add_argument("--delay", default="3-8", help="SKU 间随机延迟秒区间（默认3-8）")
    ap.add_argument("--max-fail", type=int, default=3, help="连续失败次数熔断（默认3）")
    ap.add_argument("--dry-run", action="store_true", help="只列 SKU 不抓取")
    ap.add_argument("--no-xlsx", action="store_true",
                    help="跑完不自动导出 report_images.xlsx（默认会自动导出）")
    ap.add_argument("--run-name", help="自定义批次目录名（默认：<榜单名>_<YYYYMMDD>）")
    ap.add_argument("--flat", action="store_true",
                    help="不使用 runs/ 批次目录，直接输出到 BASE（旧行为，不推荐）")
    args = ap.parse_args()

    BASE = Path(norm_path(args.base)).resolve()

    # ---- 读取 SKU（先读，因为批次名要从榜单文件名推断）----
    list_name_hint = None
    if args.from_xlsx:
        skus = read_skus_from_xlsx(norm_path(args.from_xlsx))
        list_name_hint = derive_list_name(args.from_xlsx)
    else:
        csv_path = Path(norm_path(args.skus_file)) if args.skus_file else BASE / "skus.csv"
        if not csv_path.exists():
            print(f"[错误] 找不到 {csv_path}，也没指定 --from-xlsx")
            return 2
        skus = read_skus_from_csv(str(csv_path))
        list_name_hint = derive_list_name(None, csv_path)

    # ---- 决定批次目录：runs/<榜单名>_<日期>/ ----
    today = datetime.now().strftime("%Y%m%d")
    if args.flat:
        RUN_DIR = BASE
    else:
        RUN_DIR = make_run_dir(BASE, list_name_hint or "榜单", today, args.run_name)
    IMG_DIR = RUN_DIR / "images"
    LOG_DIR = RUN_DIR / "logs"
    STATE_FILE = RUN_DIR / "state.json"
    REPORT_FILE = RUN_DIR / "report.csv"
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logfile = LOG_DIR / f"fetch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    if args.flat:
        log("[信息] --flat 模式：输出到 BASE 根目录（旧行为）", logfile)
    else:
        log(f"[信息] 批次目录：{RUN_DIR.relative_to(BASE)}", logfile)
    log(f"[信息] 读到 {len(skus)} 个 SKU"
        f"{'（榜单名推断: ' + list_name_hint + '）' if list_name_hint else ''}", logfile)

    if args.skus:
        idxs = [int(x.strip()) - 1 for x in args.skus.split(",") if x.strip().isdigit()]
        skus = [skus[i] for i in idxs if 0 <= i < len(skus)]
        log(f"[信息] 按序号筛选后剩 {len(skus)} 个", logfile)
    elif args.top and args.top > 0:
        # 只考虑榜单前 N 名，后面的不考虑
        total = len(skus)
        skus = skus[: args.top]
        if total > len(skus):
            log(f"[信息] 只取榜单前 {args.top} 名（共 {total} 个，其余 {total - args.top} 个不考虑）", logfile)

    if not skus:
        log("[错误] SKU 列表为空", logfile)
        return 2

    # ---- 断点续传过滤 ----
    state = load_state(STATE_FILE)
    done = state.get("done", {})

    # 本批 SKU 全集 + 来源，写进 state.json，供 fetch_stats.py 对账
    SCOPE_SKUS = list(skus)
    if args.from_xlsx:
        SOURCE_LABEL = f"xlsx:{Path(norm_path(args.from_xlsx)).name}"
    elif args.skus_file:
        SOURCE_LABEL = f"csv:{Path(norm_path(args.skus_file)).name}"
    else:
        SOURCE_LABEL = "csv:skus.csv"

    if not args.force:
        pending = [s for s in skus if s not in done]
        log(f"[信息] 已完成 {len(done)} 个，待抓 {len(pending)} 个", logfile)
    else:
        pending = skus
        log(f"[信息] --force 模式，全部重抓（{len(pending)} 个）", logfile)

    if args.limit and args.limit > 0:
        pending = pending[: args.limit]
    if not pending:
        log("[信息] 没有待抓 SKU，全部完成。用 --force 可重抓。", logfile)
        return 0

    d = args.delay.split("-")
    delay_lo, delay_hi = (float(d[0]), float(d[-1])) if len(d) >= 2 else (3.0, 8.0)

    log("=" * 62, logfile)
    log(f"  京东 SKU 主图抓取  本批 {len(pending)} 个", logfile)
    log(f"  BASE={BASE}", logfile)
    log(f"  延迟 {delay_lo}-{delay_hi}s  连续失败 {args.max_fail} 次熔断", logfile)
    log("=" * 62, logfile)

    if args.dry_run:
        for i, s in enumerate(pending, 1):
            log(f"  {i}. {s}", logfile)
        return 0

    # ---- 前置检查 ----
    if not check_daemon(logfile):
        return 3

    sid = session_start(logfile)
    if not sid:
        return 3

    rows = []
    fail_streak = 0
    ok_cnt = 0
    risk_hits = 0
    slow_mode = False
    stop_reason = None

    try:
        for i, sku in enumerate(pending, 1):
            url = f"https://item.jd.com/{sku}.html"
            log(f"[{i}/{len(pending)}] {sku}", logfile)

            nav_out = navigate(sid, url)
            if "__TIMEOUT__" in nav_out or "__ERROR__" in nav_out:
                log(f"    导航异常：{nav_out.strip()[:150]}", logfile)
                rows.append({"sku": sku, "status": "nav_error", "note": nav_out.strip()[:200],
                             "page_url": url, "ts": datetime.now().isoformat(timespec="seconds")})
                fail_streak += 1
            else:
                v, raw = extract(sid, sku, logfile)
                if not v:
                    log(f"    提取失败：{raw.strip()[:150]}", logfile)
                    rows.append({"sku": sku, "status": "extract_error", "note": raw.strip()[:200],
                                 "page_url": url, "ts": datetime.now().isoformat(timespec="seconds")})
                    fail_streak += 1
                else:
                    cur_url = v.get("url", "")
                    risk = is_risk_page(cur_url, v.get("bodySnip", ""))
                    if risk:
                        log(f"    [风控] 命中 {risk} → {cur_url[:90]}", logfile)
                        rows.append({"sku": sku, "status": "risk", "note": risk,
                                     "page_url": cur_url, "ts": datetime.now().isoformat(timespec="seconds")})
                        fail_streak += 1
                        risk_hits += 1
                        # 自适应降速：命中风控后本轮延迟翻倍，降低继续被拦的概率
                        if risk_hits >= 2 and not slow_mode:
                            slow_mode = True
                            delay_lo, delay_hi = delay_lo * 2.5, delay_hi * 2.5
                            log(f"    [降速] 已命中 {risk_hits} 次风控，本轮延迟提升至 "
                                f"{delay_lo:.0f}-{delay_hi:.0f}s", logfile)
                        if fail_streak >= args.max_fail:
                            stop_reason = f"连续 {fail_streak} 次风控，熔断停止"
                            log(f"\n[熔断] {stop_reason}", logfile)
                            save_state(STATE_FILE, build_state(
                                done, skus_all=SCOPE_SKUS, source=SOURCE_LABEL))
                            write_report(REPORT_FILE, merge_with_history(REPORT_FILE, rows), logfile)
                            break
                    elif not v.get("firstBig"):
                        log("    [失败] 未取到主图", logfile)
                        rows.append({"sku": sku, "status": "no_image",
                                     "title": v.get("title", ""), "price": v.get("price", ""),
                                     "comment_count": v.get("comment", ""),
                                     "promo": v.get("promo", ""),
                                     "shop": v.get("shop", ""), "page_url": cur_url,
                                     "ts": datetime.now().isoformat(timespec="seconds")})
                        fail_streak += 1
                    else:
                        img_url = v["firstBig"]
                        ext = ext_from_url(img_url)
                        out_path = IMG_DIR / f"{sku}{ext}"
                        ok = download(img_url, out_path)
                        title = v.get("title", "")
                        price = v.get("price", "")
                        log(f"    OK  {title[:30]}  价={price}  评价={v.get('comment') or '-'}"
                            f"  活动={'有' if v.get('promo') else '-'}"
                            f"  图={'成功' if ok else '下载失败'} ({v.get('imgCount')}张)", logfile)
                        rows.append({
                            "sku": sku,
                            "status": "ok" if ok else "img_download_failed",
                            "title": title, "price": price,
                            "comment_count": v.get("comment", ""),
                            "promo": v.get("promo", ""),
                            "shop": v.get("shop", ""),
                            "img_count": v.get("imgCount"),
                            "image_file": out_path.name if ok else "",
                            "image_url": img_url, "page_url": cur_url,
                            "note": "" if ok else "图片下载失败",
                            "ts": datetime.now().isoformat(timespec="seconds"),
                        })
                        if ok:
                            ok_cnt += 1
                            # state 必须存全字段：一旦 report 写失败需要补录，
                            # 缺 image_url/page_url 就会把 URL 补成空（历史踩坑）
                            done[sku] = {
                                "image": out_path.name,
                                "title": title,
                                "price": price,
                                "comment_count": v.get("comment", ""),
                                "promo": v.get("promo", ""),
                                "shop": v.get("shop", ""),
                                "img_count": v.get("imgCount"),
                                "image_url": img_url,
                                "page_url": cur_url,
                                "ts": datetime.now().isoformat(timespec="seconds"),
                            }
                            fail_streak = 0
                        else:
                            fail_streak += 1

            save_state(STATE_FILE, build_state(
                done, skus_all=SCOPE_SKUS, source=SOURCE_LABEL))
            written = write_report(REPORT_FILE, merge_with_history(REPORT_FILE, rows), logfile)

            if fail_streak >= args.max_fail:
                if not stop_reason:
                    stop_reason = f"连续 {fail_streak} 次失败，熔断停止"
                    log(f"\n[熔断] {stop_reason}", logfile)
                break

            if i < len(pending):
                time.sleep(random.uniform(delay_lo, delay_hi))
    finally:
        session_stop(sid)

    # ---- 汇总 ----
    log("", logfile)
    log("=" * 62, logfile)
    log(f"  完成：成功 {ok_cnt} / 本批 {len(pending)}", logfile)
    log(f"  累计已完成：{len(done)} 个", logfile)
    if stop_reason:
        log(f"  中断原因：{stop_reason}", logfile)
    log(f"  报告：{written if written else '（写入失败，见上文警告）'}", logfile)

    # state 与 report 对账，防止报告写入失败导致数据静默丢失
    if written:
        try:
            rp = list(csv.DictReader(io.StringIO(written.read_text(encoding="utf-8-sig"))))
            seen = {r["sku"] for r in rp}
            lost = [s for s in done if s not in seen]
            if lost:
                log(f"  [警告] 有 {len(lost)} 个已完成 SKU 不在报告中，正在补写："
                    f"{', '.join(lost[:5])}{' ...' if len(lost) > 5 else ''}", logfile)
                # 从原始 rows（本次抓取明细，字段最全）优先取，state 作兜底，
                # 避免把 image_url/page_url 补成空字符串（历史踩坑）
                by_sku = {}
                for _r in rows:
                    if _r.get("sku"):
                        by_sku.setdefault(_r["sku"], _r)
                for s in lost:
                    v = done[s]
                    src = by_sku.get(s) or {}
                    rp.append({
                        "sku": s,
                        "status": src.get("status") or "ok",
                        "title": src.get("title") or v.get("title", ""),
                        "price": src.get("price") or v.get("price", ""),
                        "comment_count": src.get("comment_count") or v.get("comment_count", ""),
                        "promo": src.get("promo") or v.get("promo", ""),
                        "shop": src.get("shop") or v.get("shop", ""),
                        "img_count": src.get("img_count") or v.get("img_count", ""),
                        "image_file": src.get("image_file") or v.get("image", ""),
                        "image_url": src.get("image_url") or v.get("image_url", ""),
                        "page_url": src.get("page_url") or v.get("page_url", ""),
                        "note": "由 state.json 补录",
                        "ts": src.get("ts") or v.get("ts", ""),
                    })
                fix = write_report(written, rp, logfile)
                if fix:
                    log(f"  [已修复] 报告补齐为 {len(rp)} 行 → {fix.name}", logfile)
        except Exception as e:
            log(f"  [警告] 报告对账失败：{e}", logfile)

    log(f"  批次目录：{RUN_DIR}", logfile)
    log(f"  图片目录：{IMG_DIR}", logfile)

    # ---- 自动导出带嵌入图片的 xlsx ----
    # 让交付物随手就有：H 列直接显示主图，点图可看原图。
    if not args.no_xlsx:
        try:
            import subprocess as _sp
            exp = Path(__file__).with_name("export_images_xlsx.py")
            if exp.exists():
                log("  正在导出带图片的 xlsx ...", logfile)
                # 传批次目录：报告与图片都在 RUN_DIR 下
                r = _sp.run([sys.executable, str(exp), str(RUN_DIR)],
                            capture_output=True, text=True, timeout=300)
                tail_lines = [l for l in (r.stdout or "").strip().splitlines()
                              if "完成 →" in l or "[警告]" in l or "[错误]" in l]
                for l in tail_lines:
                    log("  " + l.split("] ", 1)[-1], logfile)
                if r.returncode != 0 and not tail_lines:
                    log(f"  [警告] xlsx 导出返回码 {r.returncode}，可手动运行 "
                        f"export_images_xlsx.py 排查", logfile)
            else:
                log("  [提示] 未找到 export_images_xlsx.py，跳过 xlsx 导出", logfile)
        except Exception as e:
            log(f"  [警告] xlsx 导出失败（不影响图片与 CSV）：{e}", logfile)

    log(f"  日志：{logfile}", logfile)
    log("=" * 62, logfile)
    log("重跑本命令会自动跳过已完成的 SKU（断点续传）。", logfile)
    return 0


if __name__ == "__main__":
    sys.exit(main())
