---
name: 京东SKU主图抓取
description: 批量抓取京东商品主图与关键指标。当用户提到"抓京东主图/京东SKU主图/批量下载京东图片/京东商品图抓取/榜单主图/按SKU抓图/京东主图表格/抓累计评价数/抓营销活动"等意图时使用；当用户说"安装这个技能/装一下/怎么用/第一次用/跑不起来/报错了/环境检查/依赖没装"时同样使用本技能——它自带一键安装脚本与环境自检，能带用户从零装到跑通，不需要用户懂命令行。典型场景：电商运营把一份京东榜单（xlsx/csv，含 200 个 SKU）的前 50 名商品主图批量抓下来、按榜单分批次归档、导出带嵌入缩略图的 Excel。流程：bsk（BrowserSkill，真实登录态浏览器）逐个打开京东商品详情页 → 抓第一张主图原图 + 标题 + 价格 + 累计评价数 + 营销活动 + 店铺 → 按「榜单名_日期」分目录存图 → 合并输出 report.csv 与嵌图 xlsx。即使用户只说"跑一下主图抓取"也应触发。
---

# 京东SKU主图抓取

> **当前版本：2.0**（2026-09-30）—— 相比 1.0 新增「累计评价数」与「营销活动」两个字段，
> 导出 Excel 的缩略图列由 H 移到 J。

给一批京东 SKU，逐个打开商品详情页，抓**第一张主图原图**（800×800 起），
附带标题、价格、**累计评价数**、**营销活动**、店铺，产出**按榜单批次隔离**的图片目录 + 报告表格。

---

# 第一部分：AI 执行手册（拿到本技能先读这里）

> **目标：用户只说一句话，你负责把它跑通。**
> 用户不需要知道 Python、pip、bsk、daemon 这些词。凡是能用命令解决的事你自己做，
> 只有**必须人工**的两件事才让用户动手（见下方 ⚠️）。

## 目录布局

本技能有两种落盘布局，脚本内部都能自动识别，你不用手动区分：

```
源码布局（开发时）              技能包布局（安装后）
jd-sku-image-fetch/            ~/.workbuddy/skills/jd-sku-image-fetch/
  fetch_main_images.py           SKILL.md  README.md  SOP.md
  export_images_xlsx.py          doctor.py  setup.bat  run.bat
  ...                            scripts/fetch_main_images.py
                                 scripts/export_images_xlsx.py ...
```

- **所有 Python 脚本都在 `scripts/` 下**（技能包布局）；`run.bat` / `setup.bat` / `doctor.py` 在包根。
- 脚本自带 `default_base()`：脚本在 `scripts/` 下时，BASE 自动取**包根目录**。
  所以抓取数据默认落在技能包根目录的 `runs/` 里，与 `run.bat` 的行为一致。
- 你也可以显式指定 BASE（推荐，数据更整洁）：把 BASE 传成用户的**工作目录**。

## 第一步：环境自检（永远先做这一步）

```bash
# 技能包布局
python "<SKILL_DIR>/doctor.py"

# 想要机器可读的结果（推荐，便于你判断该修哪项）
python "<SKILL_DIR>/doctor.py" --json
```

`doctor.py` **只用标准库**，任何 Python 3.8+ 都能跑起来 —— 哪怕 openpyxl/Pillow 一个都没装。
它会逐项报告：Python 版本、openpyxl、Pillow、bsk CLI、bsk 守护进程、浏览器扩展、
skus.csv、数据目录可写性，并给出每项的修复命令。退出码 0 = 可用，1 = 有阻断项。

> 找不到 Python 时，直接让用户双击 `setup.bat`（见下），不要让他手敲命令。

## 第二步：按自检结果修

| 自检结果 | 你要做的 |
|---|---|
| 缺 openpyxl / Pillow | 让用户**双击 `setup.bat`**。它会自动找 Python、按需创建包内私有 `.venv` 并装依赖，**不污染系统环境**。也可以你自己跑：`"<SKILL_DIR>/setup.bat"` |
| 没有 Python | 让用户去 python.org 装 3.10+，安装首屏**务必勾选 "Add python.exe to PATH"**，装完再双击 `setup.bat` |
| 缺 bsk CLI | 给出**一行**安装命令（见下方「前置条件」），装完重开终端 |
| bsk 守护进程未运行 | 让用户双击 `start-bsk-daemon.bat`，**窗口保持不关** |
| 浏览器扩展未连接 ⚠️ | **必须人工**：让用户打开 Chrome/Edge，确认 BrowserSkill 扩展已启用 |
| 未登录京东 ⚠️ | **必须人工**：让用户在 bsk 连着的浏览器里手动登录一次 jd.com |

