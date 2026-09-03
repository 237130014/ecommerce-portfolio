# 竞品新品监控技能（competitor-new-product-monitor）

电商竞品监控能力：抓取京东/天猫竞品店铺「新品」排序商品 → 图片原图化 → 与上一轮对比（新增/涨价/降价/下架）→ 生成花瓣网式瀑布流看板。

## 目录结构

```
competitor-new-product-monitor/
├── SKILL.md                 # 技能工作流说明（触发方式、抓取步骤、踩坑经验）
├── references/
│   └── stores.json          # 【个人配置，未随仓库提交】店铺清单（平台+店名+列表页URL）
└── scripts/
    ├── fix_images.py        # 图片处理：京东 n7→n0、天猫 alicdn 尺寸后缀转原图、下载、去重、CSV
    ├── compare_new.py       # 变动对比：prev/ 与当前数据，输出新增/下架/涨价/降价
    └── gen_dashboard.py     # 瀑布流看板生成（HTML，本地图片嵌入）
```

## 使用说明

- 店铺清单 `references/stores.json` 为个人监控配置（按仓库规则不提交），使用时按以下格式自建：

```json
{
  "stores": [
    {"no": 1, "platform": "jd", "name": "店铺名", "url": "https://mall.jd.com/view_search-xxx.html"},
    {"no": 14, "platform": "tmall", "name": "店铺名", "url": "https://xxx.tmall.com/category.htm"}
  ]
}
```

- 数据目录约定：`jd_new_{序号}_{店名}.json` 存于数据目录（如 `jd-baseline/`）；`data/prev/` 存上一轮用于对比
- 脚本均支持 `BASE` 参数指定数据目录：`python fix_images.py <数据目录>`

## 要点备忘（详见 SKILL.md）

- 京东「新品」排序：店铺页点击排序栏"新品"，或 URL 第 5 段 `0→1`（`-0-1-0-0-`）
- 京东图片 n7 为缩略图，替换 `n0` 为原图；天猫 alicdn 图片去掉尺寸后缀（如 `_60x60.jpg`）为原图
- 天猫分类页需浏览器登录态；经典模板价格在 HTML 注释 `<!-- item.discntPrice: xxx -->`；React 模板（部分店）价格加密不可取
- 风控提示：保持手动低频触发、串行抓取、随机延迟；不要高频自动定时抓取
