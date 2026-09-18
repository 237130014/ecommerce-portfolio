# 竞品新品监控技能（competitor-new-product-monitor）

电商竞品监控能力：用 **bsk（Tencent/BrowserSkill）驱动真实登录态浏览器**抓取京东/天猫竞品店铺
「新品」排序商品 → 图片原图化 → 与上一轮对比（新增/涨价/降价/下架）→ 生成带变动角标的瀑布流看板。

## 为什么抓取层改成 bsk

传统无头浏览器在平台眼里「身份」就是假的：机器指纹 + 陌生账号 + 机房 IP，三重破绽叠加，
需要登录的页面往往连门都进不去。bsk 复用你日常使用的 Chrome、真实登录态、本地真实 IP，
把「设备/身份」这一层风控抹平；遇到验证码通过 `request-help` 交给人处理，处理完自动继续。

> 定位提醒：bsk 解决「你是谁」这一层，不解决「你采得多猛」这一层。本技能保持**串行 + 随机延迟**，
> 适合精准竞品调研，不适合一夜抓几千个 SKU 的批量采集。

## 目录结构

```
competitor-new-product-monitor/
├── SKILL.md                      # 技能工作流说明（触发方式、步骤、踩坑经验）
├── references/
│   ├── stores.example.json       # 店铺清单模板（占位符，复制为 stores.json 后填自己的店铺）
│   └── stores.json               # 【需自己创建，未随仓库提交】你的店铺清单
└── scripts/
    ├── scrape_new.py             # 抓取：bsk 驱动、串行限速、登录/验证码人工介入、断点续抓
    ├── fix_images.py             # 图片：转原图、带 Referer 下载、退避重试、低并发、去重、CSV
    ├── compare_new.py            # 变动对比：URL 归一化、阈值过滤、变动数据落盘、历史归档
    └── gen_dashboard.py          # 瀑布流看板：全部预览/单品牌查看、变动角标、只看变动、搜索/排序/放大
```

## 环境准备

1. 安装 bsk CLI（Windows / macOS / Linux 见 SKILL.md 第 0 节）
2. 浏览器（Chrome / Edge）安装 BrowserSkill 扩展并完成连接
   - Chrome：https://chromewebstore.google.com/detail/hhcmgoofomhgciiibhipgmgkgnoenaoi
   - Edge：https://microsoftedge.microsoft.com/addons/detail/browserskill/emacgiaaaiojkkpkddmmdfhmokgmnikg
3. 在普通终端常驻运行 `bsk daemon start`（窗口保持不关）
   - Windows cmd 里要用完整路径：`C:\Users\<你>\.local\bin\bsk.exe daemon start`
   - 若自定义过 `BSK_HOME`，**必须写 Windows 路径**（`C:\Users\<你>\.bsk`）；写成 Git Bash 的
     `/c/Users/...` 会让 bsk 找不到 daemon
4. 浏览器里登录京东 / 天猫
5. `bsk doctor` 自检通过（无 `fail` 行）

### 店铺 URL 必须自己提供，且要用「商品列表页」

**本技能不附带任何店铺 URL**，`stores.example.json` 里全是占位符，直接跑会报错。
你必须填**自己的**店铺，并且注意：店铺首页**抓不到商品**（只有导航和装修区块），必须填商品列表页 URL：

- 京东：`https://<店铺域名>.jd.com/view_search-{venderId}-{类目Id}-{店铺Id}-0-0-0-0-1-1-60.html`
- 天猫：`https://<店铺>.tmall.com/view_shop.htm?search=y&orderType=newOn_desc`

> 天猫注意：`category.htm` / `search.htm` 这类分类页**往往只渲染店铺外壳**（抓 0 条），真正出商品的是
> 「店内搜索页」`view_shop.htm?search=y`。脚本会自动把这两种 URL 转换成 view_shop 形式，但你直接填对更省事。

获取方式：浏览器打开店铺 → 点「所有商品」或任一分类 → 复制地址栏。填错脚本会明确报错跳过。

## 实测记录（2026-09-18）

### 单店深度验证

以某珠宝品牌官方旗舰店为样本跑通全链路（**测试店铺 URL 未随仓库提供**），产出 70 条真实商品数据：