⚠️ **只有两件事必须用户亲手做**：装浏览器扩展、登录京东。
其余（装依赖、建目录、跑脚本、导表格）你都应该自己执行。**绝不代填账号密码验证码。**

## 第三步：拿到榜单，开跑

用户通常会给你一份**京东导出的榜单 xlsx**（200 个 SKU），或让你从 `skus.csv` 抓。

```bash
# 推荐：把 BASE 指定成用户的工作目录，数据不跟技能包混在一起
python "<SKILL_DIR>/scripts/fetch_main_images.py" "<WORKDIR>" \
       --from-xlsx "<榜单.xlsx>" --top 50 --limit 25
```

- `--top 50`：只看榜单**前 50 名**，后面的不考虑（默认就是 50）
- `--limit 25`：本次只抓 25 个（防风控，见下方「实测节奏」）
- 跑完会**自动导出**同名嵌图 xlsx，一般不用手动再导

跑完用 `fetch_stats.py` 看进度（支持 `--all` 列全部批次）：
```bash
python "<SKILL_DIR>/scripts/fetch_stats.py" "<WORKDIR>"
```

**最后一定要把导出的 `<批次名>.xlsx` 用 present_files 给用户看**，并说明：
批次目录在哪、成功多少条、两个新字段（累计评价数 / 营销活动）取值示例。

## 常见追问怎么答

- **"怎么一次多抓点？"** → 别超 30。见下方「实测节奏」，34 个/5 分钟就是风控阈值。
- **"某个 SKU 没抓到"** → 重跑一次即可，已完成的会自动跳过，只补失败的那几个。
- **"表格里图片点开是缩略图？"** → 点图会打开 800×800 原图，画质不受缩略图影响。
- **"列怎么变了？"** → v2.0 起缩略图列由 H 移到 J（新增了两列在 price 之后）。

---

# 第二部分：原理与参考

## 前置条件（首次使用需逐项确认）

1. **bsk CLI**：`bsk --version` 能输出版本即可；失败则安装：
   - Windows：`irm https://raw.githubusercontent.com/Tencent/BrowserSkill/main/install.ps1 | iex`
   - macOS/Linux：`curl -fsSL https://raw.githubusercontent.com/Tencent/BrowserSkill/main/install.sh | sh`
   - 可选：`bsk install-skill` 把浏览器技能注册进本地 agent 环境
2. **浏览器扩展**：Chrome / Edge 安装 BrowserSkill 扩展并完成连接（**必须人工**）
3. **常驻守护进程**：双击 `start-bsk-daemon.bat`（或 `bsk daemon start --port 53899`），**窗口保持不关**
4. **登录态**：在 bsk 连着的那个浏览器里**手动登录一次京东**，长期有效（**必须人工**）
5. **Python 环境**：`openpyxl` + `Pillow`（Pillow 需 ≥ 11 才认 AVIF）—— 交给 `setup.bat`

用 `doctor.py` 或 `bsk doctor` 自检；出现 fail 行按提示处理后再继续。

## 为什么必须用 bsk，不能用 Playwright

实测（2026-09-29）：

| 方案 | 结果 |
|---|---|
| Playwright 新开浏览器（含反检测注入） | 扫码登录成功，但访问商品页仍被频控 `pc-frequent-pro.pf.jd.com?reason=403` |
| **bsk 驱动日常真实 Chrome** | **正常** |

原因是"身份"：Playwright 是陌生设备 + 新账号 + 机器指纹；bsk 复用了真实浏览器的
指纹、已登录账号、本地 IP。

## 目录约定（核心：榜单批次隔离）

> 每次抓的榜单不同，**图片和表格绝不能混在一起**。所有产出按批次分目录。

