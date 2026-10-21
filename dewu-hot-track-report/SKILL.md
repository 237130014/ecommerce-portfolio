---
name: dewu-hot-track-report
description: 抓取得物（得物/poizon）后台「商机推荐 › 高搜词 › 查看更多类目热点」的全量热点明细，并按八章口径生成《得物商机推荐市场趋势分析报告》（MD + HTML）。当用户要求在得物后台按类目抓高搜词/热点、跑得物商机推荐、出得物市场趋势周报、看某类目的机会价格带与相似机会品、或说"跑一次得物商机推荐报告""抓得物高搜词""出得物趋势报告"时使用。流程：bsk 接管真实登录态浏览器 → 打开「查看更多类目热点」抽屉 → 多选类目筛选 → 翻页拦截 getHotTrackPage 接口拿明细 → 转 16 列标准 CSV → 类目白名单/国际大牌/热度阈值三步清洗 → 渲染八章报告（执行摘要、热点对比、热门关键词、元素风格材质、场景人群、决策思路、商品案例、风险口径）。触发词：得物商机推荐、得物高搜词、得物热点、高搜词、商机推荐报告、得物市场趋势、得物新品趋势、得物后台抓数据、全网热点推荐、查看更多类目热点。
agent_created: true
---

# 得物商机推荐 · 高搜词趋势报告

把「翻得物后台热点 + 手抄数据 + 拼报告」变成一条可复现流水线：
**抓取 → 清洗 → 八章报告**。

抓取层用 bsk（BrowserSkill）驱动**真实登录态浏览器**——得物后台需要登录态，
无头浏览器进不去；同时改用**接口响应拦截**取明细，不再逐条点开卡片。

## 何时使用

- 要按类目抓得物后台「高搜词」热点，尤其是「一个一级类目下只挑几个二级类目」
- 要出《得物商机推荐市场趋势分析报告》（周维度）
- 要看某类目的机会价格带、相似机会品竞品、搜索/成交环比与连涨信号

## 前置条件（首次使用逐项确认）

1. **bsk CLI**：`bsk --version` 有输出。装法见 `references/page-flow.md`
   （仓库版还带一份抓取层技术栈总览：`docs/bsk-browser-automation.md`）
2. **浏览器已连接**：`bsk browsers` 能看到 Chrome/Edge
3. **已登录得物后台**，且有一个标签页停在
   `https://stark.dewu.com/main/businessApp/opportunity?tabId=suggestion`
4. **Python 依赖**：`pandas`、`jieba`（要出单文件分享版再加 `pillow`）

```bash
PY="$HOME/.workbuddy/binaries/python/envs/default/Scripts/python.exe"   # Windows 托管版
[ -f "$PY" ] || PY="$(command -v python3 || command -v python)"
"$PY" -c "import pandas,jieba" 2>/dev/null || "$PY" -m pip install -q pandas jieba
```

## 工作流

### 第 1 步 · 接管标签页

```bash
bsk doctor
bsk session start --json --no-focus --name dewu
bsk tab list --session dewu --json        # 找 url 含 stark.dewu.com 的 tab_id
bsk tab borrow <tab_id> --session dewu --json --timeout 90s
bsk screenshot --session dewu --out step0.png
```

接管会把页面移进「Agent 窗口」，**先截图确认真的停在高搜词页**，再往下走。
`bsk tab list` 没找到就请用户把页面打开，不要自己 navigate（登录态和 tabId 都对不上）。

### 第 2 步 · 抓取

```bash
SK="$HOME/.workbuddy/skills/dewu-hot-track-report"
DAY=$(date +%F)
"$PY" "$SK/scripts/scrape.py" --session dewu --out "./dewu-runs/$DAY" --groups A,B --max-pages 10
```

默认两组（`references/groups.example.json` 即默认值）：

| 组 | 模式 | 范围 |
|---|---|---|
| A | `children` | 流行饰品/眼镜/服配 下的 首饰、玛瑙/玉髓、水晶、黑曜石、朱砂、其他玉石、石英岩玉 |
| B | `top` | 黄金/珠宝/翡翠/玉石 整个一级类目 |

自定义范围就写一份 config 传 `--config`：

```json
[{"key":"C","label":"某类目","mode":"children","parent":"一级类目名","items":["二级1","二级2"]}]
```

`mode` 只有两种：`top`（勾一级节点本身）、`children`（展开一级后勾指定二级）。

脚本会打印每组「页数 / 条数 / 筛选结果」，产出 `<out>/data/cap_A.json`、`cap_B.json`。

### 第 3 步 · 转 CSV + 出报告

```bash
"$PY" "$SK/scripts/build_report.py" --data-dir "./dewu-runs/$DAY/data" --base "./dewu-runs" --capture-date "$DAY"
```

周目录按抓取日期自动命名（如 `2026年10月第四周-2026年10月20日`），产出：

```
<周目录>/
├── 原始数据/得物商机推荐_<date>.csv        # 16 列标准 + 8 列接口原始字段
├── 分析报告/…-<周标签>.md / .html          # 八章报告
├── 分析报告/…-<周标签>-单文件分享版.html   # 仅 --inline，图片全内嵌，可直接外发
├── 分析报告/assets/*.jpg                   # 热点长图（已下载本地，不再依赖外链）
└── 过程记录/clean_funnel.json              # 逐步剔除明细，可追溯
```