| 环节 | 结果 |
|------|------|
| 抓取 | 70 条，标题/价格/图片/ID **100% 覆盖**，0 条占位图 |
| 图片下载 | 70/70 成功，0 失败，共 14MB |
| 变动对比 | 同批数据二次抓取 → 新增 0 / 下架 0 / 涨价 0 / 降价 0（**零误报**） |
| 变动检测 | 人为扰动 → 准确识别 新增1/下架1/涨价+15%/降价-8%，+0.3% 微幅波动被阈值过滤 |

### 多店规模验证（京东 + 天猫）

用一份 19 行店铺清单（京东 12 + 天猫 7）实跑，去重后 18 家：

| 环节 | 结果 |
|------|------|
| 抓取 | **16/16 店成功、1064 条商品**（京东 11 店 62–70 条/店；天猫 5 店约 69 条/店，最多 106 条） |
| 图片下载 | **1064/1064 成功，0 失败**（约 190MB，耗时约 9 分钟） |
| 天猫价格 | 字体加密（AlibabaSans102CustomFont）**已破解**：197 个密文字符全部解出，68/69 条拿到价格 |
| 看板 | 1064 条渲染正常、16 家店铺动态统计，品牌导航 / 只看变动 / 搜索排序均可用 |
| 基线 | compare 首轮自动建档到 `prev/`，可直接跑下一轮变动检测 |

已知限制（如实留空，不编造）：

- **商品评价数抓不到**：京东 `club.jd.com` 接口校验来源，页面 DOM 中始终为空
- **React 新版模板店铺暂不支持**：2 家天猫店铺改版后 DOM 里没有商品 ID/链接（数据在 React 内部 state），
  抓到 0 条属预期行为；需走 React fiber 内部状态，后续迭代
- **访问频率仍需人工控节奏**：bsk 抹平的是「身份」维度，抹不平「频率」维度

## 使用

```bash
python scripts/scrape_new.py   jd-baseline     # 1. 抓取（bsk 驱动）
python scripts/fix_images.py   jd-baseline     # 2. 图片转原图 + 下载
python scripts/compare_new.py  jd-baseline     # 3. 变动对比（需有 prev/ 或 history/）
python scripts/gen_dashboard.py jd-baseline    # 4. 生成瀑布流看板
```

多轮运行时注意：抓取会覆盖 `jd-baseline/jd_new_*.json`，所以**抓之前**先把上一轮的 json 移进 `jd-baseline/prev/`。
首次运行没有基线也没关系——`compare_new.py` 会自动把本轮数据建档为下一轮基线，不用手动搬文件。

## 店铺清单格式

把 `references/stores.example.json` 复制为 `references/stores.json`，替换成你自己的店铺：

```json
{
  "stores": [
    {"no": 1, "platform": "jd",    "name": "<你的京东店铺名>", "url": "https://<店铺域名>.jd.com/view_search-<venderId>-<类目Id>-<店铺Id>-0-0-0-0-1-1-60.html"},
    {"no": 2, "platform": "tmall", "name": "<你的天猫店铺名>", "url": "https://<店铺>.tmall.com/view_shop.htm?search=y&orderType=newOn_desc"}
  ]
}
```

> `stores.json` 属于个人配置，已在 `.gitignore` 中排除、不会被提交——**每个使用者填自己的店铺**；
> 随仓库发布的只有不含真实店铺的 `stores.example.json`。

脚本会自动把 `url` 切换成「新品」排序（京东改 view_search 路径第 5 段为 1，天猫加 `orderType=newOn_desc`）。

## 防风控要点

- 串行抓取 + 每店随机延迟（默认 4-9 秒，`--delay` 可调）
- 不并发、不高频定时
- 登录墙 / 验证码交给人处理（`bsk request-help`），不硬闯
- 图片下载低并发（3）+ 带 Referer + 指数退避

## 产出物

| 文件 | 说明 |
|------|------|
| `竞品新品瀑布流看板-{日期}.html` | 主交付：瀑布流看板。仅京东店铺时文件名为 `京东竞品新品瀑布流看板-{日期}.html`，含天猫等多平台时去掉平台前缀。含品牌导航（全部预览 / 单品牌查看）、变动角标、「只看变动」筛选 |
| `变动对比-{日期}.md` | 新增 / 下架 / 涨价 / 降价明细表 |
| `新品全量明细.csv` | 全量商品明细（含原图链接与本地图路径） |
| `变动数据.json` | 机器可读的变动集合，供看板使用 |
| `history/{日期}/` | 历史归档，保留多轮轨迹 |
