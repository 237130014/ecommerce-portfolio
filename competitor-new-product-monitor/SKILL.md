---
name: competitor-new-product-monitor
description: 竞品新品监控与瀑布流看板生成。当用户提到"竞品监控/竞品价格监控/竞品新品监控/更新竞品看板/竞品瀑布流/看看竞品上新/抓竞品数据"等意图时使用，尤其是经营珠宝饰品、银饰、时尚饰品的商家需要盯竞品店铺热销新品、价格调整、上架下架时。流程：用 bsk（BrowserSkill，真实登录态浏览器）抓取京东/天猫竞品店铺「新品」排序商品 → 图片转原图并下载 → 与上一轮对比标出新增/涨价/降价/下架 → 生成带变动角标的花瓣网式瀑布流看板 HTML 和明细 CSV。即使只有"跑一次竞品价格监控"这类简短指令也应触发。
---

# 竞品新品监控

把"盯竞品店铺新品"变成一条可复现的流水线：**抓取 → 图片 → 变动对比 → 瀑布流看板**。

抓取层由 `bsk`（Tencent/BrowserSkill）驱动**真实登录态浏览器**，从根上解决两个老问题：
无头浏览器被平台风控拦死、需要登录的页面进不去。

## 0. 前置条件（首次使用需逐项确认）

1. **bsk CLI**：`bsk --version` 能输出版本即可；失败则安装：
   - Windows：`irm https://raw.githubusercontent.com/Tencent/BrowserSkill/main/install.ps1 | iex`
   - macOS/Linux：`curl -fsSL https://raw.githubusercontent.com/Tencent/BrowserSkill/main/install.sh | sh`
2. **浏览器扩展**：Chrome / Edge 安装 BrowserSkill 扩展并完成连接
3. **常驻守护进程**：在普通终端运行 `bsk daemon start`，**窗口保持不关**（cmd 里要用 Windows 路径写法）
4. **登录态**：在浏览器里已登录目标平台（京东 / 天猫）
5. **店铺清单（必须自己提供）**：本技能**不附带任何店铺 URL**，`stores.example.json` 只是格式模板。
   复制它为 `references/stores.json`，把占位内容替换成**你自己的**店铺商品列表页 URL；
   没替换就跑脚本会直接报错，不会拿别人的店铺去抓

用 `bsk doctor` 自检；出现 `fail` 行按提示 hint 处理后再继续。

### 怎么拿「商品列表页」URL（最容易踩的坑）

**本技能不附带任何店铺 URL，必须自己提供**——示例里的 `<...>` 都是占位符，原样跑会直接报错。

**店铺首页抓不到东西**——京东/天猫的店铺首页只有导航和装修区块，没有商品卡片。必须用**商品列表页**：

- **京东**：打开店铺 → 点左侧「所有商品」或任一分类 → 复制地址栏，形如
  `https://<店铺域名>.jd.com/view_search-<venderId>-<类目Id>-<店铺Id>-0-0-0-0-1-1-60.html`
  （URL 里必须含 `view_search`，脚本会自动把排序切成「新品」）
- **天猫**：打开店铺 → 点「全部商品」/店内搜索 → 复制地址栏。**推荐形态**
  `https://<店铺>.tmall.com/view_shop.htm?search=y&orderType=newOn_desc`
  （`category.htm` / `search.htm` 常常只渲染店铺外壳、抓 0 条；脚本会自动转成 view_shop 形式，但你直接拿对更稳）

把 URL 里的排序参数保持原样即可，脚本会自动改成新品排序。填了首页 URL 脚本会**明确报错并跳过**，不会静默抓 0 条。

## 目录约定

- `BASE`（数据目录）：默认当前工作目录下的 `jd-baseline/`；脚本均以 BASE 为第一参数
- `references/stores.json`：店铺清单（**需自己提供**；个人配置，不随仓库提交，模板见 `stores.example.json`）
- `BASE/jd_new_{序号}_{店名}.json`：每店抓取结果（store/platform/url/sort/fetched_at/count/items[]）
- `BASE/images/{序号}_{三位序号}.jpg`：下载的商品主图（原图）
- `BASE/prev/`：上一轮数据备份（本轮对比基准）
- `BASE/history/{日期}/`：历史归档，保留多轮轨迹
- `BASE/变动数据.json`：变动结果，供看板打角标
- 交付物：`BASE/竞品新品瀑布流看板-{日期}.html`（只有京东店铺时命名为 `京东竞品新品瀑布流看板-{日期}.html`，含天猫等多平台时去掉平台前缀）、`BASE/新品全量明细.csv`、`BASE/变动对比-{日期}.md`

## 工作流

### Step 1 备份上一轮（有数据时）

若 `BASE/jd_new_*.json` 存在：整体移动到 `BASE/prev/`，作为本轮对比基准。首次抓取无此步。

