# 字段口径与接口映射

## 1. 接口

| 项 | 值 |
|---|---|
| 列表接口 | `/api/.../getHotTrackPage`（请求体含 `pageNum`、`pageSize`） |
| 触发时机 | 抽屉打开 / 翻页 / 修改类目筛选 |
| 单页条数 | 12 |
| 单条大小 | 约 4.9 KB（含明细，无需再点卡片） |
| 拦截位置 | 页面内 hook `window.fetch` 与 `XMLHttpRequest`，关键词 `chanceRecommend|hotTrack|HotTrack|opportunity` |

响应结构：`resp.data.contents[]`，每项即一条热点。

## 2. 16 列标准字段（下游 analysis.py 依赖这些列名）

| 列名 | 来源字段 | 说明 |
|---|---|---|
| 抓取日期 | 运行参数 | `YYYY-MM-DD` |
| 类目组 | 类目组 config 的 label | 如 `流行饰品/眼镜/服配` |
| 页码 | 请求体 `pageNum` | |
| 页内序号 | 循环索引 | 从 1 开始 |
| 热点标题 | `trackName` | |
| 热点图链接 | `bannerImg` | 报告里会下载到 `assets/` |
| 商品信息 | `trackDescNew.commodityInfo` | **JSON 字符串**（元素/风格/材质的来源） |
| 卖点分析 | `trackDescNew.sellingPoint` | 整段文案，非标签 |
| 适用人群 | `trackDescNew.suitableCrowd` | 整段文案，非标签 |
| 适用场景 | `trackDescNew.suitableScene` | 整段文案，非标签 |
| 成交热度（近30天） | `transactionHeat` | 纯数字指数 |
| 搜索热度（近30天） | `searchHeat` | 纯数字指数 |
| 机会类目 | `categoryNameList` | 空格拼接 |
| 机会价格 | `chancePriceSegment` | 空格拼接，形如 `¥116-3825` |
| 相似机会品 | `spuList[]` | **JSON 字符串**：`[{商品标题, 平台最低价, 主图链接}]` |
| 副标题 | `recommendReason` | |

## 3. 附加字段（本技能追加，供交叉核对）

| 列名 | 来源字段 | 说明 |
|---|---|---|
| 社区热度（近30天） | `communityHeat` | |
| 搜索环比 | `searchHeatQoq` | **单位 0.01%**，见下 |
| 成交环比 | `transactionHeatQoq` | 同上 |
| 搜索连涨周数 | `searchHeatGrowthWeeks` | 0 表示无信号 |
| 热门搜索 | `hotSearchList` | 空格拼接 |
| 组内排名 | `rankNum` | |
| 主图链接 | `headImg` | 方形主图，与 bannerImg 不同 |
| trackId | `trackId` | 去重键 |

## 4. 两个必须注意的量纲

**热度是绝对指数，不是带单位的文本。**

`searchHeat = 6650811` 表示 665 万，页面显示为「665万」。CSV 里存的是**裸数字**，`analysis.parse_heat()`
兼容 `6650811` 与 `"665万"` 两种写法，但**不要**自己再乘 10000。

**环比整数是 0.01% 单位。**

`searchHeatQoq = 2187` → **+21.87%**；`397` → +3.97%。实测取值区间 72 ~ 30000
（即 +0.72% ~ +300%），中位数 1540（+15.4%），量级与「周环比增长速度」吻合。
若按绝对增量理解，会出现「搜索热度 319 却增长 11169」的矛盾，故确认为百分比口径。
`build_report.patch_growth()` 里 `/100` 的处理即基于此。

## 5. 字段缺失情况（写报告时必须如实说明）

| 字段 | 覆盖率 | 影响 |
|---|---|---|
| `commodityInfo`（商品画像） | 约 47% | 「四、元素/风格/材质」章节偏薄，**点开卡片不会补回来**（已验证不触发新接口） |
| `suitableScene` / `suitableCrowd` | 较高但为整段描述 | 「五、场景/人群」计数粒度粗（同值多为 1） |
| `chancePriceSegment` | 约 72% | 价格带分布有缺口 |
| `spuList` | 约 45% | 相似机会品库规模受限 |
| `searchHeatQoq` | 约 42% | 增长趋势只能覆盖这部分 |

这些是**平台返回缺字段**，不是抓取遗漏。报告「八、数据口径」需写明，不要粉饰成完整数据。

## 6. 类目白名单

`domain_dict.py` 内置 50 条类目白名单（黄金/珠宝/翡翠/玉石/饰品两套）与 30 个国际大牌中英文别名。
清洗时**命中白名单即保留**，未命中直接剔除。若本次抓取的类目不在白名单内，
需先往 `CATEGORY_WHITELIST_GOLD` / `CATEGORY_WHITELIST_FASHION` 里补充，否则会被误删。
