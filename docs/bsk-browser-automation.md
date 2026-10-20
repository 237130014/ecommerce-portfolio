# 抓取层技术栈：bsk（Tencent/BrowserSkill）

本仓库所有**需要登录态**的抓取工具（竞品监控 / 京东主图抓取 / 得物热点分析）共用同一套抓取层：
用 bsk 接管你日常使用的浏览器，而不是起一个无头浏览器。

这份文档是这个技术栈的**单一出处**，各工具 README 只讲自己业务侧的差异。

---

## 1. 一句话

bsk 是一组 CLI 命令，通过浏览器扩展把**真实浏览器标签页**的控制权借给脚本：
`tab borrow` 拿到 tab → `evaluate` 注入 JS / `click` 真实点击 / `network` 读接口 → 干完 `tab finalize` 还回去。
脚本跑在你的浏览器里，用的是你的登录态、你的 IP、你的设备指纹。

## 2. 为什么不用 headless

传统无头浏览器在平台眼里「身份」就是假的，三重破绽同时暴露：

| 破绽 | 无头浏览器 | bsk |
|---|---|---|
| 设备指纹 | 全新 profile、异常 WebGL / Canvas / 字体集合 | 真实用户的浏览器 |
| 登录态 | 要么没登录，要么是新号异地登录 | 你日常在用的、长期活跃的账号 |
| 网络环境 | 机房 / 代理 IP、异常 UA | 本地家庭或办公网络真实 IP |

三重叠加，风控不需要多聪明就能识别。真要登录的页面，往往**连门都进不去** ——
不是被封，是页面压根不会给你渲染出数据。

bsk 把「你是谁」这一层抹平：在平台看来，就是本人在浏览器里正常点了点。
遇到验证码也不用硬闯 —— `bsk request-help` 把控制权交给人，人处理完脚本自动继续。

## 3. 它不解决什么

> **bsk 抹平的是「身份」维度，抹不平「频率」维度。**

同一个人一小时点 3000 次商品页，照样触发风控。所以三个工具都保留了节制：

- 串行抓取，不并发
- 每步随机间隔（4–9 秒级别，可调）
- 连续失败熔断
- 只抓「一个人正常会看」的量级（一次周报 20 页、一次竞品巡检几十家店）

这套组合的定位是**精准调研**，不是一夜抓十万 SKU 的批量采集。真需要那个量级，该走开放平台或采购数据。

## 4. 常用命令

```bash
bsk doctor                                   # 环境自检，看有没有 fail 行
bsk browsers                                 # 列出已连接浏览器
bsk daemon start                             # 常驻守护进程（窗口别关）
bsk session start --json --no-focus --name dewu   # 建一个命名会话
bsk tab list    --session dewu --json        # 找目标 tab_id
bsk tab borrow  <tab_id> --session dewu --timeout 90s
bsk screenshot  --session dewu --out step0.png
bsk evaluate    --session dewu --file js/extract.js
bsk click       --session dewu --selector '<css>'
bsk network     --session dewu --json        # 看请求，定位真接口
bsk tab finalize <tab_id> --session dewu     # 还回去
```

## 5. 三个工具怎么共用它

| 工具 | 用 bsk 做什么 | 取数方式 |
|---|---|---|
| [competitor-new-product-monitor](../competitor-new-product-monitor/README.md) | 打开竞品店铺「新品」排序页 | 解析 DOM 商品卡 + 翻页 |
| [jd-sku-image-fetch](../jd-sku-image-fetch/README.md) | 逐个打开京东商品详情页 | DOM 取主图 / 标题 / 价格 / 评价数 |
| [dewu-hot-track-report](../dewu-hot-track-report/README.md) | 开「查看更多类目热点」抽屉、多选类目、翻页 | **注入 fetch/XHR 拦截器**，直接收 `getHotTrackPage` 响应 |

第三种是这套架构里性价比最高的一档：**列表接口的响应本身就带全量明细字段**，
不用一条条点开卡片。代价是要先摸清接口、并且翻页时序得自己对（见下）。

## 6. 环境准备

1. 安装 bsk CLI（`bsk --version` 有输出即算装好）
2. 浏览器装 BrowserSkill 扩展并连接
   - Chrome：https://chromewebstore.google.com/detail/hhcmgoofomhgciiibhipgmgkgnoenaoi
   - Edge：https://microsoftedge.microsoft.com/addons/detail/browserskill/emacgiaaaiojkkpkddmmdfhmokgmnikg
3. 普通终端里常驻 `bsk daemon start`，**窗口不要关**
4. 浏览器里把目标平台登录好，留一个停在目标页的标签页
5. `bsk doctor` 无 `fail`

## 7. 踩过的坑

**Windows 路径**
`bsk daemon start` 在 cmd 里要用完整路径（`C:\Users\<你>\.local\bin\bsk.exe`）；
自定义过 `BSK_HOME` 时必须写 Windows 路径（`C:\Users\<你>\.bsk`），写成 Git Bash 的 `/c/Users/...` 会让 daemon 找不到。

**别自己 navigate**
登录态和 tabId 是绑在用户那个标签页上的。`tab list` 没找到目标页就请用户打开，
不要 `tab goto` 新建一个 —— 新标签往往没登录态。

**antd / React 组件不认合成事件**
`element.click()` 对 Ant Design 级联、按钮常常无效。要用 bsk 的真实鼠标事件（`bsk click`），
或者按组件真实交互顺序来（hover 一级 → 再点二级）。

**页面刷新 = 注入失效**
`evaluate` 注入的拦截器在刷新后全没了，只能从抓取那一步重来。

**类目哈希类名不可靠**
antd 的 `css-xxxx` 哈希会变，选择器要用属性部分匹配（`[class*=cardGrid]`）+ 文案定位兜底。

## 8. 取舍

| 优点 | 代价 |
|---|---|
| 登录态、验证码、风控身份问题一次性解决 | 必须开着浏览器和 daemon，不能纯服务器跑 |
| 接口拦截拿到结构化全量字段 | 每个平台要单独摸接口 + 时序 |
| 出错可以截图、可以人工接管，调试直观 | 速度受限于「像人一样点」的节奏 |

对电商运营这类**每天看几十页、要出报告**的场景，这个取舍很划算：
与其跟风控斗智，不如让脚本就用你本人的身份干活。