### Step 2 抓取（bsk 驱动）

```bash
python {skill_dir}/scripts/scrape_new.py {BASE}
```

常用参数：

| 参数 | 作用 |
|------|------|
| `--stores 1,3,5` | 只抓指定序号店铺 |
| `--platform jd\|tmall` | 只抓指定平台 |
| `--force` | 已抓过的店也重抓（默认跳过 = 断点续抓） |
| `--delay 4-9` | 每店之间的随机延迟秒数（防风控，默认 4-9） |
| `--dump-html DIR` | 额外存页面 HTML，便于排查选择器 |

行为要点：
- **串行抓取**，每店之间随机延迟，模拟人的浏览节奏
- 自动把店铺 URL 切换成「新品」排序（京东 view_search 路径第 5 段置 1；天猫 `orderType=newOn_desc`）
- **命中登录墙 / 验证码时自动调用 `bsk request-help`** 请用户接管，处理完自动继续
- 单店失败不影响其它店，最后汇总失败清单；失败店铺可重跑（已成功的会跳过）

### Step 3 图片处理

```bash
python {skill_dir}/scripts/fix_images.py {BASE}
```

- 链接转原图：京东 `360buyimg` 的 `/n7/` → `/n0/`；天猫 `alicdn` 去掉尺寸/质量后缀
- **带 Referer 下载**（规避图床防盗链）+ **指数退避重试**（1s/2s/4s）+ **低并发**（3，防风控）
- 两层去重：店内按商品链接、CSV 全局按商品链接
- 更新 JSON 与 `新品全量明细.csv`；失败的图片如实记录并在报告里说明

### Step 4 变动对比

```bash
python {skill_dir}/scripts/compare_new.py {BASE}
```

- **URL 归一化匹配**：按平台稳定商品 ID 比对，商品换活动链接不会被误判成「下架 + 新增」
- **阈值过滤**：`--min-pct`（默认 1%）过滤一分钱级别的噪音
- **可选基准**：`--against 2026-09-10` 对比指定历史日期
- **首轮自动建档**：没有 `prev/` 时不会报错跳过，而是自动把本轮数据复制到 `prev/` 作为下一轮基线（不需要手动搬文件）
- 输出：`变动对比-{日期}.md`、`变动数据.json`，并归档到 `history/{日期}/`

### Step 5 瀑布流看板

```bash
python {skill_dir}/scripts/gen_dashboard.py {BASE}
```

- 瀑布流卡片 + 品牌导航 chips + 关键词搜索 + 价格排序 + 点击放大（lightbox）+ 下载 CSV
- **品牌导航：全部预览 + 单品牌查看**——默认「全部预览」，点某个品牌只呈现该品牌商品；
  再点一次同一品牌、或点「× 返回全部预览」回到全部。与搜索/排序/只看变动叠加生效
- **变动角标**：新上架 / 涨 x% / 降 x%
- **「只看变动」筛选**：一键过滤出本轮有变化的商品

### Step 6 交付

`present_files` 依次推：看板 HTML（主交付）→ 变动对比 md → 明细 CSV。
汇报：新增/涨价/降价/下架数量、价格待补数量、失败店铺与原因。

## 关键经验（踩坑记录）

### 风控与身份

1. **风控的本质是"身份"**：无头浏览器 = 机器指纹 + 陌生账号 + 机房 IP，三重破绽叠加。bsk 用你真实的浏览器、真实登录态、本地 IP，把这一层直接抹平
2. **bsk 解决身份，不解决频率**：访问太猛照样会被风控。保持串行 + 随机延迟，不要并发、不要高频定时抓取
3. **验证码不要硬闯**：用 `bsk request-help` 交给人处理，处理完自动继续。这是半自动打法，不是全自动跑量

### bsk 环境（Windows 实测）

4. **`BSK_HOME` 不能给 Git Bash 风格路径**：`BSK_HOME=$HOME/.bsk` 会展开成 `/c/Users/xxx/.bsk`，Windows 版 bsk 读不懂 → 报「ensure daemon is running」，即使 daemon 活得好好的。**要么不设这个变量（默认目录就是对的），要么写 Windows 路径 `C:\Users\xxx\.bsk`**
5. **`navigate` 用 `load`，别用 `networkidle`**：京东/天猫页面有常驻埋点和轮询请求，`networkidle` 可能永远不触发而误报超时。内容是否就绪交给滚动等待逻辑判断
6. **扩展禁止访问 `file://`**：想让 agent 打开本地看板 HTML 验证渲染会被拒（`Navigating to local URL is not allowed`），只能靠静态检查或让用户自己看

### 京东店铺页 DOM（实测，2026-09）

