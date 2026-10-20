# Ecommerce Portfolio

> 个人电商工具项目集 — 涵盖竞品监控、主图抓取、平台热点分析、快速分析、买家秀生成、内容抓取等方向

## 关于

本仓库收录了我在电商领域的个人工具与技能，聚焦于解决实际业务场景中的效率与自动化问题。目前已落地五个工具：竞品新品监控、京东 SKU 主图抓取、小红书热门笔记监控、得物商机推荐趋势报告、表格图片链接转图片，另有多个方向的项目在规划中。

## 项目列表

| 项目 | 方向 | 技术栈 | 简介 | 状态 |
|------|------|--------|------|------|
| [competitor-new-product-monitor](./competitor-new-product-monitor) | 竞品监控 | Python / bsk 浏览器自动化 | 用真实登录态浏览器抓取京东/天猫竞品新品，变动对比 + 瀑布流看板（**店铺清单需自备**） | 已上线 |
| [jd-sku-image-fetch](./jd-sku-image-fetch) | 主图采集 | Python / bsk 浏览器自动化 | 批量抓京东商品主图 + 标题/价格/**累计评价数/营销活动**，**按榜单批次分目录归档**，输出嵌图 Excel。**双击 setup.bat 一键装、双击 run.bat 就能跑**（[SOP](./jd-sku-image-fetch/SOP.md)） | 已上线 |
| [xhs-hot-note-monitor](./xhs-hot-note-monitor) | 热点监控 | Python / Playwright | 小红书关键词近 7 天热门笔记抓取 + 瀑布流看板 | 已上线 |
| [dewu-hot-track-report](./dewu-hot-track-report) | 热点分析 | Python / bsk 浏览器自动化 | 得物后台「高搜词」按类目抓全量热点 → 三步清洗 → 八章市场趋势报告（MD + HTML） | 已上线 |
| [image-url-to-excel](./image-url-to-excel) | 表格提效 | Python / openpyxl | 把表格里的图片链接自动转成单元格内嵌图片，支持防盗链、WebP 伪装后缀与 OSS 签名链接 | 已上线 |
| [quick-analysis](./projects/quick-analysis) | 数据分析 | Python / Pandas | 电商数据快速分析与可视化 | 规划中 |
| [buyer-show-gen](./projects/buyer-show-gen) | 内容生成 | Python / LLM API | 买家秀文案与图片自动生成 | 规划中 |
| [content-scraper](./projects/content-scraper) | 数据采集 | Python / Scrapy | 电商平台商品信息与评论抓取 | 规划中 |

## 技术亮点

> **抓取层统一是 bsk（Tencent/BrowserSkill）**：竞品监控、京东主图抓取、得物热点三个工具共用同一套思路 ——
> 复用真实登录态浏览器抹平「设备/身份」这层风控，再靠串行限速控制「采得多猛」这层。
> 这套技术栈的完整讲解（为什么不用 headless、命令、坑位、取舍）见
> **[docs/bsk-browser-automation.md](./docs/bsk-browser-automation.md)**；
> 得物热点是它在**接口拦截 + 类目多选**场景上的又一次复用。

- **竞品监控**：基于 bsk（Tencent/BrowserSkill）复用**真实登录态浏览器**，从根上绕开平台对「机器身份」的风控；覆盖京东 / 天猫，含**天猫字体加密价格破解**（canvas 字形比对反查映射）；自动对比新增/涨价/降价/下架，生成花瓣网式瀑布流看板（品牌导航 + 变动角标）。使用前需**自行提供店铺商品列表页 URL**（仓库不附带任何店铺）
- **京东 SKU 主图抓取**：同样基于 bsk 真实登录态浏览器，逐个打开京东商品详情页抓第一张**主图原图**（800×800，AVIF 自动转码）+ 标题 / 价格 / **累计评价数** / **营销活动** / 店铺。**按榜单批次隔离产出**：`runs/<榜单名>_<日期>/`，榜单名从 xlsx 文件名自动提取，同批目录复用支持断点续传，多榜单互不污染。输出 `report.csv` 与 **J 列**直接嵌入 90×90 缩略图的 Excel（点图开原图）。内置随机间隔、连续失败熔断、风控降速三层防线。**面向非技术使用者的零命令行体验**：`setup.bat` 一键安装（依赖已齐则直接复用系统 Python，不齐才建包内私有 `.venv`，绝不污染系统环境）、`doctor.py` 环境自检（仅用标准库，逐项给修复命令）、[`SOP.md`](./jd-sku-image-fetch/SOP.md) 操作手册
- **热点监控**：小红书关键词搜索 + 「最多点赞/一周内」筛选，拦截接口拿结构化数据，自动下载封面图生成瀑布流看板
- **得物商机推荐趋势报告**：同样是 bsk 真实登录态浏览器，从「查看更多类目热点」抽屉多选类目级联（勾父节点即全选子类），逐页翻并**拦截 `getHotTrackPage` 响应**——列表接口本身带全量明细，不再逐条点卡片。抓到 20 页 / 200+ 条热点后走「类目白名单 → 剔国际大牌 → 热度 > 均值」三步清洗（阈值是均值不是 top N，分布右偏所以通常只剩十几条），渲染成含执行摘要、热点对比、元素风格材质、场景人群、价格带、商品案例的**八章报告**（MD + HTML），图片本地化、清洗漏斗逐步留痕。仓库根目录 `install.ps1` 一键装
- **表格图片链接转图片**：扫描表格内所有图片 URL（含单元格里内嵌 JSON 的多个链接），并发下载后统一缩放成白底缩略图嵌入单元格。自动构造 Referer 绕防盗链，按真实内容而非扩展名解码（WebP 伪装成 `.jpg` 也能纠正）；带一条把表格拖上去就能用的 `run.bat`
- **快速分析**：支持多维度交叉分析，一键生成可视化报表
- **买家秀生成**：结合 LLM 与商品信息，自动生成自然真实的买家评价内容
- **内容抓取**：分布式爬虫架构，支持反爬策略与数据清洗

## 快速开始

```bash
git clone https://github.com/237130014/ecommerce-portfolio.git
cd ecommerce-portfolio
```

每个项目的具体运行方式请参考对应目录下的 README。

**技能类项目（目前是 `dewu-hot-track-report`）可以一键安装到 WorkBuddy**，不用手动拷目录：

```powershell
git clone https://github.com/237130014/ecommerce-portfolio.git
cd ecommerce-portfolio
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

脚本会下载仓库、把技能落到 `~/.workbuddy/skills/`、检查并补 `pandas`/`jieba` 依赖，
旧版本自动备份为 `.bak-时间戳`。只装某一个：`.\install.ps1 -Skill dewu-hot-track-report`。
装完完全退出 WorkBuddy（含托盘图标）再重开即可。

## 联系方式

- GitHub: [@237130014](https://github.com/237130014)
- Email: _（待补充）_

## License

[MIT](./LICENSE)