```
<BASE>/                                  ← 数据根目录，默认当前工作目录
  runs/
    <榜单名>_<YYYYMMDD>/                  ← 一个榜单一批，同名复用（支持续抓）
      images/<sku>.jpg                   ← 本批图片，只放本批
      <榜单名>_<YYYYMMDD>.xlsx           ← 嵌图表格，与批次目录同名
      report.csv                         ← 本批报告（累计合并，不丢历史）
      state.json                         ← 断点续传状态（含本批 SKU 全集与来源）
      logs/                              ← 运行日志 + 调试截图
      .thumbs/                           ← 缩略图缓存（可随时删）
```

### 榜单名怎么来的

从 xlsx / csv **文件名自动提取**，自动剔除：
日期片段（`2026-09-27` / `202607-202609` / 独立四位年份）、格式噪音词
（`离线`/`汇总下载`/`导出`/`数据`/`报表`/`跨天不去重`/`唯一` 等）、
Excel 临时前缀（`~$`）、文件名尾部随机串（`_a1b2c3d4`）。

例：`商品明细-条码粒度_唯一某店_跨天不去重_202607-202609_202609271022.xlsx`
→ 批次目录 `商品明细-条码粒度_某店_20260929`

### 批次目录怎么定位（用户视角）

不用手记路径，所有脚本共用同一条规则 `resolve_run_dir()`：

| 场景 | 行为 |
|---|---|
| 不传 `--run` | 自动取 `runs/` 下 **最新修改** 的批次 |
| `--run <名字>` | 指定某个批次 |
| `--run <绝对路径>` | 直接用该目录 |
| 同名日期再抓 | **复用**同一批次目录 → 续抓，不合并不重复 |

## 用法

**给非技术用户**：双击 `setup.bat`（首次一次性）→ 双击 `run.bat`（日常）。

双击 `run.bat`（Windows 菜单）：
```
1. Fetch from skus.csv  (asks how many)   ← 日常入口，先问抓几个
2. Fetch from xlsx      (drag file)       ← 拖榜单文件
3. Check bsk daemon status
4. Show progress / stats                   ← 看进度、还剩多少
5. Force refetch ALL
6. Export embedded-image xlsx              ← 导出嵌图表格
7. Fix report.csv (体检/修复)              ← URL 缺失、失败行被覆盖
8. Run self-test (what is missing?)        ← 环境自检
9. Exit
```

`run.bat` 也支持**非交互调用**（给 AI / 脚本用，执行完直接退出，不弹菜单、不等待）：
```bash
run.bat 4          # 等于菜单里选 4
run.bat stats      # 命名入口：stats / doctor / export / repair / bsk
```

命令行：
```bash
# 从 skus.csv 抓（默认只看榜单前 50 名，自动跳过已完成）
python fetch_main_images.py . --top 50 --limit 25

# 直接拖榜单 xlsx，同样只看前 50 名
python fetch_main_images.py . --from-xlsx "榜单.xlsx" --top 50 --limit 25

# 自定义批次目录名
python fetch_main_images.py . --from-xlsx "榜单.xlsx" --run-name "618大促_某店_20260601"

# 环境自检（首次/排障先跑这个）
python doctor.py
python doctor.py --json

# 看进度 / 看所有批次概览
python fetch_stats.py
python fetch_stats.py --all

# 导出嵌图表格（抓完自动执行，一般不用手动跑）
python export_images_xlsx.py .                 # 最新批次
python export_images_xlsx.py . --all-runs      # 所有批次

# 体检/修复 report.csv
python fix_report_urls.py .            # 只体检
python fix_report_urls.py . --apply    # 确认后写回
```

### 两个关键参数

| 参数 | 含义 | 默认 |
|---|---|---|
| `--top N` | **只看榜单前 N 名**，后面的一律不考虑 | **50** |
| `--limit N` | **本次抓几个**（0 = 有多少抓多少） | 0 |

榜单表每份 200 个 SKU，**默认只取前 50 名**（排名最靠前的），后 150 个不抓。
`run.bat` 里选 1 之后会直接问你「本次抓几个」。

## 管理 SKU（增删改）

复制 `skus.example.csv` 为 `skus.csv`，三列（`setup.bat` 会自动帮你建一份）：

