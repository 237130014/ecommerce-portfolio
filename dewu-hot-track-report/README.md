# 得物商机推荐趋势报告（dewu-hot-track-report）

把「翻得物后台高搜词 → 手抄到表格 → 拼趋势报告」压成一条可复现流水线：
**bsk 接管真实登录态浏览器抓全量热点 → 三步清洗 → 八章市场趋势报告（MD + HTML）**。

## 解决什么问题

得物后台「商机推荐 › 高搜词 › 查看更多类目热点」里，一个类目动辄 10 页热点卡片，
每张卡片要单独点开才知道人群、场景、价格带、关联商品。人工做法是边翻边抄，
一次周报要半天，而且抄不全、口径每次不一样。

这个技能改成**拦接口**：列表接口 `getHotTrackPage` 的响应本身就带全量明细字段，
翻页即累积，一轮下来 20 页 / 200+ 条热点结构化落盘，剩下的交给清洗和渲染。

## 为什么抓取层用 bsk

得物后台是**强登录态**页面，无头浏览器连门都进不去：机器指纹 + 陌生账号 + 机房 IP，
三重破绽叠加，风控一眼就能识别。bsk（Tencent/BrowserSkill）复用的却是你日常那个 Chrome、
真实登录态、本地真实 IP —— 它把「你是谁」这一层抹平了，只留下「你采得多猛」这一层需要自己控制。

所以本技能跟仓库里另外两个抓取类工具（`competitor-new-product-monitor`、`jd-sku-image-fetch`）
是**同一套抓取架构**：bsk 接管标签页 → 真实鼠标事件操作 → 拦接口拿结构化数据。
这套技术栈的完整讲解（为什么不用 headless、常用命令、坑位、取舍）见
**[docs/bsk-browser-automation.md](../docs/bsk-browser-automation.md)**。

> bsk 只解决「身份」，不解决「采得多猛」。本技能本身保持**逐页串行 + 翻页间隔**，
> 一次周报 20 页左右，属于正常人工浏览的量级。

## 流水线

```
bsk 接管标签页
   └─ 开「查看更多类目热点」抽屉 → 多选类目级联（勾父节点 = 全选子类）
        └─ 逐页翻 → 拦截 getHotTrackPage 响应 → data/cap_<组>.json
             └─ 16 列标准 CSV（原始 9 列 + 接口字段 8 列）
                  └─ 清洗漏斗：类目白名单 → 剔国际大牌 → 热度 > 均值
                       └─ 八章报告：执行摘要 / 热点对比 / 关键词 / 元素风格材质
                          / 场景人群 / 决策思路 / 商品案例 / 风险口径
```

默认两组对照，也可以自己写 config 换类目：

| 组 | 模式 | 范围 |
|---|---|---|
| A | `children` | 流行饰品/眼镜/服配 下 首饰、玛瑙/玉髓、水晶、黑曜石、朱砂、其他玉石、石英岩玉 |
| B | `top` | 黄金/珠宝/翡翠/玉石 整个一级类目 |

## 目录结构

```
dewu-hot-track-report/
├── SKILL.md                      # 技能工作流（触发方式、4 步流程、坑位速查）
├── references/
│   ├── page-flow.md              # 页面 DOM / 接口 / 交互流程细节（踩坑全记录）
│   ├── field-schema.md           # 字段口径、量纲换算、字段覆盖率缺口
│   └── groups.example.json       # 抓取范围模板（--config 用这个格式）
└── scripts/
    ├── scrape.py                 # bsk 驱动：开抽屉 → 勾类目 → 翻页拦截接口
    ├── to_csv.py                 # 接口响应 → 16 列标准 CSV
    ├── build_report.py           # 编排：CSV → 清洗 → 下图 → MD/HTML + 漏斗记录
    ├── analysis.py               # 清洗漏斗、统计口径、parse_heat
    ├── domain_dict.py            # 50 条类目白名单 + 30 个国际大牌别名
    ├── render_report.py          # 八章 MD / HTML 渲染
    └── inline_images.py          # 单文件分享版：图片压缩 + base64 内联
```

## 安装

前置：bsk CLI 可用、浏览器已连接、**已登录得物后台**、Python 装了 `pandas` + `jieba`
（要把报告外发，再加 `pillow`）。

