---
name: xhs-hot-note-monitor
description: 小红书近期热门笔记抓取与 Web 看板生成。当用户提到"小红书热门笔记/小红书爆款/小红书热点/抓小红书笔记/笔记数据看板/小红书选题/小红书趋势"等意图时使用，尤其是电商/内容运营者需要盯某品类近期（近 7 天）最多点赞的笔记，提取标题、正文摘要、封面图、链接做选品或选题分析时。流程：扫码登录（持久化）→ 关键词搜索 → 筛选「最多点赞 + 一周内」→ 拦截搜索接口拿结构化数据 → 浏览器原生抓封面图 → 生成瀑布流看板 HTML 和明细 CSV。即使只有"帮我抓一下小红书某词最近的热门笔记"这类简短指令也应触发。
---

# 小红书热门笔记监控

把"盯小红书某关键词近期爆款"变成一条流水线：每次运行产出 (1) 近 7 天最多点赞的笔记明细、(2) 本地封面图、(3) 瀑布流 Web 看板。服务对象是电商/内容运营者，用于选品、选题、竞品内容拆解。

## 输入与目录约定

- 数据目录 `BASE`：默认 `xhs-baseline/`（脚本接受命令行参数覆盖）
- `references/keywords.json`：关键词清单（`{"keywords": ["黄金项链", ...]}`）
- `BASE/notes_{关键词}.json`：每关键词一份抓取数据（keyword/sort/publish_time/fetched_at/count/items[]）
- `BASE/images/{关键词}_{note_id前10位}.jpg`：本地封面图
- `BASE/热门笔记明细.csv`、`BASE/小红书热门笔记-{日期}.html`：交付物
- `.browser_profile/`：登录态持久化目录（含 Cookie，**绝不提交**）

## 工作流

### Step 1 登录（持久化，只首次扫码）
运行 `python scripts/login.py`（有头模式），或直接跑 `run.py` 自动触发。
- 登录弹窗会自动弹出，二维码是 `img.qrcode-img` 的 **base64 data URI**（不是外链图片），脚本会把它落盘成 `login_qr.png` 供扫描，每 2 秒刷新
- 登录成功后 Cookie 存到 `.browser_profile/`，之后 `run.py --headless` 复用登录态、无打扰跑
- **登录态判断用 `.login-btn` 是否存在**：未登录时页面有登录入口，登录后消失。不要用 `web_session` cookie（匿名态也会下发）或 `user.loggedIn`（Vue 响应式对象，读不到）

### Step 2 搜索 + 筛选（API 拦截，不用 DOM 抓）
运行：`python run.py [关键词...]`（不带参数则读 keywords.json）
- 数据源：拦截 `https://so.xiaohongshu.com/api/sns/web/v2/search/notes` 的 **POST 响应**，直接解析结构化 JSON（比 DOM 抓更抗页面改版）
- 卡片字段在 `note_card`：`display_title`（标题）、`cover.url_default`（封面）、`interact_info`（点赞/收藏/评论）、`user.nickname`（作者）、`corner_tag_info` 里 `type=publish_time`（发布时间）、`id`+`xsec_token`（拼接详情链接）
- **筛选「最多点赞 + 一周内」**：hover 搜索页「筛选」字样弹出面板，点击对应选项。参数语义：`sort_type=popularity_descending`（最多点赞）、`filter_note_time=一周内`
- **筛选面板是 hover 触发，不是 click**；每个选项 tag 有重复 DOM——隐藏热力层（`aria-hidden="true"` + `opacity:1e-05`）和真实可点层（`div.tags`）。必须用 JS 遍历 `div.filter-panel span`、向上找 `.tags`、排除 `aria-hidden=true` 后 `.click()`。**不要用 Playwright `is_visible()`**（`opacity:1e-05` 仍判可见且每判一次卡 5 秒）
- **过滤脏数据**：搜索 API 会混入推广位卡片（note_id 含 `#`、title/cover 空），必须过滤——`"#" in nid` 或 title/cover 为空都跳过

### Step 3 封面图（浏览器原生抓图，绕 403）
- **根因不是防盗链**：小红书封面 CDN 是 `http://` 链接，在开代理的机器上 `urllib`/`context.request` 都会 `connect ETIMEDOUT`（代理 fake-ip 段 198.18.0.x 拦截 http）
- **解法**：URL 转 `https://` + `page.goto` 图片 URL + 对 `<img>` 元素 `screenshot()`，走浏览器原生网络栈（和搜索页里 `<img>` 正常显示同一套机制），稳定 600×800
- 在搜索页还开着时立即抓图（`download_images` 复用搜索用的同一个 page），避免 CDN 签名 URL 过期
- **顺序坑**：必须先抓图、再 `save_items` 保存 JSON，否则 JSON 丢 `local_image` 字段（抓图写的是内存对象，不会回写已落盘的 JSON）

### Step 4 生成看板
运行 `python scripts/gen_dashboard.py`（run.py 末尾自动调用）
- 合并所有 `notes_*.json` → 按点赞数降序 → 输出 `热门笔记明细.csv` + 瀑布流 HTML 看板
- 看板含：关键词筛选 chips、标题/作者搜索、瀑布流卡片（Top3 徽章）、点击放大（lightbox 显示正文摘要 + 点赞/收藏/评论 + 打开原文）、统计条、下载 CSV

### Step 5 交付
- `present_files`：看板 HTML（主交付）+ 明细 CSV
- 告诉用户：各关键词条数、全站点赞 Top、封面图是否齐全、下次如何触发（"抓一下小红书 XX 词最近热门笔记"）

## 关键经验（踩坑记录）

1. **登录二维码**：是 `img.qrcode-img` 的 base64 data URI，不是外链；落盘成 PNG 比让用户盯浏览器窗口更稳
2. **登录态判断**：只信 `.login-btn` 消失与否；`web_session` cookie 匿名态也下发、`user.loggedIn` 读不到，都不能当依据
3. **搜索页导航**：直接 `goto` 搜索 URL 可能 `net::ERR_ABORTED`；先开首页再导航，`wait_until="commit"` 而非 `domcontentloaded`
4. **筛选面板 hover**：`page.locator("text=筛选").hover()` 弹出，再用 JS 点选项；`text=最多点赞` 会误匹配隐藏热力层导致点击超时
5. **封面图 http→https**：只需改协议，别删 `!` 尺寸后缀（保留 webp 中等尺寸，看板够用）；删后缀会拿原图（几 MB，加载慢）
6. **脏数据**：note_id 形如 `uuid#数字` 的是推广位卡片，过滤 `#` 即可
7. **时序**：`save_items` 必须在 `download_images` 之后
8. **headless 复用登录态**：登录过的 `.browser_profile` 在 headless 下也能识别已登录，可全程无弹窗

## 输出格式（固定模板）

- CSV 列：rank, keyword, title, desc, liked_count, collected_count, comment_count, author, publish_time, cover, local_image, url
- 看板卡片 = 封面图 + TOP 徽章 + 标题 + 作者 + 点赞数，点击放大看全文摘要与原文链接
- 笔记链接：`https://www.xiaohongshu.com/explore/{id}?xsec_token={token}&xsec_source=pc_search`