7. **商品卡片选择器是 `li.jSubObject`**（内层 `.jItem`），一页约 60–70 个。
   ⚠️ 陷阱：`li[data-src]` 是**缩略图轮播项**（class `jCurrent`），里面只有 `href="javascript:;"`，不是商品卡片；用它当主选择器会抓到 0 条
8. **价格和图片都是滚动懒加载**：
   - 首屏只有 4 条左右有价格，其余 `.jdNum` 内容是 `&nbsp;`；必须滚动后才异步填充
   - 图片首屏是 `class="J_imgLazyload"` 的 gif 占位图，真实地址在 **`original` 属性**里（其次才是 `src`）
   - 做法：逐步滚动整页（每步约 `0.75 × 视口高`、停 650ms）→ 轮询「出价数/出图数」达标再提取。实测可达 70/70 全覆盖
   - 实测 2026-09-18：`mall.jd.com/view_search-...` 域名可直接用（不必换成 `ctf.jd.com`）；`preprice` 属性服务端直出，不依赖滚动
9. **价格绝不能取 `jdprice` 属性**：那是 SKU 编号。价格取 `.jdNum` 文本，兜底 `preprice` 属性。曾因回退到 `jdprice` 导致「价格」字段被写成商品 ID
10. **评价数抓不到**：`.jCommentNum` 由 `club.jd.com/comment/productCommentSummaries.action` 异步填充，页面上始终为空；直接 fetch 该接口返回「系统繁忙」（京东校验来源）。现已如实留空，不编造
11. **标题取 `.jDesc a`**，链接取 `.jPic a[href*="item.jd.com"]`（协议相对 URL `//item.jd.com/xxx.html`，需转绝对地址并剥掉 query/hash）

### 天猫店铺页 DOM（实测，2026-09-18）

12. **URL 必须转成 `view_shop.htm?search=y`**：用户常给的 `category.htm` / `search.htm` 往往只渲染店铺外壳（0 商品）；「店内搜索页」`view_shop.htm?search=y&orderType=newOn_desc` 才渲染商品。脚本已自动做这个转换（`apply_new_sort`）
13. **商品卡片是 `dl.item[data-id]`**，标题取 `a.item-name`（兜底 `dt.photo img` 的 alt），图片取 `dt.photo img` 的 src，销量取 `.sale-num`
14. **天猫商品 ID 在 query 里（`?id=xxx`）**——URL 绝不能整段 `split('?')`，否则所有商品 URL 都变成同一个 `detail.tmall.com/item.htm`，69 个商品被去重成 1 条（真实踩过）。规范化方式：提取 id 后重建 `https://detail.tmall.com/item.htm?id=<id>`
15. **价格是字体加密的，可破解**：`.c-price` 里是密文（如「曍燰忈叱捨澥」），靠 `@font-face`（AlibabaSans102CustomFont，逐页随机映射）渲染成正常数字。CSV 备注说「React 模板才加密」已过时——**经典模板同样加密**。解法：把密文字符和 `0-9/.` 用同一字体画到 canvas，逐像素比对字形反查映射。实测 197 个密文字符全部解出、68/69 有价格
16. **React 新版店铺模板暂不支持**（实测 2 家天猫店，卡片是 `[class*="cardContainer"]`）：DOM 里**没有任何商品 ID 和链接**（数据在 React 内部 state），价格同样是密文字体。需要走 React fiber 内部状态才能拿到，后续迭代。这类店铺脚本会抓到 0 条，属预期行为

### 工程细节

17. **京东新品排序**：view_search 路径第 5 段为 1（形如 `-0-1-0-0-`），实测排序值：`0`=综合、`5`=销量、`4`=价格、`1`=新品
18. **图片 n7→n0**：只替换 `360buyimg.com/n7/` → `/n0/`，不要全局替换 `n7`
19. **HTML 图片路径**：必须相对路径 `images/xx.jpg`（HTML 与 images 同在 BASE 下）；写 `jd-baseline/images/xx.jpg` 会路径重复 404
20. **序号解析**：`jd_new_01_xx.json` 用正则 `r'jd_new_(\d+)_'` 提取，不要用 `split('_')[1]`（会取到 'new' 导致文件互相覆盖）
21. **CSV 被占用**：Excel 打开 CSV 时写会失败 → 自动降级写 `_v2`；看板会自动识别并指向实际文件
22. **看板与图片目录必须一起移动**：HTML 引用相对路径 `images/`
23. **禁止编造数据**：抓不到就如实说「未抓到 / 价格待补」，绝不虚构价格或商品

## 输出格式（固定模板）

- 看板卡片 = 主图(原图) + 店标签 + 变动角标 + 商品名 + 价格 + 评价数 + 点击放大 + 商品链接
- CSV 列：`store, title, price, activity, comments, image_n0, local_image, url, id`
- 变动 md：`| 商品 | 店铺 | 原价→现价 | 幅度 | 链接 |`