已有 CSV 只想重出报告：`--csv <路径> --week-dir <周目录>`；不想下图加 `--no-images`。

### 第 4 步 · 要发给别人就出「单文件分享版」

普通 HTML 是**不自包含**的：热点图是 `assets/*.jpg` 相对路径、相似机会品图是 `cdn.poizon.com` 外链，
单独把 HTML 发给别人，图片会全变成「加载失败」的灰块。加 `--inline` 就能一次产出可分享版本：

```bash
"$PY" "$SK/scripts/build_report.py" --data-dir "./dewu-runs/$DAY/data" --base "./dewu-runs" --inline
# 或对已生成的报告补跑
"$PY" "$SK/scripts/inline_images.py" "<周目录>/分析报告/…-<周标签>.html"
```

做的是：本地热点长图缩到 1400px、远程案例图缩到 360px，统一转 JPEG 后 base64 内联，
输出 `<…>-单文件分享版.html`（约 2~3 MB，137 张图全在文件里）。微信 / 邮件 / 钉钉直接发，对方不联网也能看全。

> 依赖 `pillow`。**默认不开** `--inline`：日常自己看不必背 2.5 MB 的体积，只在要外发时加。

### 第 5 步 · 交付

用 `present_files` 呈现 **HTML 报告 → MD 报告 → CSV**（要外发再加分享版 HTML），并口头汇报三件事：

1. 抓了多少组/页/条，每组命中多少（要如实说「不足 10 页」是因为数据本身只有这些）
2. 清洗漏斗：原始 → 类目白名单 → 国际大牌 → 热度阈值，每一档掉了多少
3. 本次数据的**硬缺口**（缺字段覆盖率，见 `references/field-schema.md` 第 5 节）

## 清洗口径（业务方确认过，不要擅自改）

| 步骤 | 规则 |
|---|---|
| 1 类目白名单 | `domain_dict.py` 里 50 条类目，命中即留 |
| 2 国际大牌 | 30 个品牌中英文别名命中即剔（避免"和卡地亚同款"类伪机会） |
| 3 热度阈值 | 搜索热度 > 全量均值，保留；再按成交热度均值分「高成交 / 低成交」两组 |

阈值是 `>` 均值，**不是** top N。因热度分布极度右偏（中位数远低于均值），
这一步通常会砍掉 80%+ 的条目，只剩十几条。这是预期行为，不要为了"数据好看"调松。

## 脚本

| 文件 | 作用 |
|---|---|
| `scripts/scrape.py` | bsk 驱动抓取：开抽屉 → 多选类目 → 翻页拦截接口。`--groups A,B` / `--config` / `--max-pages` |
| `scripts/to_csv.py` | 接口响应 → 16 列标准 CSV；也提供 `week_label()` |
| `scripts/build_report.py` | 编排：CSV → 清洗 → 下载图 → MD/HTML + 漏斗记录 |
| `scripts/analysis.py` | 清洗漏斗、统计、`parse_heat` 等口径函数 |
| `scripts/domain_dict.py` | 类目白名单 + 国际大牌别名 |
| `scripts/render_report.py` | 八章 MD/HTML 渲染 |
| `scripts/inline_images.py` | 出单文件分享版：本地图 + 远程案例图压缩后 base64 内联（需 pillow） |

## 坑位速查（详见 `references/page-flow.md`）

- 筛选入口是「查看更多类目热点」打开的多选级联，**不是**页面上方的「常用筛选」单选
- 想勾二级，必须先 `hover` 一级展开；直接点一级 = 勾整个一级类目
- antd 级联对 `element.click()` 无反应，**必须真实鼠标事件**
- 抽屉叠加，关详情别用 `.ant-drawer-close`（会误关外层列表）
- 第 1 页响应不会自己出现 → 先向前翻到底，再退回第 1 页
- 页面刷新 = hook 失效，要从第 2 步重来
- 热度是**裸数字指数**（6650811 = 665 万），环比整数是 **0.01% 单位**（2187 = 21.87%）

## 结果自查清单

报告生成后逐项确认，别把空章节当正常：

- [ ] `最终分析集 > 0`（脚本内已 assert，若失败说明白名单/阈值与本次类目不匹配）
- [ ] HTML 里没有 `None` / `nan` 字面量
- [ ] 八个 `<h2>` 章节齐全，且「四、元素/风格/材质」「五、场景/人群」若数据薄，
      已在「八、风险提示与数据口径」里写明是平台缺字段
- [ ] `assets/` 图片数与分析集条数接近（下载失败会打印出来）
- [ ] 要外发时检查分享版：`data:image/jpeg;base64` 数量 ≈ 热点图×2 + 相似品数，且文件里不再有 `assets/` 或 `cdn.poizon.com` 的 `src` 残留
- [ ] `过程记录/clean_funnel.json` 的 `finalCount` 与 MD 报告里的数字一致