```csv
sku,remark,enabled
100312606664,竞品A金款,1
10098765432,竞品A银款,0
```

- **增加**：加一行
- **删减**：删行，或把 `enabled` 改成 `0`（保留历史，不抓取）
- **修改**：直接改

也可以用 `--from-xlsx` 直接喂京东导出的榜单表，无需转成 csv。
抓取进度独立存在 `state.json`，改 SKU 清单不会打乱已完成记录 —— 这就是断点续传。

## 防风控设计

| 层 | 措施 |
|---|---|
| 身份 | bsk 复用真实 Chrome + 已登录账号 + 本地 IP |
| 节奏 | SKU 间隔随机 **3~8 秒**（`--delay 3-8`），串行不并发 |
| 批量 | 每批默认 **≤50**，批间建议间隔 10 分钟以上 |
| 熔断 | 连续 **3 次** 风控/失败即停止并报告（`--max-fail 3`），不硬闯 |
| 降速 | 本轮命中 2 次风控后，延迟自动翻倍（2.5×）继续 |
| 续传 | 已完成的不重抓，被中断后重跑接着来 |

### 实测节奏（2026-09-29，重要）

一次跑到 **第 34 个**时开始被风控（`reason=403`），说明**约 34 个 / 5 分钟是当前触发阈值**。

**推荐打法**：
- **每批 25~30 个**，别贴着 50 跑
- 批间**至少间隔 10~15 分钟**
- 一天总量控制在 **100~150 个**以内
- 被风控后**别立刻重跑**，等 15~30 分钟冷却

```bash
python fetch_main_images.py . --limit 25 --delay 5-12
# 等 15 分钟后
python fetch_main_images.py . --limit 25 --delay 5-12
```

## 产出说明

### report.csv 字段

`sku / status / 标题 / 价格 / 累计评价数 / 营销活动 / 店铺 / 主图数 / 本地图片名 / 图片URL / 备注 / 抓取时间`

**v2.0 新增两个字段**（放在「价格」之后）：

| 字段 | 说明 |
|---|---|
| `comment_count` | **累计评价数**，如 `2万+`。取页面展示值，非精确条数 |
| `promo` | **营销活动**，如 `已享受：单品立减60元 可再享：最高返26京豆` |

| status | 含义 |
|---|---|
| `ok` | 成功 |
| `risk` | 命中风控页 |
| `no_image` | 页面正常但没取到主图 |
| `nav_error` | 导航超时/异常 |
| `extract_error` | 页面提取失败 |
| `img_download_failed` | 提取成功但图片下载失败 |

> 重抓时若失败，**不会覆盖**该 SKU 已有的成功记录（避免一次风控抹掉成果）。
> 想彻底重来用 `--force`。

> `state.json` 除 `done` / `failed` 外，还记录 `skus_all`（本批 SKU 全集）与 `source`（清单来源）。
> 这是给 `fetch_stats.py` 对账用的：拖 xlsx 跑的批次，其清单跟 `BASE/skus.csv` 是两份不同的东西，
> 没有这个字段统计就会显示"已完成 0"。

### 嵌图 xlsx（与批次同名，抓完自动生成）

把 `report.csv` 转成 Excel，**J 列直接嵌入 90×90 缩略图**，不用对着 URL 猜图。

| 列 | 内容 |
|---|---|
| A–I | SKU / 状态 / 标题 / 价格 / 累计评价数 / 营销活动 / 店铺 / 图数 / 本地图片名 |
| **J** | **主图缩略图（90×90）** |
| K–M | 商品链接 / 备注 / 抓取时间 |

> ⚠️ v2.0 起新增「累计评价数」「营销活动」两列，**缩略图列由 H 顺移到 J**。
> 如果你有基于旧列号（H）的表格公式或脚本，升级后需要同步改。

**点图看原图**：缩略图挂了超链接，点一下用浏览器打开 800×800 原图（画质不受缩略图影响）。
个别 SKU 的 CDN 地址丢失时，自动改为打开本地 `images/` 里的原图文件。

```bash
python export_images_xlsx.py . --size 140 --quality 92   # 换大图/更高清
python export_images_xlsx.py . --keep-url               # 额外保留一列 URL 文本
python fetch_main_images.py . --no-xlsx                 # 跑完不自动导出
```

