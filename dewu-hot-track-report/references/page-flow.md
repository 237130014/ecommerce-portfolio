# 页面操作细节与踩过的坑

目标页：`https://stark.dewu.com/main/businessApp/opportunity?tabId=suggestion`
（得物商情 › 商机推荐 › 高搜词）

## 1. 正确的筛选入口

页面上有**两个**类目筛选器，效果完全不同：

| 入口 | 位置 | 单选/多选 | 结论 |
|---|---|---|---|
| 「常用筛选」类目级联 | 页面列表上方 | 单选 | ❌ 不要用，选不出「一个一级类目下挑 7 个二级」 |
| **「查看更多类目热点」→ 右侧抽屉 → 类目级联** | 页面右上角文字按钮 | **多选（带 checkbox）** | ✅ 用这个 |

抽屉里的多选级联行为：

- 勾**父节点** = 全选其下所有子类（会折叠成一个 chip，很干净）
- 勾**子节点** = 只选中该子类
- 悬停父节点 = 展开下一级（**不选中**）

## 2. 主要坑位

**坑 1：直接点一级节点会把整个一级类目勾上。**
想「在 流行饰品/眼镜/服配 下只勾 7 个二级」，必须先 `hover` 第 0 级节点展开，
再点第 1 级节点的 checkbox。直接 `click` 第 0 级 = 选中整个一级类目（95 条 → 变成 300+ 条）。

**坑 2：合成事件无效。**
`element.click()` / `dispatchEvent(new MouseEvent('click'))` 对 antd 的 Cascader 无效——
DOM 上看起来点了，但选中值不变。**必须用真实鼠标事件**（`bsk click --selector`）。
`mouseover` 合成事件对「展开」是可用的，但仍建议统一走真实 `bsk hover`。

**坑 3：哈希类名不可靠。**
`seeAll___Bznma`、`cardGrid___xxx` 这类带哈希的类名会随前端发版变化。
本技能一律用 `[class*=cardGrid]`、`[class*=cardTitle]` 这类**部分匹配**，或按文案定位。

**坑 4：关闭详情抽屉会误关外层。**
抽屉是叠加的（外层=热点列表，内层=单条详情）。`.ant-drawer-close` 会命中第一个，
把外层列表抽屉关掉，之前抓的状态全部丢失。
正确做法：先按内容特征（`[class*=trackDescriptionWrapper]`）找到**详情**那一层，再取它内部的关闭按钮。

**坑 5：第 1 页的响应不会自己出现。**
打开抽屉/应用筛选时的第一个请求发生在 hook 注入之前，或已被计入 `base`。
所以捕获流程是：**先向前翻到底，再退回第 1 页**，每个请求都会重发一次。
`scrape.py` 的 `capture_pages()` 就是按这个顺序实现的。

**坑 6：翻页必须等接口回来再翻。**
固定 `sleep` 会拿到半截数据或空页。要轮询 `window.__cap` 长度增长 + `reqBody.pageNum`
来确认「这一页真的回来了」。

**坑 7：刷新页面 = hook 失效。**
`window.__cap` 挂在页面上下文，任何 reload / 跳转都会丢。刷新后必须重新注入。

## 3. bsk 关键命令

```bash
bsk doctor                                   # 环境自检
bsk browsers                                 # 已连接的浏览器
bsk session start --json --no-focus --name <名字>
bsk tab list --session <名字> --json          # 找目标标签页 tab_id
bsk tab borrow <tab_id> --session <名字> --json --timeout 90s   # 接管（可能需人工确认）
bsk evaluate "<js>" --json                   # 返回值在 .value
bsk click --selector "#id"                   # 真实鼠标点击
bsk hover --selector "#id"                   # 真实悬停
bsk press Escape                             # 收起下拉
bsk screenshot --out <path>
```

借标签页会让浏览器弹出一个「Agent 窗口」，页面从用户窗口移过去，**用户会看到窗口切换**，
所以每次接管后要主动告知，结束后按需归还。

## 4. O: 盘读取受限（团队 SKILL 库）

若技能库放在 `O:` 等网络盘，脚本进程（python / powershell）读该盘会 `Permission denied`，
只有编辑器的 Read 通道能读。

处理方式：用 Read 读出脚本内容 → 原样落到本地目录 → 在本地跑。**不要修改原技能。**

另外原技能的 `build_report.py` 里 `data_base()` 用 `parents[5]` 定位数据目录，
在不同目录深度下会解析失败，必须显式传 `--week-dir`。本技能已改为全部显式传参。
