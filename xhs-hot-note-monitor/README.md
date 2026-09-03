# 小红书热门笔记抓取（xhs-hot-note-monitor）

通过指定关键词搜索小红书笔记，筛选「近 7 天 + 最多点赞」的热门笔记，抓取标题 / 正文 / 封面图 / 链接，汇总成 CSV 表格，并生成瀑布流 Web 看板。

## 功能

- **关键词搜索**：支持多关键词批量抓取
- **精准筛选**：排序「最多点赞」+ 发布时间「一周内」
- **字段抓取**：标题、正文摘要、封面图、链接、点赞、收藏、评论、作者、发布时间
- **封面图下载**：浏览器原生抓图（goto https 图片 URL + 元素截图，绕开 CDN http 代理超时）
- **汇总表格**：`热门笔记明细.csv`
- **Web 看板**：瀑布流卡片 + 关键词筛选 + 标题搜索 + 点击放大 + 下载 CSV

## 环境

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m playwright install chromium
```

## 使用

```bash
# 配置关键词（references/keywords.json）
# 一键执行（首次会弹窗扫码登录，登录态自动保存复用）
python run.py

# 或命令行指定关键词
python run.py 黄金项链 银饰耳环

# 已登录后可用无头模式（不弹窗、无打扰）
python run.py --headless 黄金项链

# 分步执行
python scripts/login.py                              # 只扫码登录
python scripts/search.py 黄金项链                    # 只搜索
python scripts/fix_images.py                         # 只下载图片
python scripts/gen_dashboard.py                      # 只生成看板
```

## 目录结构

```
xhs-hot-note-monitor/
├── run.py                  # 一键执行入口
├── references/
│   └── keywords.json       # 关键词清单
├── scripts/
│   ├── login.py            # 扫码登录 + Cookie 持久化
│   ├── search.py           # 搜索 + 筛选 + 提取
│   ├── fix_images.py       # 封面图下载
│   └── gen_dashboard.py    # CSV + 看板
└── xhs-baseline/           # 数据目录（图片 / JSON / CSV / 看板）
```

## 注意事项

- 登录态存于 `.browser_profile/`，请勿提交或分享（含 Cookie）
- 小红书封面图签名 URL 时效短，搜索后应尽快下载
- 保持手动低频触发、串行抓取，避免触发风控
- 仅供个人学习研究，遵守平台使用条款