在仓库根目录执行（会自动装依赖并落盘到 `~/.workbuddy/skills/`）：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

也可以手动把 `dewu-hot-track-report/` 整个目录复制到 `~/.workbuddy/skills/` 下。

装完**完全退出** WorkBuddy（含托盘图标）再重开，新建对话说一句
「跑一次得物商机推荐报告」即可触发。

## 命令行用法

```bash
PY="$HOME/.workbuddy/binaries/python/envs/default/Scripts/python.exe"

# 1. 抓（--groups A,B / --config ./my.json / --max-pages 10）
"$PY" ~/.workbuddy/skills/dewu-hot-track-report/scripts/scrape.py \
      --session dewu --out "./dewu-runs/$(date +%F)" --groups A,B --max-pages 10

# 2. 出报告（周目录按抓取日期自动建）
"$PY" ~/.workbuddy/skills/dewu-hot-track-report/scripts/build_report.py \
      --data-dir "./dewu-runs/$(date +%F)/data" \
      --base "./dewu-runs" --capture-date "$(date +%F)"
```

产出：

```
<周目录>/
├── 原始数据/得物商机推荐_<date>.csv      # 16 列标准 + 8 列接口原始字段
├── 分析报告/…-<周标签>.md / .html        # 八章报告
├── 分析报告/assets/*.jpg                # 热点长图（已本地化，不依赖外链）
└── 过程记录/clean_funnel.json            # 每档剔除明细，可追溯
```

## 清洗口径（业务方确认过，别擅自改）

| 步骤 | 规则 |
|---|---|
| 1 类目白名单 | `domain_dict.py` 里 50 条类目，命中即留 |
| 2 国际大牌 | 30 个品牌中英文别名命中即剔（避免「卡地亚同款」类伪机会） |
| 3 热度阈值 | 搜索热度 > 全量均值保留；再按成交热度均值分「高成交 / 低成交」 |

热度分布极度右偏，阈值过滤通常会砍掉 80%+，只剩十几条 —— **这是预期行为**，
不要为了报告好看把阈值调松。

## 要把报告发给别人？加一个 `--inline`

报告里的图片有两处坑，直接发 HTML 会一片灰块：

| 图片 | 原地址 | 单独发 HTML 的后果 |
|---|---|---|
| 17 张热点长图 | `assets/hotspot_xxx.jpg`（本地相对路径） | 文件没跟着走 → 404 |
| 120 张相似机会品图 | `https://cdn.poizon.com/…`（远程外链） | 对方网络 / 防盗链 / 图片过期 → 加载不出来 |

加 `--inline` 会另出一份**单文件分享版**：本地长图缩到 1400px、远程缩略图缩到 360px，
统一转 JPEG 后 base64 内联，137 张图全塞进一个文件里，体积约 2.5 MB。
微信、邮件、钉钉直接发，对方不联网也能看全。

```bash
# 出报告时一起出
"$PY" ~/.workbuddy/skills/dewu-hot-track-report/scripts/build_report.py \
      --data-dir "./dewu-runs/$(date +%F)/data" --base "./dewu-runs" --inline

# 已生成的报告补跑
"$PY" ~/.workbuddy/skills/dewu-hot-track-report/scripts/inline_images.py \
      "分析报告/得物商机推荐市场趋势分析报告-<周标签>.html"
```

需要 `pillow`（`pip install pillow`）。**默认不开**：日常自己看不必背 2.5 MB 的体积。

> 还有一种情况是图片本来就抓不到（得物 CDN 拒绝、热点本身没图）—— 那部分是数据缺口，
> 内联解决不了，报告里会显示「热点图加载失败」的说明块。

## 三个关键坑（完整版见 references/page-flow.md）

1. **筛选入口**是「查看更多类目热点」弹出的多选级联，不是页面上方那个单选的「常用筛选」
2. antd 级联对 `element.click()` 无反应，**必须真实鼠标事件**；想勾二级必须先 hover 一级，
   直接点一级 = 勾整个一级类目
3. 第 1 页的接口响应不会自己出现 —— 先向前翻到底，再退回第 1 页把它捞回来

量纲也别搞错：热度是**裸指数**（6650811 = 665 万），环比整数是 **0.01% 单位**（2187 = +21.87%）。