## 页面选择器（2026-09-30 实测）

| 字段 | 选择器 |
|---|---|
| 第一主图 | `.image-carousel-track .item:first-child img.image` |
| 原图 | 把 URL 里 `/s<W>x<H>_` 前缀去掉 |
| 标题 | `document.title` 去掉尾部「【行情 报价 价格 评测】-京东」 |
| 价格 | `.product-price` |
| **累计评价数** | `.product-price-panel--options-comment`（首屏稳定）→ 兜底 `#comment-title` |
| **营销活动** | `.page-right-discount`（价格下方「已享受 / 可再享」区域） |
| 店铺 | `.top-name-tag` |

京东详情页会改版，选择器失效时**直接现场问页面**（bsk 会话里查 DOM，无需额外脚本）：

```bash
bsk session start                      # 记下返回的 session id
bsk navigate "https://item.jd.com/<sku>.html" --session <id> --wait-until load
bsk evaluate --session <id> "document.querySelector('.product-price-panel--options-comment')?.innerText"
bsk session stop <id>
```

查到的新选择器回填到上表，并同步改 `fetch_main_images.py` 里的 `EXTRACT_JS`。

## 工程踩坑（改代码前必读）

1. **京东导出的榜单 xlsx 把 `<dimension ref="A1"/>` 写坏**，openpyxl 只读到 A 列。
   脚本已改为直接解析 `sheet1.xml` 原始 XML，不依赖 dimension。
2. **bsk 默认端口 52800 被 VPN 占用** → daemon 启动即死且无报错。已改用 53899。
3. **图片是 AVIF 编码**（`xxx.jpg.avif`）。扩展名按主格式保留，Pillow ≥ 11 可直接读。
   判断 AVIF 支持**不能**用 `features.check_feature('avif')`（会抛异常）。
4. **图片走 CDN，下载不需要登录态**，但抓页面需要。
5. **字段里的裸换行会让 Excel 行错位**。京东店铺名形如
   `知芝好物严选小店\n3.0`（店名+评分），写进 CSV 后 Excel 把一行拆成两行。
   已在 JS 和 Python 两侧把 `\r\n\t` 和连续空白拍平（`_flat()`）。
6. **`report.csv` 曾被批次覆盖**：早期实现每次只写本批 `rows`。
   已改为 `merge_with_history()` 合并写入，报告始终是累计全量。
7. **重抓失败会抹掉已有的成功记录**。合并逻辑已加保护：失败结果不覆盖历史成功行。
8. **风控页地址曾被当成图片 URL 写进报告**（`pc-frequent-pro.pf.jd.com/?reason=403`）。
   日志正则已限定只认 `360buyimg.com` / `jfs/`，写 CSV 时再做一次兜底清洗。
9. **openpyxl 的坑**：给单元格 `hyperlink` 赋值时，若 `value` 为 `None`，
   它会自动把 URL 填进 `value`。J 列挂完超链接后必须再 `value = None` 清一次。
10. **`report.csv` 被 Excel 打开时写入会 `PermissionError`**。
    写报告改为三级降级：原文件 → `report_2.csv` … `report_20.csv` → 放弃落盘但不中断抓取。
11. **`shutil.move` 在部分沙箱环境会被 safe-delete 拦截**（报 trash operation 失败）。
    改用 `cp` + `rm` + `mv` 组合。
12. **`.bat` 里绝不能出现裸尖括号**，包括 `REM` 注释行 —— cmd **仍会解析 `REM` 行里的
    重定向符**，会把后面的行（连标签一起）吃掉，报 `cannot find the batch label`。
    用 `--` 代替 `->`。同理 `.bat` 必须纯 ASCII + CRLF。
13. **`set "PY=py -3"` 这种写法不能用于后续加引号调用** —— `"!PY!" x.py` 会去找一个
    名为 `py -3` 的文件。必须先用 `for /f` 解析出真实 `sys.executable` 路径。
14. **`goto` 出 `call` 子程序不可靠**：`call :done` 里的 `goto end` 或 `exit /b` 都只会
    "返回调用点"，然后掉进下一个分支。收尾判断要直接写在每个分支末尾，不要封装成子程序。
